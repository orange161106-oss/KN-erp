from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.domain.inventory_engine.reorder import Calendar, assess
from app.models.audit import AuditLog
from app.models.inventory_masters import Supplier, SupplierConsumable
from app.models.plant_workflow import RequirementAdjustment
from app.schemas.reorder import ReorderRequest
from app.tests.test_inventory import inventory_api
from app.tests.test_inventory_masters import masters_api
from app.tests.test_projection import at, projection_api, save

BASE = '/api/v1/inventory/reorder/assess'


def engine(**changes):
    args = dict(baseline=at(2), evaluated_at=at(2), cutoff=at(10), initial_condition='ABOVE_MSL',
                timeline=((at(5), 'BELOW_MSL'),), violation='BELOW_MSL', boundary='AT_CROSSING_ALLOWED', days=2)
    return assess(**{**args, **changes})


@pytest.mark.parametrize('days,deadline,required', [(1, 4, False), (2, 3, False), (3, 2, True), (4, 1, True), (0, 5, False)])
def test_lead_time_shorter_equal_longer_than_stock_cover(days, deadline, required):
    result = engine(days=days)
    assert result['reorder_required'] is required
    assert result['latest_safe_order_at'] == at(deadline)
    assert result['expected_msl_crossing_at'] == at(5)


@pytest.mark.parametrize('days,status', [(2, 'DETERMINED'), (8, 'INCOMPLETE'), (9, 'INCOMPLETE')])
def test_no_breach_requires_horizon_beyond_arrival(days, status):
    result = engine(days=days, timeline=())
    assert result['status'] == status
    assert result['reorder_required'] is (False if status == 'DETERMINED' else None)


def test_already_breached_needs_action_without_inventing_past_order_point():
    result = engine(initial_condition='BELOW_MSL', timeline=(), days=None)
    assert result['reorder_required'] is True and result['already_breached'] is True
    assert result['latest_safe_order_at'] is None
    assert result['crossing_time_kind'] == 'AT_OR_BEFORE_EVALUATION'


def test_evaluation_uses_event_state_and_recovery_not_stale_baseline():
    result = engine(evaluated_at=at(6), timeline=((at(5), 'BELOW_MSL'), (at(6), 'ABOVE_MSL')))
    assert result['already_breached'] is False and result['reorder_required'] is False
    assert engine(evaluated_at=at(5))['already_breached'] is True


@pytest.mark.parametrize('policy,required', [('BELOW_MSL', False), ('AT_OR_BELOW_MSL', True), (None, None)])
def test_equality_is_explicit_policy(policy, required):
    result = engine(initial_condition='AT_MSL', timeline=(), violation=policy)
    assert result['reorder_required'] is required


def test_receipt_recovery_does_not_erase_a_future_breach():
    result = engine(timeline=((at(5), 'BELOW_MSL'), (at(6), 'ABOVE_MSL')))
    assert result['expected_msl_crossing_at'] == at(5)


@pytest.mark.parametrize('changes,code', [({'days': None}, 'LEAD_TIME_UNCONFIRMED'),
    ({'working_days': True}, 'CALENDAR_UNCONFIRMED'), ({'initial_condition': 'UNKNOWN'}, 'MSL_UNCONFIGURED'),
    ({'boundary': None}, 'MSL_POLICY_UNCONFIRMED')])
def test_missing_evidence_is_unknown(changes, code):
    result = engine(**changes)
    assert result['reorder_required'] is None and result['limitations'][0]['code'] == code


def calendar():
    # Jan 6 is explicitly omitted as a synthetic holiday; no locale defaults.
    return Calendar(date(2020, 1, 1), date(2020, 1, 15), frozenset(
        date(2020, 1, d) for d in [1, 2, 3, 7, 8, 9, 10, 13, 14, 15]))


def test_working_days_skip_explicit_weekends_and_holidays():
    result = engine(timeline=((at(8), 'BELOW_MSL'),), working_days=True, calendar=calendar())
    assert result['latest_safe_order_at'] == at(3)
    assert result['earliest_usable_at_if_ordered_now'] == at(7)
    assert engine(timeline=((at(8), 'BELOW_MSL'),))['latest_safe_order_at'] == at(6)


