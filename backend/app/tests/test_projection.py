from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.domain.inventory_engine.projection import Event, Floor, calculate
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.auth import Permission
from app.models.inventory import StockSnapshot
from app.models.inventory_masters import Supplier, SupplierConsumable
from app.models.plant_workflow import RequirementAdjustment
from app.models.prd import PlanningVersion
from app.models.production import Plant
from app.models.projection import ProjectionInputSet
from app.modules.inventory.projection_router import projection_database
from app.schemas.projection import ProjectionInputs
from app.tests.test_inventory import inventory_api, source_payload
from app.tests.test_inventory_masters import masters_api

D = Decimal
BASE = '/api/v1/inventory/projections'


def at(day, hour=0):
    return datetime(2020, 1, day, hour, tzinfo=timezone.utc)


def engine(**changes):
    values = dict(opening=D('100.0000'), baseline=at(2), cutoff=at(10), receipts=(),
                  demands=(Event('d1', at(5), D('60')),), floors=(Floor('msl1', at(1), D('50')),))
    return calculate(**{**values, **changes})


def test_no_incoming_future_breach_and_negative_shortage():
    result = engine()
    assert result['projected_stock'] == D('40')
    assert result['first_future_breach_at'] == at(5)
    assert result['future_breach'] is True
    assert engine(demands=(Event('d1', at(5), D('110')),))['projected_stock'] == D('-10')


@pytest.mark.parametrize('day,breach', [(4, False), (6, True), (11, True)])
def test_receipts_before_after_and_outside_breach(day, breach):
    result = engine(receipts=(Event('r1', at(day), D('30')),))
    assert result['future_breach'] is breach
    assert result['projected_stock'] == D('40' if day == 11 else '70')
    assert len(result['excluded']) == (1 if day == 11 else 0)


def test_exact_msl_is_distinct_and_not_below():
    result = engine(demands=(Event('d1', at(5), D('50')),))
    assert result['timeline'][0]['msl_condition'] == 'AT_MSL'
    assert result['future_breach'] is False
    assert engine(opening=D('50'), demands=())['current_msl_condition'] == 'AT_MSL'


def test_effective_msl_change_and_recovery_do_not_erase_first_breach():
    result = engine(demands=(), floors=(Floor('old', at(1), D('50')), Floor('new', at(4), D('110'))),
                    receipts=(Event('r', at(6), D('30')),))
    assert result['first_future_breach_at'] == at(4) and result['projected_stock'] == D('130')
    result = engine(opening=D('40'), receipts=(Event('r', at(3), D('30')),), demands=(Event('d', at(4), D('30')),))
    assert result['current_msl_condition'] == 'BELOW_MSL' and result['first_future_breach_at'] == at(4)


def test_exclusive_cutoff_and_lead_time_do_not_add_supply():
    result = engine(cutoff=at(5), lead_time_at=at(5))
    assert result['projected_stock'] == D('100') and result['timeline'] == []
    assert result['lead_time_balance'] == D('100')


def test_no_msl_or_lead_time_does_not_mean_zero():
    result = engine(floors=())
    assert result['projected_stock'] == D('40') and result['future_breach'] is None
    assert {item['code'] for item in result['limitations']} == {'MSL_UNCONFIGURED', 'LEAD_TIME_UNCONFIGURED'}


def test_same_timestamp_order_is_not_invented():
    result = engine(receipts=(Event('r', at(5), D('100')),))
    assert result['status'] == 'INCOMPLETE' and 'projected_stock' not in result
    assert result['limitations'][0]['code'] == 'TIMING_ORDER_UNCONFIRMED'


def test_exact_decimal_and_deterministic_order():
    events = (Event('b', at(4), D('0.1001')), Event('a', at(3), D('0.2002')))
    first = engine(opening=D('0.3003'), demands=events)
    assert first['projected_stock'] == D('0')
    assert first == engine(opening=D('0.3003'), demands=tuple(reversed(events)))


