from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.domain.purchase_engine.recommendation import Constraint, NAMES, calculate
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.plant_workflow import RequirementAdjustment
from app.tests.test_inventory import inventory_api
from app.tests.test_inventory_masters import masters_api
from app.tests.test_projection import at, projection_api, save
from app.tests.test_reorder import add_supplier, payload as timing_payload

D = Decimal
BASE = '/api/v1/purchasing/recommendations/assess'


def engine(target='13', projected='0', **values):
    constraints = {name: Constraint('NOT_APPLICABLE') for name in NAMES}
    constraints.update({name: value if isinstance(value, Constraint) else Constraint('APPLICABLE', D(value)) for name, value in values.items()})
    return calculate(target=D(target) if target is not None else None, projected=D(projected), constraints=constraints)


@pytest.mark.parametrize('projected', ['13', '20'])
def test_raw_nonpositive_does_not_trigger_moq(projected):
    result = engine(projected=projected, moq='100', pack_size='12')
    assert result['recommended_quantity'] == D('0')
    assert result['raw_quantity'] <= 0


@pytest.mark.parametrize('values,expected', [({}, '13'), ({'moq': '20'}, '20'),
    ({'pack_size': '12'}, '24'), ({'order_multiple': '10'}, '20'),
    ({'moq': '20', 'pack_size': '12', 'order_multiple': '10'}, '60'),
    ({'moq': '61', 'pack_size': '12', 'order_multiple': '10'}, '120')])
def test_constraints_apply_simultaneously(values, expected):
    assert engine(**values)['recommended_quantity'] == D(expected)


def test_decimal_increments_and_negative_projected_stock():
    result = engine(target='0.1001', projected='-0.2002', pack_size='0.25', order_multiple='0.30')
    assert result['raw_quantity'] == D('0.3003')
    assert result['combined_increment'] == D('1.50')
    assert result['recommended_quantity'] == D('1.50')
    assert result['stock_after_receipt'] == D('1.2998')


@pytest.mark.parametrize('name,limit,code', [('max_order_quantity', '59', 'MAX_ORDER_CONFLICT'),
    ('max_stock_quantity', '59', 'MAX_STOCK_CONFLICT')])
def test_maximum_conflict_is_not_silently_capped(name, limit, code):
    result = engine(pack_size='12', order_multiple='10', **{name: limit})
    assert result['status'] == 'CONFLICT' and result['recommended_quantity'] is None
    assert result['candidate_quantity'] == D('60')
    assert result['limitations'][0]['code'] == code


def test_exact_maximum_and_raw_multiple_require_no_extra_rounding():
    assert engine(target='60', pack_size='12', order_multiple='10', max_order_quantity='60', max_stock_quantity='60')['recommended_quantity'] == D('60')


def test_missing_constraints_and_target_are_not_zero():
    for name in NAMES:
        result = engine(**{name: Constraint('UNKNOWN')})
        assert result['recommended_quantity'] is None and result['status'] == 'INCOMPLETE'
    assert engine(target=None)['limitations'][0]['code'] == 'TARGET_UNCONFIRMED'
    assert engine(projected='20', moq=Constraint('UNKNOWN'))['recommended_quantity'] is None


def test_existing_overstock_does_not_recommend_negative_purchase():
    result = engine(projected='20', max_stock_quantity='15')
    assert result['recommended_quantity'] == 0
    assert result['limitations'][0]['code'] == 'EXISTING_STOCK_ABOVE_MAXIMUM'


def test_large_lcm_returns_conflict_instead_of_overflow_or_float():
    result = engine(pack_size='99999999999999.9999', order_multiple='99999999999999.9998')
    assert result['status'] == 'CONFLICT'
    assert result['limitations'][0]['code'] == 'QUANTITY_OUT_OF_RANGE'


def test_exact_arithmetic_independent_of_ambient_precision():
    with localcontext() as ctx:
        ctx.prec = 6
        assert engine(target='99999999.0001', projected='99999998.9000')['raw_quantity'] == D('.1001')


def test_grid_result_is_smallest_common_multiple_meeting_need():
    # Independent finite enumeration checks correctness and minimality, not just divisibility.
    for raw in range(1, 15):
        for pack in range(1, 6):
            for multiple in range(1, 6):
                expected = next(q for q in range(max(raw, 7), 121) if q % pack == 0 and q % multiple == 0)
                assert engine(target=str(raw), moq='7', pack_size=str(pack), order_multiple=str(multiple))['recommended_quantity'] == expected


@pytest.mark.parametrize('value', [0.1, True, D('NaN'), D('Infinity'), D('0.00001'), D('-1')])
def test_invalid_exact_quantities(value):
    constraints = {name: Constraint('NOT_APPLICABLE') for name in NAMES}
    with pytest.raises(ValueError):
        calculate(target=value, projected=D('0'), constraints=constraints)