def test_calendar_limits_and_nonworking_crossing_do_not_invent_intraday_cutoffs():
    for changes in [dict(timeline=((at(5), 'BELOW_MSL'),)), dict(days=10, timeline=((at(8), 'BELOW_MSL'),))]:
        result = engine(working_days=True, calendar=calendar(), **changes)
        assert result['reorder_required'] is None
        assert result['limitations'][0]['code'] == 'CALENDAR_COVERAGE_UNAVAILABLE'


def test_before_crossing_deadline_is_exclusive_without_microsecond_buffer():
    result = engine(boundary='BEFORE_CROSSING', evaluated_at=at(3))
    assert result['latest_safe_order_at'] == at(3)
    assert result['latest_safe_order_inclusive'] is False
    assert result['reorder_required'] is True


@pytest.mark.parametrize('changes', [dict(days=True), dict(days=1.5), dict(days=-1), dict(days=3661),
    dict(evaluated_at=at(1)), dict(cutoff=at(2)), dict(baseline=datetime(2020, 1, 2)),
    dict(timeline=((at(10), 'BELOW_MSL'),)), dict(violation='invented')])
def test_invalid_domain_inputs(changes):
    with pytest.raises(ValueError):
        engine(**changes)


def payload(data, supplier_id):
    return {'consumable_id': data['consumable_id'], 'planning_version_id': data['planning_version_id'],
            'source_set_id': data['source_set_id'], 'evaluated_at': at(2).isoformat(), 'cutoff': at(10).isoformat(),
            'policy': {'approval_reference': 'synthetic-policy', 'effective_from': at(1).isoformat(),
                       'effective_until': at(11).isoformat(), 'violation': 'BELOW_MSL', 'availability_boundary': 'BEFORE_CROSSING'},
            'lead_time': {'supplier_id': str(supplier_id), 'approval_reference': 'synthetic-duration',
                          'start_event': 'ORDER_INITIATED', 'end_event': 'MATERIAL_USABLE', 'days': 2,
                          'basis': 'ELAPSED_24_HOUR_DAYS', 'effective_from': at(1).isoformat(), 'effective_until': at(11).isoformat()}}


def add_supplier(session, material_id):
    supplier = Supplier(code='TIMING-SUPPLIER', name='Synthetic timing supplier')
    session.add(supplier)
    session.flush()
    session.add(SupplierConsumable(supplier_id=supplier.id, consumable_id=UUID(str(material_id))))
    session.commit()
    return supplier.id


@pytest.fixture
def reorder_api(projection_api):
    client, session, user, headers, data, adjustment_id = projection_api
    supplier_id = add_supplier(session, data['consumable_id'])
    return client, session, user, headers, data, payload(data, supplier_id), adjustment_id


