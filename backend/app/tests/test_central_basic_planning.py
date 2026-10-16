"""Disposable-data checks for direct norms → central approval → existing purchase engine."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import pytest
from openpyxl import Workbook
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.tests.test_permission_foundation import db, actor
from app.core.errors import ApplicationError, register_error_handlers
from app.models.auth import User
from app.models.audit import AuditLog
from app.models.masters import Product, Customer, CustomerAlias
from app.models.production import Process
from app.models.inventory_masters import Consumable, Unit, Supplier, SupplierConsumable
from app.models.inventory import StockSnapshot
from app.models.prd import PlanningVersion, PRDOrderItem
from app.models.requirements import CalculatedRequirement
from app.models.plant_workflow import PlantConfirmation
from app.schemas.rules import ConsumptionNormCreate
from app.schemas.requirements import CalculationRunRequest
from app.schemas.inventory import SourceImport, SourceSnapshot
from app.schemas.projection import ProjectionInputs
from app.schemas.purchase_recommendation import PurchaseRequest
from app.schemas.purchase_order import DemandSubmission
from app.services import basic_planning as basic, rules, inventory, projection, purchase_recommendation, purchase_order
from app.services.requirements import calculate_planning_version_requirements
from app.services.requirement_approval import approve
from app.services.plant_workflow import get_final_requirements, _assert_plant_access

WHEN = date(2026, 10, 15)

@pytest.fixture
def catalog(db):
    root = User(username='synthetic_reviewer', password_hash='synthetic', is_super_admin=True)
    unit = Unit(code='PCS', name='Pieces'); process = Process(name='Drilling')
    a = Product(code='PROD-A', part_number='PART-A', item_id='ITEM-A', name='Synthetic A', uom='PCS')
    b = Product(code='PROD-B', part_number='PART-B', item_id='ITEM-B', name='Synthetic B', uom='PCS')
    supplier = Supplier(code='SUP-A', name='Synthetic supplier')
    db.add_all([root, unit, process, a, b, supplier]); db.flush()
    material = Consumable(code='DRILL-A', name='Synthetic drill', unit_id=unit.id)
    db.add(material); db.flush()
    db.add(SupplierConsumable(supplier_id=supplier.id, consumable_id=material.id)); db.commit()
    for product, rate in ((a, '2'), (b, '3')):
        rules.create_consumption_norm(db, ConsumptionNormCreate(rule_type='PRODUCTION_RATE', product_id=product.id,
            process_id=process.id, consumable_id=material.id, unit_id=unit.id, parameters={'rate':rate,'scrap_factor':'0'},
            rounding_policy='NONE', rounding_precision=4, effective_from=date(2026,1,1)), actor_id=root.id)
    return root, unit, process, a, b, material, supplier

def source(quantity='100', duplicate=False):
    rows = 'Part No,Item ID,Part Description,Planned Quantity,Unit\nPART-A,ITEM-A,Synthetic A,' + quantity + ',PCS\nPART-B,ITEM-B,Synthetic B,10,PCS\n'
    return (rows + ('PART-A,ITEM-A,Synthetic A,5,PCS\n' if duplicate else '')).encode()

def imported(db, catalog, content=None, revision='R3'):
    content = content or source()
    preview = basic.production_preview(db, content, 'production.csv', 'CSV', '2026-10', revision, WHEN)
    result = basic.production_confirm(db, content, 'production.csv', 'CSV', '2026-10', revision, WHEN, preview['review_token'], catalog[0].id)
    return result['planning_version_id'], preview, result

def calculated(db, catalog):
    identity, _, _ = imported(db, catalog)
    result = calculate_planning_version_requirements(db, CalculationRunRequest(planning_version_id=identity, as_of_date=WHEN), catalog[0].id)
    return identity, result

def approved(db, catalog):
    identity, result = calculated(db, catalog)
    reviewer = actor(is_super_admin=True); reviewer.id = catalog[0].id
    approve(db, identity, reviewer)
    return identity

def test_read_only_preview_exact_matching_and_no_mapping_prerequisite(db, catalog):
    before = len(list(db.scalars(select(AuditLog))))
    value = basic.production_preview(db, source(), 'production.csv', 'CSV', '2026-10', 'R3', WHEN)
    assert value['can_confirm'] and value['norm_ready'] and len(value['rows']) == 2
    assert value['rows'][0]['norm_count'] == 1
    assert db.scalar(select(PlanningVersion)) is None
    assert len(list(db.scalars(select(AuditLog)))) == before
    bad_pair = source().replace(b'PART-A,ITEM-A', b'PART-A,ITEM-B')
    value = basic.production_preview(db, bad_pair, 'production.csv', 'CSV', '2026-10', 'R3', WHEN)
    assert not value['can_confirm'] and value['rows'][0]['product_id'] is None

def test_import_is_atomic_retry_safe_and_keeps_explicit_zero(db, catalog):
    identity, preview, first = imported(db, catalog, source('0'))
    again = basic.production_confirm(db, source('0'), 'production.csv', 'CSV', '2026-10', 'R3', WHEN, preview['review_token'], catalog[0].id)
    assert again['replayed'] and again['planning_version_id'] == identity
    items = list(db.scalars(select(PRDOrderItem).order_by(PRDOrderItem.source_row_number)))
    assert len(items) == 2 and items[0].planned_quantity == 0 and items[0].plant_code == ''
    with pytest.raises(ApplicationError): imported(db, catalog, source('5'))

@pytest.mark.parametrize('quantity', ['-1', 'NaN', '', '1.00001'])
def test_invalid_quantities_never_become_zero(db, catalog, quantity):
    with pytest.raises(ApplicationError):
        basic.production_preview(db, source(quantity), 'production.csv', 'CSV', '2026-10', 'R3', WHEN)
    assert db.scalar(select(PlanningVersion)) is None

def test_duplicates_block_whole_import_and_stale_preview_is_rechecked(db, catalog):
    value = basic.production_preview(db, source(duplicate=True), 'production.csv', 'CSV', '2026-10', 'R3', WHEN)
    assert not value['can_confirm']
    with pytest.raises(ApplicationError):
        basic.production_confirm(db, source(duplicate=True), 'production.csv', 'CSV', '2026-10', 'R3', WHEN, value['review_token'], catalog[0].id)
    value = basic.production_preview(db, source(), 'production.csv', 'CSV', '2026-10', 'R3', WHEN)
    catalog[3].is_active = False; db.commit()
    with pytest.raises(ApplicationError) as failure:
        basic.production_confirm(db, source(), 'production.csv', 'CSV', '2026-10', 'R3', WHEN, value['review_token'], catalog[0].id)
    assert failure.value.code == 'STALE_PRODUCTION_PREVIEW'

def test_two_products_consolidate_once_and_super_admin_approves_central_plan(db, catalog):
    identity, result = calculated(db, catalog)
    assert result.error_count == 0 and result.summary_by_consumable[0].total_calculated_qty == Decimal('230')
    rows = list(db.scalars(select(CalculatedRequirement).order_by(CalculatedRequirement.source_production_qty.desc())))
    assert rows[0].calculated_qty == Decimal('200') and all(row.plant_id is None for row in rows)
    assert rows[0].explanation_payload['production_source']['source_row_number'] == 2
    assert not get_final_requirements(db, planning_version_id=identity)[0].is_fully_confirmed
    with pytest.raises(ApplicationError): approve(db, identity, actor(requirements_update=True))
    reviewer = actor(is_super_admin=True); reviewer.id = catalog[0].id
    assert not approve(db, identity, reviewer)['replayed']
    assert approve(db, identity, reviewer)['replayed']
    final = get_final_requirements(db, planning_version_id=identity)
    assert final[0].final_required_qty == Decimal('230') and final[0].is_fully_confirmed
    assert db.scalar(select(PlantConfirmation)) is None
    assert get_final_requirements(db, planning_version_id=identity, allowed_plant_ids=[uuid4()]) == []
    with pytest.raises(ApplicationError): _assert_plant_access(db, reviewer, None)
    with pytest.raises(ApplicationError):
        basic.calculate(db, CalculationRunRequest(planning_version_id=identity), catalog[0].id)

def test_missing_norm_is_reported_and_blocks_central_approval(db, catalog):
    norm = db.scalar(select(rules.ConsumptionNorm).where(rules.ConsumptionNorm.product_id == catalog[4].id))
    norm.is_active = False; db.commit()
    identity, result = calculated(db, catalog)
    assert result.error_count == 1 and result.status == 'CALCULATED_WITH_ERRORS'
    with pytest.raises(ApplicationError): approve(db, identity, actor(is_super_admin=True))

def test_latest_revision_only_keeps_approved_history(db, catalog):
    identity = approved(db, catalog)
    next_id, _, _ = imported(db, catalog, revision='R4')
    with pytest.raises(ApplicationError) as failure:
        basic.calculate(db, CalculationRunRequest(planning_version_id=identity), catalog[0].id)
    assert failure.value.code == 'LATEST_REVISION_REQUIRED'
    report = projection.report(db, catalog[5].id, identity, datetime(2026,10,30,tzinfo=timezone.utc))
    assert 'LATEST_REVISION_REQUIRED' in [issue.code for issue in report.limitations]

def evidence(db, catalog, identity):
    t0 = datetime(2026,10,15,tzinfo=timezone.utc)
    material, unit = catalog[5], catalog[1]
    inventory.import_source(db, SourceImport(export_id='synthetic-stock', generated_at=t0, import_reason='Verified synthetic usable stock', snapshots=[
        SourceSnapshot(source_snapshot_id='synthetic-snapshot',consumable_id=material.id,unit_id=unit.id,
            usable_quantity='100',as_of=t0,nonusable_excluded=True,reservations_excluded=True)]), catalog[0].id, enabled=True)
    snapshot = db.scalar(select(StockSnapshot))
    data = ProjectionInputs(source_set_id='synthetic-projection',source_reference='Approved dated source',import_reason='Verified reconciliation',
        planning_version_id=identity,stock_snapshot_id=snapshot.id,consumable_id=material.id,unit_id=unit.id,reconciled_as_of=t0,
        coverage_until=t0+timedelta(days=30),reconciliation_reference='Stock/demand/PO reconciliation',
        demand=[{'plant_id':None,'fulfilled_quantity':'0','reserved_quantity':'0','events':[
            {'source_id':'central-demand','at':t0+timedelta(days=2),'quantity':'230'}]}],
        incoming=[{'source_id':'incoming-po','status':'CONFIRMED','scheduled_quantity':'50','received_quantity':'0','cancelled_quantity':'0','available_at':t0+timedelta(days=1)}],
        msl_history=[{'source_id':'approved-msl','effective_at':t0,'quantity':'20','approval_reference':'MSL approval'}])
    projection.import_inputs(db,data,catalog[0].id,enabled=True)
    return t0

def test_central_demand_flows_to_stock_and_existing_purchase_formulas_without_double_count(db, catalog):
    identity=approved(db,catalog);t0=evidence(db,catalog,identity)
    result=projection.report(db,catalog[5].id,identity,t0+timedelta(days=5),'synthetic-projection')
    assert result.status=='COMPLETE' and result.opening_stock==Decimal('100') and result.projected_stock==Decimal('-80')
    assert len(result.requirement_totals)==1 and result.requirement_totals[0].final_quantity==Decimal('230')
    terms={key:{'state':'NOT_APPLICABLE','approval_reference':'Approved synthetic policy'} for key in ('moq','pack_size','order_multiple','max_order_quantity','max_stock_quantity')}
    terms['moq']={'state':'APPLICABLE','value':'120','approval_reference':'Approved synthetic MOQ'}
    terms['pack_size']={'state':'APPLICABLE','value':'25','approval_reference':'Approved synthetic packs'}
    request=PurchaseRequest(consumable_id=catalog[5].id,planning_version_id=identity,source_set_id='synthetic-projection',supplier_id=catalog[6].id,unit_id=catalog[1].id,
        initiated_at=t0+timedelta(days=3),receipt_at=t0+timedelta(days=5),evidence_from=t0,evidence_until=t0+timedelta(days=30),
        target={'quantity':'20','approval_reference':'Approved target'},constraints={**terms,'other_constraints':'CONFIRMED_NONE','other_constraints_reference':'Approved no other terms'},
        lead_time={'supplier_id':catalog[6].id,'approval_reference':'Approved usable lead time','start_event':'ORDER_INITIATED','end_event':'MATERIAL_USABLE','days':2,'basis':'ELAPSED_24_HOUR_DAYS','effective_from':t0,'effective_until':t0+timedelta(days=30)})
    report=purchase_recommendation.report(db,request)
    assert report.status=='RECOMMENDED' and report.raw_quantity==Decimal('100') and report.recommended_quantity==Decimal('125')
    submission=DemandSubmission(submission_key='synthetic-central-demand',reason='Reviewed purchase need',recommendation=request)
    first=purchase_order.submit_demand(db,submission,catalog[0].id)
    assert purchase_order.submit_demand(db,submission,catalog[0].id)['replayed']
    assert first['approval_id']
    missing=request.model_copy(update={'source_set_id':None})
    assert purchase_recommendation.report(db,missing).status=='INCOMPLETE'

def test_grouped_import_retains_exact_company_aliases_without_creating_masters(db,catalog):
    customer=Customer(code='CUST-A',name='Synthetic customer');db.add(customer);db.flush()
    db.add(CustomerAlias(customer_id=customer.id,alias_text='SYNTHETIC',normalized_alias='synthetic'));db.commit()
    book=Workbook();book.active.title='Prd. Order'
    for row in [['KNL',None,None,'Production Order',"Oct'2026"],[None,None,None,'Schedule given on','01.10.2026'],[None,None,None,'Month','01.10.2026'],
        ['S. No','Part No','Item ID','Part Description','R3'],[1,'PART-A','ITEM-A','Synthetic A',100],[None,None,None,'SYNTHETIC - TOTAL',100],
        [None,None,None,'Grand Total',100]]:book.active.append(row)
    stream=BytesIO();book.save(stream)
    result=basic.production_preview(db,stream.getvalue(),'grouped.xlsx','Prd. Order','2026-10',None,WHEN)
    assert result['can_confirm'] and result['rows'][0]['customer_id']==str(customer.id)
    assert len(list(db.scalars(select(Customer))))==1

def test_central_routes_preserve_exact_decimals_and_strict_write_permissions(db,catalog):
    from app.modules.requirements.basic_router import router
    from app.db.session import get_db
    from app.security.dependencies import get_current_user
    identity,_,_=imported(db,catalog)
    identity_user=actor(requirements_read=True)
    app=FastAPI();register_error_handlers(app);app.include_router(router,prefix='/api/v1')
    from app.modules.requirements.router import router as legacy_router
    app.include_router(legacy_router,prefix='/api/v1')
    app.dependency_overrides[get_db]=lambda:db;app.dependency_overrides[get_current_user]=lambda:identity_user
    with TestClient(app) as client:
        response=client.post('/api/v1/requirements/basic/preview',json={'planning_version_id':str(identity),'as_of_date':str(WHEN)})
        assert response.status_code==200 and response.json()['calculations'][0]['calculated_qty']=='200.0000'
        assert client.post('/api/v1/requirements/basic/calculate',json={'planning_version_id':str(identity),'as_of_date':str(WHEN)}).status_code==403
        assert client.post('/api/v1/requirements/calculate',json={'planning_version_id':str(identity),'as_of_date':str(WHEN)}).status_code==403
        identity_user.plant_ids=[uuid4()]
        assert client.get(f'/api/v1/requirements/planning-versions/{identity}').status_code==403


def test_fractional_results_require_approved_rounding_and_preserve_exact_raw_trace(db,catalog):
    identity,_,_=imported(db,catalog)
    norm=db.scalar(select(rules.ConsumptionNorm).where(rules.ConsumptionNorm.product_id==catalog[3].id))
    norm.rule_type='TOOL_LIFE';norm.parameters={'operations_per_unit':'1','tool_life':'3'};db.commit()
    value=basic.preview(db,identity,WHEN)
    assert any(row['code']=='APPROVED_ROUNDING_REQUIRED' for row in value['errors'])
    norm.rounding_policy='ROUND_UP';norm.rounding_precision=4;db.commit()
    basic.calculate(db,CalculationRunRequest(planning_version_id=identity,as_of_date=WHEN),catalog[0].id)
    result=db.scalar(select(CalculatedRequirement).where(CalculatedRequirement.product_id==catalog[3].id))
    assert result.calculated_qty==Decimal('33.3334')
    assert result.explanation_payload['raw_requirement'].startswith('33.333333')


@pytest.mark.parametrize('marker',['-','–','—'])
def test_owner_confirmed_dash_markers_are_zero_not_negative_numbers(marker):
    from app.services.prd_source import parse
    parsed=parse([['Part No','Part Description','Planned Quantity'],['PART-A','Synthetic part',marker]],'2026-10','R0')
    assert parsed[0]['quantity']==0


def test_migration_emits_only_reviewed_postgres_changes_and_refuses_lossy_downgrade():
    import importlib.util
    from pathlib import Path
    from io import StringIO
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[2]/'alembic'/'versions'/'c001_central_basic_planning.py'
    spec=importlib.util.spec_from_file_location('central_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=StringIO();context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(context):module.upgrade()
    sql=output.getvalue()
    assert 'ALTER COLUMN plant_id DROP NOT NULL' in sql and 'planned_quantity >= 0' in sql
    assert 'DELETE' not in sql and 'DROP TABLE' not in sql and 'TRUNCATE' not in sql
    module.op=SimpleNamespace(get_bind=lambda:SimpleNamespace(scalar=lambda _statement:1))
    with pytest.raises(RuntimeError,match='inventing plant assignments'):module.downgrade()
