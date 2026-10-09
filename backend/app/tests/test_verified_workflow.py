"""Synthetic integration examples, not KNL company golden-case approval."""
import io
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import openpyxl
import pytest
from sqlalchemy import select, text
from app.schemas.masters import ProductBulkCreate
from app.services.product import create_products, list_products
from app.tests.test_permission_foundation import db, actor
from app.core.errors import ApplicationError
from app.models.auth import User
from app.models.masters import Product
from app.models.production import Plant, Process, Route, RouteStep
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.inventory_masters import Unit, Consumable
from app.models.prd import PlanningVersion, PRDOrderItem
from app.models.rules import ConsumptionNorm
from app.models.requirements import CalculatedRequirement
from app.schemas.requirements import CalculationRunRequest
from app.services import prd_source, prd_workspace, product_source, stock_source, inventory
from app.services.grn import import_excel_sheet
from app.services.requirements import calculate_planning_version_requirements
from app.services.requirements_workspace import calculate_workspace_requirements
from app.services.requirement_approval import approve
from app.domain.purchase_engine.orders import pending_quantity


def workbook(rows, sheet='Prd. Order'):
    w = openpyxl.Workbook(); w.active.title = sheet
    for row in rows: w.active.append(row)
    buffer = io.BytesIO(); w.save(buffer); return buffer.getvalue()


def revision_rows(latest=0):
    return [['KNL', None, None, 'Production Order', "Aug'2026", "Aug'2026"],
            [None, None, None, 'Schedule given on', '01.08.2026', '23.07.2026'],
            [None, None, None, 'Month', '01.08.2026', '01.08.2026'],
            ['S. No', 'Part No.', 'Item ID', 'Part Description', 'R3', 'R0'],
            [1, 'PART-001', 'ITEM-001', 'Synthetic product', latest, 200]]


def setup_masters(db):
    user = User(username='root', password_hash='synthetic', is_super_admin=True)
    product = Product(code='ITEM-001', item_id='ITEM-001', part_number='PART-001', name='Synthetic product', uom='PCS')
    plant = Plant(name='Verified plant'); process = Process(name='Verified process'); route = Route(name='Verified route')
    unit = Unit(code='KG', name='Kilogram')
    db.add_all([user, product, plant, process, route, unit]); db.flush()
    material = Consumable(code='MAT-001', name='Synthetic material', unit_id=unit.id)
    db.add(material); db.flush()
    db.add_all([ProductPlant(product_id=product.id, plant_id=plant.id, route_id=route.id, is_primary=True),
                RouteStep(route_id=route.id, process_id=process.id, sequence_order=1),
                ProductProcessConsumable(product_id=product.id, process_id=process.id, consumable_id=material.id)])
    db.commit(); return user, product, plant, process, unit, material


def test_latest_revision_keeps_zero_without_old_fallback():
    parsed = prd_source.parse(revision_rows(), '2026-08')
    assert parsed[0]['revision'] == 'R3' and parsed[0]['quantity'] == Decimal('0')


@pytest.mark.parametrize('quantity', [None, -1, 'NaN', '1.00001'])
def test_invalid_latest_quantity_never_becomes_zero(quantity):
    with pytest.raises(ApplicationError):
        prd_source.parse(revision_rows(quantity), '2026-08')


def test_source_preview_is_read_only_and_retains_both_identifiers():
    result = product_source.preview(workbook(revision_rows()), 'source.xlsx', 'Prd. Order')
    assert result['products'][0]['item_id'] == 'ITEM-001'
    assert result['products'][0]['part_number'] == 'PART-001'
    assert result['products'][0]['uom'] == ''


def test_source_conflicting_descriptions_require_explicit_review():
    contents = workbook([['Part No.', 'Item ID', 'Part Description'],
                         ['PART1', 'ITEM1', 'Assembly SFG'],
                         ['PART1', 'ITEM1', 'Assembly']], 'Prd. Order')
    result = product_source.preview(contents, 'source.xlsx', 'Prd. Order')
    assert len(result['products']) == 1
    candidate = result['products'][0]
    assert candidate['name'] == ''
    assert candidate['description_options'] == ['Assembly SFG', 'Assembly']
    assert candidate['source_rows'] == [2, 3]


