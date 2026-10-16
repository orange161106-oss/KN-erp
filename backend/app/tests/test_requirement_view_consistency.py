"""Real import provenance and shared central/monthly demand, using disposable data."""
from decimal import Decimal
from uuid import UUID
from sqlalchemy import event, select
import pytest

from app.core.errors import ApplicationError
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderItem
from app.models.requirements import CalculatedRequirement, MonthlyRequirementRecord, RequirementCalculationError
from app.schemas.requirements import CalculationRunRequest
from app.services import basic_planning as basic, requirements_workspace as monthly
from app.services.requirements import get_calculated_requirements
from app.tests.test_central_basic_planning import db, catalog, imported, WHEN


def legacy_schedule(db, catalog):
    identity, _, _ = imported(db, catalog)
    batch = db.scalar(select(ImportBatch).where(ImportBatch.planning_version_id == identity))
    batch.validation_summary = {'workflow': basic.WORKFLOW, 'blocks_count': 1, 'grand_total': {},
        'planning_period': '2026-10', 'revision': 'R3'}
    for item in db.scalars(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == identity)):
        item.uom = 'Nos'
    db.commit()
    return identity


def test_old_schedule_default_recovers_master_unit_without_rewriting_source(db, catalog):
    identity = legacy_schedule(db, catalog)
    value = basic.preview(db, identity, WHEN)
    assert value['errors'] == [] and value['complete']
    result = basic.calculate(db, CalculationRunRequest(planning_version_id=identity), catalog[0].id)
    assert result.error_count == 0
    rows = list(db.scalars(select(CalculatedRequirement)))
    assert sorted(r.calculated_qty for r in rows) == [Decimal('30'), Decimal('200')]
    assert {r.uom for r in rows} == {'PCS'}
    assert {i.uom for i in db.scalars(select(PRDOrderItem))} == {'Nos'}
    for row in rows:
        evidence = row.explanation_payload['production_source']
        assert evidence['source_unit'] == 'Nos' and evidence['unit'] == 'PCS'
        assert evidence['unit_source'] == 'LEGACY_SCHEDULE_PRODUCT_MASTER'


def test_explicit_unit_mismatch_is_still_reported(db, catalog):
    identity, _, _ = imported(db, catalog)
    item = db.scalar(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == identity))
    item.uom = 'KG'
    db.commit()
    value = basic.preview(db, identity, WHEN)
    assert 'PRODUCTION_UNIT_CHANGED' in {e['code'] for e in value['errors']}
    assert not value['complete']


def test_fresh_sales_schedule_uses_canonical_production_unit(db, catalog):
    from io import BytesIO
    from openpyxl import Workbook
    from app.models.masters import Customer, CustomerAlias
    from app.services.prd_workspace import preview_sales_schedule_upload, confirm_sales_schedule_import
    customer = Customer(code='DEMO-CUSTOMER', name='Synthetic customer')
    db.add(customer); db.flush()
    db.add(CustomerAlias(customer_id=customer.id, alias_text='SYNTHETIC', normalized_alias='synthetic')); db.commit()
    book = Workbook(); book.active.title = 'Prd. Order'
    for row in [['KNL', None, None, 'Production Order', "Oct'2026"],
        [None,None,None,'Schedule given on','01.10.2026'], [None,None,None,'Month','01.10.2026'],
        ['S. No','Part No','Item ID','Part Description','R3'], [1,'PART-A','ITEM-A','Synthetic A',100],
        [None,None,None,'SYNTHETIC - TOTAL',100], [None,None,None,'Grand Total',100]]:
        book.active.append(row)
    stream = BytesIO(); book.save(stream)
    review = preview_sales_schedule_upload(db, stream.getvalue(), 'production.xlsx', 'Prd. Order', '2026-10', 'R3')
    assert review.can_confirm
    confirm_sales_schedule_import(db, review.file_token, 'Prd. Order', '2026-10', 'R3', None, catalog[0].id)
    batch = db.scalar(select(ImportBatch))
    assert batch.validation_summary['production_unit_source'] == 'PRODUCT_MASTER'
    assert {item.uom for item in db.scalars(select(PRDOrderItem))} == {'PCS'}
    assert basic.preview(db, batch.planning_version_id, WHEN)['errors'] == []