@pytest.mark.parametrize('changes', [dict(opening=0.1), dict(opening=D('NaN')), dict(opening=D('0.00001')),
                                   dict(cutoff=at(1)), dict(baseline=datetime(2020, 1, 2)),
                                   dict(receipts=(Event('r', at(2), D('1')),)),
                                   dict(demands=(Event('same', at(3), D('1')), Event('same', at(4), D('1'))))])
def test_invalid_engine_inputs_cannot_silently_change_a_balance(changes):
    with pytest.raises(ValueError):
        engine(**changes)


def seed_requirement(session, actor_id, material_id, unit_code):
    plant = Plant(name='Synthetic projection plant')
    version = PlanningVersion(planning_period='2020-01', version_number=1, source_filename='synthetic.xlsx',
                              status='RELEASED_TO_PLANTS', created_by=actor_id, approved_by=actor_id, approved_at=at(1))
    session.add_all([plant, version])
    session.flush()
    adjustment = RequirementAdjustment(planning_version_id=version.id, plant_id=plant.id, consumable_id=material_id,
                                      category='SPECIAL', requested_qty=D('80'), uom=unit_code, reason='Synthetic approved demand',
                                      requested_by=actor_id, status='APPROVED', reviewed_by=actor_id, reviewed_at=at(1))
    session.add(adjustment)
    session.commit()
    return plant.id, version.id, adjustment.id


def input_payload(material_id, unit_id, plant_id, version_id, snapshot_id):
    return {'source_set_id': 'synthetic-inputs-1', 'source_reference': 'synthetic-source-export',
            'import_reason': 'Synthetic projection validation', 'planning_version_id': str(version_id),
            'stock_snapshot_id': str(snapshot_id), 'consumable_id': str(material_id), 'unit_id': str(unit_id),
            'reconciled_as_of': at(2).isoformat(), 'coverage_until': at(10).isoformat(),
            'reconciliation_reference': 'synthetic-received-fulfilled-reserved-reconciliation',
            'demand': [{'plant_id': str(plant_id), 'fulfilled_quantity': '10', 'reserved_quantity': '10',
                        'events': [{'source_id': 'demand-1', 'at': at(5).isoformat(), 'quantity': '60'}]}],
            'incoming': [], 'msl_history': [{'source_id': 'msl-1', 'effective_at': at(1).isoformat(),
                                           'quantity': '50', 'approval_reference': 'synthetic-msl-approval'}]}


@pytest.fixture
def projection_api(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    user.roles[0].permissions.extend([Permission(code='inventory.projection.read', description='Synthetic central reader'),
                                     Permission(code='inventory.projection.import', description='Synthetic source importer')])
    session.commit()
    client.app.dependency_overrides[projection_database] = client.app.dependency_overrides[get_db]
    client.app.state.settings.projection_import_enabled = True
    material_id, unit_id = UUID(material['id']), UUID(unit['id'])
    plant_id, version_id, adjustment_id = seed_requirement(session, user.id, material_id, unit['code'])
    stock = source_payload(material_id, unit_id, as_of=at(2).isoformat(), quantity='100')
    assert client.post('/api/v1/inventory/imports', headers=headers, json=stock).status_code == 201
    snapshot_id = session.scalar(select(StockSnapshot.id))
    data = input_payload(material_id, unit_id, plant_id, version_id, snapshot_id)
    return client, session, user, headers, data, adjustment_id


def view(client, headers, data, **changes):
    params = {'consumable_id': data['consumable_id'], 'planning_version_id': data['planning_version_id'],
              'cutoff': at(10).isoformat(), 'source_set_id': data['source_set_id'], **changes}
    return client.get(BASE, headers=headers, params={key: value for key, value in params.items() if value is not None})


def save(client, headers, data):
    response = client.post(BASE + '/inputs', headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_import_report_replay_audit_and_no_double_demand(projection_api):
    client, session, user, headers, data, _ = projection_api
    saved = save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['status'] == 'COMPLETE' and result['projected_stock'] == '40.0000'
    assert result['requirement_totals'][0]['final_quantity'] == '80.0000'
    assert result['first_future_breach_at'] == '2020-01-05T00:00:00Z'
    assert result['timeline'][0]['requirements'] == '60.0000'
    replay = client.post(BASE + '/inputs', headers=headers, json=data)
    assert replay.status_code == 200 and replay.json()['id'] == saved['id'] and replay.json()['replayed']
    assert session.scalar(select(func.count()).select_from(ProjectionInputSet)) == 1
    assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'IMPORT_PROJECTION_INPUTS')) == 1
    changed = deepcopy(data)
    changed['msl_history'][0]['quantity'] = '55'
    assert client.post(BASE + '/inputs', headers=headers, json=changed).status_code == 409