def payload(data, supplier_id):
    lead = timing_payload(data, supplier_id)['lead_time']
    lead['days'] = 5
    return {'consumable_id': data['consumable_id'], 'planning_version_id': data['planning_version_id'],
            'source_set_id': data['source_set_id'], 'supplier_id': str(supplier_id), 'unit_id': data['unit_id'],
            'initiated_at': at(2).isoformat(), 'receipt_at': at(7).isoformat(),
            'evidence_from': at(1).isoformat(), 'evidence_until': at(11).isoformat(),
            'target': {'quantity': '53', 'approval_reference': 'synthetic-target'}, 'lead_time': lead,
            'constraints': {**{name: {'state': 'NOT_APPLICABLE', 'approval_reference': 'synthetic-none'} for name in NAMES},
                            'moq': {'state': 'APPLICABLE', 'value': '20', 'approval_reference': 'synthetic-moq'},
                            'pack_size': {'state': 'APPLICABLE', 'value': '12', 'approval_reference': 'synthetic-pack'},
                            'order_multiple': {'state': 'APPLICABLE', 'value': '10', 'approval_reference': 'synthetic-multiple'},
                            'other_constraints': 'CONFIRMED_NONE', 'other_constraints_reference': 'synthetic-no-others'}}


@pytest.fixture
def purchase_api(projection_api):
    client, session, user, headers, data, adjustment_id = projection_api
    supplier_id = add_supplier(session, data['consumable_id'])
    return client, session, user, headers, data, payload(data, supplier_id), adjustment_id