def test_unmigrated_product_database_returns_actionable_error(db):
    db.execute(text('ALTER TABLE products DROP COLUMN item_id'))
    db.commit()
    batch = ProductBulkCreate(products=[{'code': 'ITEM1', 'name': 'Synthetic product', 'uom': 'PCS'}],
                              source_reference='synthetic-test.xlsx')
    for operation in (lambda: list_products(db), lambda: create_products(db, batch, actor().id)):
        with pytest.raises(ApplicationError) as failure:
            operation()
        assert failure.value.code == 'PRODUCT_DATABASE_SETUP_REQUIRED'
        assert failure.value.status_code == 503
    assert db.scalar(text('SELECT COUNT(*) FROM products')) == 0


def test_import_calculate_approve_preserves_trace_and_history(db):
    user, product, plant, process, unit, material = setup_masters(db)
    # Rate is an explicit synthetic test input, never a production default.
    db.add(ConsumptionNorm(rule_type='PRODUCTION_RATE', consumable_id=material.id, product_id=product.id,
           process_id=process.id, plant_id=plant.id, unit_id=unit.id, parameters={'rate': '0.2500'},
           rounding_policy='NONE', rounding_precision=4, effective_from=date(2026, 1, 1)))
    db.commit()
    prd_workspace.import_prd_excel(db, workbook(revision_rows(20)), 'source.xlsx', 'Prd. Order', user.id,
                                  target_period='2026-08')
    version = db.scalar(select(PlanningVersion))
    assert version.version_number == 3 and version.revision_label == 'R3'
    assert db.scalar(select(PRDOrderItem)).product_id == product.id
    result = calculate_planning_version_requirements(db, CalculationRunRequest(planning_version_id=version.id,
                                                   as_of_date=date(2026, 8, 1)), user.id)
    assert result.error_count == 0
    assert db.scalar(select(CalculatedRequirement)).calculated_qty == Decimal('5.0000')
    rows = calculate_workspace_requirements(db)
    assert rows[0].required_qty == '5.0000' and rows[0].stock_qty == 'Unavailable'
    identity = actor(is_super_admin=True); identity.id = user.id
    assert approve(db, version.id, identity)['status'] == 'APPROVED'
    assert approve(db, version.id, identity)['replayed']
    with pytest.raises(ApplicationError):
        calculate_planning_version_requirements(db, CalculationRunRequest(planning_version_id=version.id), user.id)


def test_missing_norm_is_explicit_not_an_invented_percentage(db):
    user, *_ = setup_masters(db)
    prd_workspace.import_prd_excel(db, workbook(revision_rows(20)), 'source.xlsx', 'Prd. Order', user.id,
                                  target_period='2026-08')
    version = db.scalar(select(PlanningVersion))
    result = calculate_planning_version_requirements(db, CalculationRunRequest(planning_version_id=version.id), user.id)
    assert result.error_count == 1
    assert db.scalar(select(CalculatedRequirement)) is None
    assert calculate_workspace_requirements(db)[0].status == 'Configuration required'
    with pytest.raises(ApplicationError):
        approve(db, version.id, actor(is_super_admin=True))


def test_stock_statement_latest_snapshot_and_duplicate_protection(db):
    user, product, plant, process, unit, material = setup_masters(db)
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    for days, quantity in ((1, '100.0000'), (0, '180.0000')):
        cutoff = now - timedelta(days=days)
        data = stock_source.preview(db, workbook([['Item ID', 'Unit', 'Closing'], ['MAT-001', 'KG', quantity]], 'Stock'),
            'stock.xlsx', 'Stock', as_of=cutoff, generated_at=cutoff, exclusions_confirmed=True)
        assert not inventory.import_source(db, data, user.id, enabled=True).replayed
        assert inventory.import_source(db, data, user.id, enabled=True).replayed
    assert inventory.get_balance(db, material.id).usable_quantity == Decimal('180.0000')


def test_billed_quantity_cannot_fulfil_po():
    # Ordered 200, physical receipt 200, rejected 20 => accepted 180; billed 200 is irrelevant.
    assert pending_quantity(Decimal('200'), Decimal('0'), Decimal('180')) == Decimal('20')


def test_grn_ordered_and_billed_columns_cannot_substitute_for_actual_receipt(db):
    contents = workbook([['Part No.', 'Item ID', 'Description', 'Unit', 'Order Qty', 'GRN. Qty', 'Rejected Qty', 'Billed Qty'],
                         ['PART1', 'ITEM1', 'Synthetic material', 'KG', 200, 200, 20, 200]], 'GRN')
    with pytest.raises(ApplicationError) as error:
        import_excel_sheet(db, contents, 'grn.xlsx', 'GRN', actor().id)
    assert error.value.code == 'ACTUAL_RECEIPT_REQUIRED'