def test_monthly_totals_without_schedule_surface_limits(projection_api):
    client, session, user, headers, data, _ = projection_api
    result = view(client, headers, data, source_set_id=None).json()
    assert result['status'] == 'INCOMPLETE' and result['projected_stock'] is None
    assert result['timeline'] == [] and result['future_breach'] is None
    assert 'TIMING_UNCONFIRMED' in {row['code'] for row in result['limitations']}
    data['demand'][0]['events'] = None
    save(client, headers, data)
    assert view(client, headers, data).json()['projected_stock'] is None


@pytest.mark.parametrize('field,value,code', [('incoming', None, 'INCOMING_UNCONFIRMED'),
                                           ('reconciliation_reference', None, 'RECONCILIATION_UNCONFIRMED')])
def test_missing_source_data_is_not_assumed_zero(projection_api, field, value, code):
    client, session, user, headers, data, _ = projection_api
    data[field] = value
    save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['projected_stock'] is None and code in {row['code'] for row in result['limitations']}


def test_partial_received_cancelled_unconfirmed_supply(projection_api):
    client, session, user, headers, data, _ = projection_api
    data['incoming'] = [{'source_id': 'line-1', 'status': 'CONFIRMED', 'scheduled_quantity': '100',
                         'received_quantity': '60', 'cancelled_quantity': '10', 'available_at': at(4).isoformat()},
                        {'source_id': 'line-2', 'status': 'UNCONFIRMED', 'scheduled_quantity': '1000',
                         'received_quantity': '0', 'cancelled_quantity': '0', 'available_at': at(3).isoformat()}]
    save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['projected_stock'] == '70.0000' and result['future_breach'] is False
    assert result['timeline'][0]['receipts'] == '30.0000'


def test_unapproved_changed_and_superseded_requirements_block_results(projection_api):
    client, session, user, headers, data, adjustment_id = projection_api
    save(client, headers, data)
    adjustment = session.get(RequirementAdjustment, adjustment_id)
    adjustment.requested_qty = D('90')
    session.commit()
    result = view(client, headers, data).json()
    assert result['projected_stock'] is None
    assert 'REQUIREMENT_INPUTS_CHANGED' in {row['code'] for row in result['limitations']}
    version = session.get(PlanningVersion, UUID(data['planning_version_id']))
    version.status = 'SUPERSEDED'
    session.commit()
    assert 'FINAL_REQUIREMENT_NOT_APPROVED' in {row['code'] for row in view(client, headers, data).json()['limitations']}


def test_new_stock_requires_new_reconciliation(projection_api):
    client, session, user, headers, data, _ = projection_api
    save(client, headers, data)
    stock = source_payload(data['consumable_id'], data['unit_id'], export_id='new-stock', as_of=at(3).isoformat(), quantity='120')
    assert client.post('/api/v1/inventory/imports', headers=headers, json=stock).status_code == 201
    result = view(client, headers, data).json()
    assert result['projected_stock'] is None and 'STOCK_INPUTS_CHANGED' in {row['code'] for row in result['limitations']}