def test_monthly_and_central_use_identical_saved_quantities_and_protect_sources(db, catalog):
    identity = legacy_schedule(db, catalog)
    old = MonthlyRequirementRecord(planning_version_id=identity, planning_period='2026-10', planning_month=10,
        planning_year=2026, part_name='Manual history', part_number='HISTORY', consumable_code='DRILL-A',
        consumable_name='Manual value', process_name='Drilling', scheduled_consumable_qty=Decimal('999'))
    db.add(old); db.commit()
    result = monthly.recalculate_monthly_requirements(db, catalog[0].id, 10, 2026)
    assert result.plan_metadata.source_workflow == basic.WORKFLOW
    central = get_calculated_requirements(db, identity)
    assert {r.id: r.calculated_qty for r in central} == {UUID(r.id): Decimal(r.required_qty) for r in result.records}
    assert result.plan_metadata.record_count == len(central) == 2
    assert db.get(MonthlyRequirementRecord, old.id).scheduled_consumable_qty == Decimal('999')
    assert {r.part_number for r in result.records} == {'PART-A', 'PART-B'}
    from app.modules.requirements.basic_router import export
    from app.tests.test_permission_foundation import actor
    document = export(identity, actor(is_super_admin=True), db, 'csv').body.decode('utf-8-sig')
    assert 'Part No.,Product Item ID,Product Description' in document
    assert 'PART-A,ITEM-A,Synthetic A' in document
    version = db.get(PlanningVersion, identity)
    version.status = 'APPROVED'; db.commit()
    with pytest.raises(ApplicationError) as failure:
        monthly.recalculate_monthly_requirements(db, catalog[0].id, 10, 2026)
    assert failure.value.code == 'CALCULATION_HISTORY_PROTECTED'


def test_monthly_error_loading_is_batched_and_retains_production_quantities(db, catalog):
    identity = legacy_schedule(db, catalog)
    item = db.scalar(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == identity))
    db.add_all([RequirementCalculationError(planning_version_id=identity, prd_order_item_id=item.id,
        product_id=item.product_id, error_code='PROCESS_REQUIRED', error_message='Choose an active process.') for _ in range(100)])
    db.commit(); db.expunge_all()
    queries = []
    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith('SELECT'): queries.append(statement)
    event.listen(db.get_bind(), 'before_cursor_execute', capture)
    try:
        records = monthly.calculate_workspace_requirements(db, month=10, year=2026)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', capture)
    assert len(records) == 100 and len(queries) <= 5
    assert {r.production_order_qty for r in records} == {format(item.planned_quantity, '.4f')}


def test_monthly_routes_cannot_bypass_central_plant_scope(db, catalog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from uuid import uuid4
    from app.core.errors import register_error_handlers
    from app.db.session import get_db
    from app.modules.requirements.requirements_workspace_router import router
    from app.security.dependencies import get_current_user
    from app.tests.test_permission_foundation import actor
    legacy_schedule(db, catalog)
    user = actor(requirements_read=True, requirements_update=True, plant_ids=[uuid4()])
    app = FastAPI(); register_error_handlers(app); app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        for path in ('records', 'plan-metadata', 'export'):
            assert client.get(f'/api/v1/requirements/workspace/{path}?month=10&year=2026').status_code == 403
        assert client.post('/api/v1/requirements/workspace/recalculate?month=10&year=2026').status_code == 403


def test_monthly_metadata_and_saved_line_reads_have_bounded_remote_round_trips(db, catalog):
    identity = legacy_schedule(db, catalog)
    basic.calculate(db, CalculationRunRequest(planning_version_id=identity), catalog[0].id)
    db.expunge_all()
    queries = []
    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith('SELECT'): queries.append(statement)
    event.listen(db.get_bind(), 'before_cursor_execute', capture)
    try:
        metadata = monthly.get_monthly_plan_metadata(db, 10, 2026)
        assert len(queries) == 2
        assert metadata.record_count == 2 and metadata.source_workflow == basic.WORKFLOW
        assert metadata.created_by_name == catalog[0].username
        queries.clear()
        records = monthly.calculate_workspace_requirements(db, month=10, year=2026)
        assert len(queries) <= 4
        assert {Decimal(row.required_qty) for row in records} == {Decimal('30'), Decimal('200')}
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', capture)