def test_api_explains_all_inputs_and_has_no_write_side_effect(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    before = session.scalar(select(func.count()).select_from(AuditLog))
    response = client.post(BASE, headers=headers, json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'RECOMMENDED' and result['recommended_quantity'] == '60.0000'
    assert result['final_requirement'] == '80.0000' and result['current_stock'] == '100.0000'
    assert result['projected_stock_at_receipt'] == '40.0000' and result['confirmed_incoming_before_receipt'] == '0.0000'
    assert result['msl_at_receipt'] == '50.0000' and result['target_stock'] == '53.0000'
    assert result['raw_quantity'] == '13.0000' and result['lead_time']['days'] == 5
    assert result['constraints']['pack_size']['value'] == '12.0000'
    assert result['supplier_id'] == request['supplier_id'] and result['policy_basis'] == 'OWNER_APPROVED_PROVISIONAL'
    assert result['projection']['source_set_id'] == data['source_set_id'] and result['is_live'] is False
    assert session.scalar(select(func.count()).select_from(AuditLog)) == before


def test_incoming_received_and_reserved_quantities_count_once(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    data['incoming'] = [{'source_id': 'partial', 'status': 'CONFIRMED', 'scheduled_quantity': '100',
                         'received_quantity': '60', 'cancelled_quantity': '10', 'available_at': at(4).isoformat()},
                        {'source_id': 'late', 'status': 'CONFIRMED', 'scheduled_quantity': '1000',
                         'received_quantity': '0', 'cancelled_quantity': '0', 'available_at': at(8).isoformat()}]
    save(client, headers, data)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['confirmed_incoming_before_receipt'] == '30.0000'
    assert result['projected_stock_at_receipt'] == '70.0000'
    assert result['raw_quantity'] == '-17.0000' and result['recommended_quantity'] == '0.0000'


@pytest.mark.parametrize('field', list(NAMES))
def test_omitted_constraint_is_unknown(purchase_api, field):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request['constraints'].pop(field)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['status'] == 'INCOMPLETE' and result['recommended_quantity'] is None
    assert result['raw_quantity'] == '13.0000'


@pytest.mark.parametrize('field,code', [('target', 'TARGET_UNCONFIRMED'), ('lead_time', 'LEAD_TIME_UNCONFIRMED')])
def test_missing_target_or_lead_time(purchase_api, field, code):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request.pop(field)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['recommended_quantity'] is None and result['limitations'][0]['code'] == code


def test_unknown_additional_supplier_constraint_blocks(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request['constraints']['other_constraints'] = 'UNKNOWN'
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['limitations'][0]['code'] == 'ADDITIONAL_CONSTRAINTS_UNCONFIRMED'


def test_permissions_are_checked_and_read_grant_is_sufficient(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    assert client.post(BASE, json=request).status_code == 401
    user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code == 'inventory.projection.read']
    session.commit()
    assert client.post(BASE, headers=headers, json=request).status_code == 200
    user.roles[0].permissions = []
    session.commit()
    assert client.post(BASE, headers=headers, json=request).status_code == 403


@pytest.mark.parametrize('model', [Consumable, Unit, Supplier, SupplierConsumable])
def test_inactive_master_blocks_new_recommendation(purchase_api, model):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    session.scalar(select(model)).is_active = False
    session.commit()
    response = client.post(BASE, headers=headers, json=request)
    assert response.status_code == 409 and response.json()['code'] == 'PURCHASE_MASTER_INACTIVE'


def test_unknown_supplier_and_wrong_unit_rejected(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    assert client.post(BASE, headers=headers, json={**request, 'supplier_id': str(uuid4())}).status_code == 409
    assert client.post(BASE, headers=headers, json={**request, 'unit_id': str(uuid4())}).status_code == 409


@pytest.mark.parametrize('value', [0.1, True, 'NaN', '-1', '1.00001'])
def test_api_rejects_inexact_target(purchase_api, value):
    client, session, user, headers, data, request, _ = purchase_api
    request['target']['quantity'] = value
    assert client.post(BASE, headers=headers, json=request).status_code == 422


def test_no_client_balance_or_silent_pack_size_semantics(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    assert client.post(BASE, headers=headers, json={**request, 'projected_stock': '999'}).status_code == 422
    request['constraints']['pack_size']['value'] = '0'
    assert client.post(BASE, headers=headers, json=request).status_code == 422


@pytest.mark.parametrize('change,code', [('lead', 'RECEIPT_LEAD_TIME_MISMATCH'), ('calendar', 'CALENDAR_UNCONFIRMED'),
    ('expired', 'PURCHASE_EVIDENCE_EXPIRED'), ('supplier', 'LEAD_TIME_SUPPLIER_MISMATCH')])
def test_invalid_timing_evidence_stays_incomplete(purchase_api, change, code):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    if change == 'lead': request['lead_time']['days'] = 4
    elif change == 'calendar': request['lead_time']['basis'] = 'WORKING_DAYS'
    elif change == 'expired': request['evidence_until'] = at(6).isoformat()
    else: request['lead_time']['supplier_id'] = str(uuid4())
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['recommended_quantity'] is None and result['limitations'][0]['code'] == code


def test_same_timestamp_event_is_not_silently_excluded(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    data['demand'][0]['events'][0]['at'] = request['receipt_at']
    save(client, headers, data)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['recommended_quantity'] is None
    assert result['limitations'][0]['code'] == 'RECEIPT_EVENT_ORDER_UNCONFIRMED'


def test_monthly_only_or_stale_requirements_cannot_recommend(purchase_api):
    client, session, user, headers, data, request, adjustment_id = purchase_api
    result = client.post(BASE, headers=headers, json={**request, 'source_set_id': None}).json()
    assert result['status'] == 'INCOMPLETE' and result['recommended_quantity'] is None
    save(client, headers, data)
    session.get(RequirementAdjustment, adjustment_id).requested_qty = D('81')
    session.commit()
    assert client.post(BASE, headers=headers, json=request).json()['limitations'][0]['code'] == 'PROJECTION_INCOMPLETE'


def test_maximum_conflict_api_exposes_candidate_not_a_recommendation(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request['constraints']['max_stock_quantity'] = {'state': 'APPLICABLE', 'value': '99', 'approval_reference': 'synthetic-max'}
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['status'] == 'CONFLICT' and result['recommended_quantity'] is None
    assert result['candidate_quantity'] == '60.0000'


def test_database_error_is_sanitized(purchase_api, monkeypatch):
    from app.repositories import purchase_recommendation
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    def fail(*args):
        raise SQLAlchemyError('private connection detail')
    monkeypatch.setattr(purchase_recommendation, 'context', fail)
    response = client.post(BASE, headers=headers, json=request)
    assert response.status_code == 503 and 'private connection detail' not in response.text


def test_working_calendar_validates_receipt_date(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request['lead_time'].update(days=2, basis='WORKING_DAYS', calendar={
        'reference': 'synthetic-calendar', 'approval_reference': 'synthetic-calendar-approval',
        'first_date': '2020-01-01', 'last_date': '2020-01-10',
        'working_dates': ['2020-01-02', '2020-01-03', '2020-01-06', '2020-01-07'],
        'convention': 'UTC_DATES_START_EXCLUDED_END_INCLUDED'})
    request['receipt_at'] = at(6).isoformat()
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['recommended_quantity'] == '60.0000'
    request['lead_time']['calendar']['last_date'] = '2020-01-07'
    request['lead_time']['days'] = 10
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['limitations'][0]['code'] == 'CALENDAR_COVERAGE_UNAVAILABLE'


def test_known_constraints_require_reference(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    request['constraints']['max_order_quantity'].pop('approval_reference')
    assert client.post(BASE, headers=headers, json=request).status_code == 422


def test_target_below_msl_is_visible_and_not_silently_replaced(purchase_api):
    client, session, user, headers, data, request, _ = purchase_api
    save(client, headers, data)
    request['target']['quantity'] = '30'
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['target_stock'] == '30.0000' and result['recommended_quantity'] == '0.0000'
    assert 'TARGET_BELOW_MSL' in {row['code'] for row in result['limitations']}