def test_permissions_disabled_inputs_and_no_local_msl_edits(projection_api):
    client, session, user, headers, data, _ = projection_api
    assert client.get(BASE + '/status').status_code == 401
    client.app.state.settings.projection_import_enabled = False
    assert client.post(BASE + '/inputs', headers=headers, json=data).json()['code'] == 'PROJECTION_IMPORT_DISABLED'
    assert client.patch(BASE + '/inputs', headers=headers, json=data).status_code == 405
    user.roles[0].code = 'ADMIN'
    user.roles[0].permissions = []
    session.commit()
    assert client.get(BASE + '/status', headers=headers).status_code == 403
    assert client.post(BASE + '/inputs', headers=headers, json=data).status_code == 403
    assert view(client, headers, data).status_code == 403


@pytest.mark.parametrize('mutation', ['unit', 'plant', 'quantity', 'snapshot'])
def test_inconsistent_inputs_are_rejected_atomically(projection_api, mutation):
    client, session, user, headers, data, _ = projection_api
    if mutation == 'unit': data['unit_id'] = str(uuid4())
    if mutation == 'plant': data['demand'][0]['plant_id'] = str(uuid4())
    if mutation == 'quantity': data['demand'][0]['events'][0]['quantity'] = '61'
    if mutation == 'snapshot': data['stock_snapshot_id'] = str(uuid4())
    assert client.post(BASE + '/inputs', headers=headers, json=data).status_code == 409
    assert session.scalar(select(func.count()).select_from(ProjectionInputSet)) == 0


def test_audit_failure_rolls_back_input_set(projection_api, monkeypatch):
    client, session, user, headers, data, _ = projection_api
    from app.services import projection
    def fail(**kwargs):
        raise SQLAlchemyError('synthetic private diagnostic')
    monkeypatch.setattr(projection, 'AuditLog', fail)
    response = client.post(BASE + '/inputs', headers=headers, json=data)
    assert response.status_code == 503 and 'private' not in response.text
    assert session.scalar(select(func.count()).select_from(ProjectionInputSet)) == 0