def test_api_uses_persisted_projection_and_is_read_only(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    save(client, headers, data)
    before = session.scalar(select(func.count()).select_from(AuditLog))
    response = client.post(BASE, headers=headers, json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['latest_safe_order_at'] == '2020-01-03T00:00:00Z'
    assert result['reorder_required'] is False and result['is_live'] is False
    assert result['projection']['projected_stock'] == '40.0000'
    assert result['request']['policy']['approval_reference'] == 'synthetic-policy'
    assert session.scalar(select(func.count()).select_from(AuditLog)) == before


def test_incoming_prevents_breach_without_double_addition(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    data['incoming'] = [{'source_id': 'supply', 'status': 'CONFIRMED', 'scheduled_quantity': '100',
                         'received_quantity': '60', 'cancelled_quantity': '10', 'available_at': at(4).isoformat()}]
    save(client, headers, data)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['reorder_required'] is False and result['expected_msl_crossing_at'] is None
    assert result['projection']['projected_stock'] == '70.0000'


@pytest.mark.parametrize('field', ['policy', 'lead_time'])
def test_api_missing_policy_or_duration_is_not_defaulted(reorder_api, field):
    client, session, user, headers, data, request, _ = reorder_api
    save(client, headers, data)
    request.pop(field)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['status'] == 'INCOMPLETE' and result['reorder_required'] is None


def test_monthly_only_and_stale_requirements_cannot_produce_reorder(reorder_api):
    client, session, user, headers, data, request, adjustment_id = reorder_api
    unscheduled = {**request, 'source_set_id': None}
    result = client.post(BASE, headers=headers, json=unscheduled).json()
    assert result['reorder_required'] is None
    save(client, headers, data)
    session.get(RequirementAdjustment, adjustment_id).requested_qty = 90
    session.commit()
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['limitations'][0]['code'] == 'PROJECTION_INCOMPLETE'
    assert result['reorder_required'] is None


def test_read_permission_enforced_without_role_bypass(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    assert client.post(BASE, json=request).status_code == 401
    user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code != 'inventory.projection.read']
    session.commit()
    assert client.post(BASE, headers=headers, json=request).status_code == 403


@pytest.mark.parametrize('change,status', [({'days': 0.5}, 422), ({'days': True}, 422),
    ({'start_event': 'PO_APPROVED'}, 422), ({'supplier_id': str(uuid4())}, 409)])
def test_duration_validation_and_supplier_mapping(reorder_api, change, status):
    client, session, user, headers, data, request, _ = reorder_api
    save(client, headers, data)
    request['lead_time'].update(change)
    assert client.post(BASE, headers=headers, json=request).status_code == status


@pytest.mark.parametrize('field,code', [('policy', 'POLICY_COVERAGE_UNAVAILABLE'), ('lead_time', 'LEAD_TIME_VALIDITY_UNAVAILABLE')])
def test_expired_evidence_cannot_be_used(reorder_api, field, code):
    client, session, user, headers, data, request, _ = reorder_api
    save(client, headers, data)
    request[field]['effective_until'] = at(3).isoformat()
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['reorder_required'] is None and result['limitations'][0]['code'] == code


def test_request_rejects_client_calculated_stock_and_naive_dates(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    assert client.post(BASE, headers=headers, json={**request, 'projected_stock': '999'}).status_code == 422
    assert client.post(BASE, headers=headers, json={**request, 'evaluated_at': '2020-01-02T00:00:00'}).status_code == 422


def test_working_calendar_schema_rejects_duplicate_dates():
    data = payload({'consumable_id': str(uuid4()), 'planning_version_id': str(uuid4()), 'source_set_id': 'test'}, uuid4())
    data['lead_time']['basis'] = 'WORKING_DAYS'
    data['lead_time']['calendar'] = {'reference': 'synthetic', 'approval_reference': 'synthetic',
        'first_date': '2020-01-01', 'last_date': '2020-01-10', 'working_dates': ['2020-01-02', '2020-01-02'],
        'convention': 'UTC_DATES_START_EXCLUDED_END_INCLUDED'}
    with pytest.raises(ValueError):
        ReorderRequest.model_validate(data)


def test_late_receipt_does_not_remove_order_deadline(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    data['incoming'] = [{'source_id': 'late', 'status': 'CONFIRMED', 'scheduled_quantity': '30',
                         'received_quantity': '0', 'cancelled_quantity': '0', 'available_at': at(6).isoformat()}]
    save(client, headers, data)
    request['lead_time']['days'] = 3
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['reorder_required'] is True
    assert result['expected_msl_crossing_at'] == '2020-01-05T00:00:00Z'
    assert result['projection']['projected_stock'] == '70.0000'


def test_missing_msl_and_ambiguous_events_block_timing(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    data['msl_history'] = []
    save(client, headers, data)
    result = client.post(BASE, headers=headers, json=request).json()
    assert result['reorder_required'] is None and result['limitations'][0]['code'] == 'MSL_UNCONFIGURED'


def test_read_only_grant_can_assess_and_calendar_is_applied(reorder_api):
    client, session, user, headers, data, request, _ = reorder_api
    data['demand'][0]['events'][0]['at'] = at(8).isoformat()
    save(client, headers, data)
    user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code == 'inventory.projection.read']
    session.commit()
    request['lead_time']['basis'] = 'WORKING_DAYS'
    request['lead_time']['calendar'] = {'reference': 'synthetic', 'approval_reference': 'synthetic',
        'first_date': '2020-01-01', 'last_date': '2020-01-15',
        'working_dates': [day.isoformat() for day in sorted(calendar().working)],
        'convention': 'UTC_DATES_START_EXCLUDED_END_INCLUDED'}
    result = client.post(BASE, headers=headers, json=request)
    assert result.status_code == 200, result.text
    assert result.json()['latest_safe_order_at'] == '2020-01-03T00:00:00Z'