@pytest.mark.parametrize('value', [0.1, True, 'NaN', '-1', '0.00001'])
def test_source_decimal_validation(value):
    data = input_payload(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    data['msl_history'][0]['quantity'] = value
    with pytest.raises(ValidationError):
        ProjectionInputs.model_validate(data)


def test_duplicate_source_and_naive_time_are_rejected():
    data = input_payload(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    data['demand'][0]['events'] *= 2
    with pytest.raises(ValidationError): ProjectionInputs.model_validate(data)

    data['demand'][0]['events'] = []
    data['reconciled_as_of'] = '2020-01-02T00:00:00'
    with pytest.raises(ValidationError): ProjectionInputs.model_validate(data)


def test_lead_time_interval_uses_approved_mapping_and_does_not_create_receipt(projection_api):
    client, session, user, headers, data, _ = projection_api
    supplier = Supplier(code='SYNTHETIC-S1', name='Synthetic projection supplier')
    session.add(supplier)
    session.flush()
    session.add(SupplierConsumable(supplier_id=supplier.id, consumable_id=UUID(data['consumable_id'])))
    session.commit()
    data['lead_time'] = {'supplier_id': str(supplier.id), 'starts_at': at(1).isoformat(), 'usable_at': at(6).isoformat(),
                         'start_event': 'SYNTHETIC_SOURCE_START', 'calendar_basis': 'WORKING_DAYS',
                         'calendar_reference': 'Synthetic approved calendar interval', 'approval_reference': 'Synthetic approval'}
    save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['lead_time_balance'] == '40.0000' and result['projected_stock'] == '40.0000'
    assert result['projected_msl_condition'] == 'BELOW_MSL'
    assert all(row['receipts'] == '0.0000' for row in result['timeline'])


def test_lead_time_without_supplier_mapping_cannot_be_imported(projection_api):
    client, session, user, headers, data, _ = projection_api
    data['lead_time'] = {'supplier_id': str(uuid4()), 'starts_at': at(1).isoformat(), 'usable_at': at(6).isoformat(),
                         'start_event': 'SOURCE_START', 'calendar_basis': 'CALENDAR_DAYS',
                         'calendar_reference': 'Synthetic calendar', 'approval_reference': 'Synthetic approval'}
    response = client.post(BASE + '/inputs', headers=headers, json=data)
    assert response.status_code == 409 and response.json()['code'] == 'SUPPLIER_MAPPING_MISSING'


def test_coverage_and_cutoff_cannot_claim_unknown_future(projection_api):
    client, session, user, headers, data, _ = projection_api
    save(client, headers, data)
    result = view(client, headers, data, cutoff=at(11).isoformat()).json()
    assert result['projected_stock'] is None and 'INPUT_COVERAGE_EXCEEDED' in {row['code'] for row in result['limitations']}
    assert view(client, headers, data, cutoff=at(2).isoformat()).status_code == 422
    assert view(client, headers, data, cutoff='2020-01-06T00:00:00').status_code == 422


@pytest.mark.parametrize('available_at', [None, '2020-01-01T00:00:00Z'])
def test_outstanding_supply_with_missing_or_overdue_time_blocks_projection(projection_api, available_at):
    client, session, user, headers, data, _ = projection_api
    data['incoming'] = [{'source_id': 'line-1', 'status': 'CONFIRMED', 'scheduled_quantity': '100',
                         'received_quantity': '60', 'cancelled_quantity': '10', 'available_at': available_at}]
    save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['projected_stock'] is None and 'SUPPLY_TIMING_UNCONFIRMED' in {row['code'] for row in result['limitations']}


def test_unknown_timing_still_reports_known_current_msl(projection_api):
    client, session, user, headers, data, _ = projection_api
    data['demand'][0]['events'] = None
    data['msl_history'][0]['quantity'] = '110'
    save(client, headers, data)
    result = view(client, headers, data).json()
    assert result['current_msl'] == '110.0000' and result['current_msl_condition'] == 'BELOW_MSL'
    assert result['projected_stock'] is None and result['future_breach'] is None


def test_read_grant_does_not_allow_import(projection_api):
    client, session, user, headers, data, _ = projection_api
    save(client, headers, data)
    user.roles[0].permissions = [grant for grant in user.roles[0].permissions if grant.code == 'inventory.projection.read']
    session.commit()
    assert view(client, headers, data).status_code == 200
    assert client.post(BASE + '/inputs', headers=headers, json=data).status_code == 403


def test_scope_and_missing_source_returns_clear_errors(projection_api):
    client, session, user, headers, data, _ = projection_api
    save(client, headers, data)
    other = PlanningVersion(planning_period='2020-02', version_number=1, source_filename='synthetic-other.xlsx',
                            status='RELEASED_TO_PLANTS', created_by=user.id, approved_by=user.id, approved_at=at(1))
    session.add(other)
    session.commit()
    response = view(client, headers, data, planning_version_id=str(other.id))
    assert response.status_code == 409 and response.json()['code'] == 'PROJECTION_SCOPE_MISMATCH'
    assert view(client, headers, data, source_set_id='missing').status_code == 404


def test_replaced_adjustment_with_same_total_invalidates_evidence(projection_api):
    client, session, user, headers, data, adjustment_id = projection_api
    save(client, headers, data)
    adjustment = session.get(RequirementAdjustment, adjustment_id)
    adjustment.status = 'REJECTED'
    session.add(RequirementAdjustment(planning_version_id=adjustment.planning_version_id, plant_id=adjustment.plant_id,
                                      consumable_id=adjustment.consumable_id, category='SPECIAL', requested_qty=adjustment.requested_qty,
                                      uom=adjustment.uom, reason='Synthetic replacement', requested_by=user.id,
                                      status='APPROVED', reviewed_by=user.id, reviewed_at=at(1)))
    session.commit()
    result = view(client, headers, data).json()
    assert result['requirement_totals'][0]['final_quantity'] == '80.0000'
    assert result['projected_stock'] is None and 'REQUIREMENT_INPUTS_CHANGED' in {row['code'] for row in result['limitations']}
