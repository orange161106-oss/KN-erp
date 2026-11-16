import math
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from app.db.base import Base
from app.domain.purchase_engine.monthly import calculate_monthly_purchase
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Process
from app.models.prd import PlanningVersion, ImportBatch, PRDOrderHeader, PRDOrderItem
from app.models.rules import ConsumptionNorm
from app.models.requirements import CalculatedRequirement
from app.models.stock_statements import (
    StockParameter,
    StockParameterBatch,
    StockStatementBatch,
    StockStatementLine,
)
from app.models.requirement_requests import RequirementRequestBatch, RequirementRequest
from app.services.monthly_purchase import MonthlyPurchaseInputs
from app.services.purchase_workspace import list_purchase_workspace


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.create_function("btrim", 1, lambda v: v.strip() if v else "")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    u_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
    u_kgs = Unit(id=uuid4(), code="KGS", name="Kilograms")
    session.add_all([u_nos, u_kgs])
    session.flush()

    user = User(id=uuid4(), username="admin", password_hash="pw", is_super_admin=True)
    session.add(user)
    session.flush()

    yield session

    session.close()
    engine.dispose()


def _setup_month(db, month=10, year=2026):
    user = db.query(User).first()
    version = PlanningVersion(
        id=uuid4(),
        planning_period=f"{year:04d}-{month:02d}",
        version_number=1,
        revision_label="R0",
        status="APPROVED",
        source_filename="Plan_Oct.xlsx",
        created_by=user.id,
    )
    db.add(version)
    db.flush()

    ib = ImportBatch(
        id=uuid4(),
        planning_version_id=version.id,
        filename="Plan_Oct.xlsx",
        file_size_bytes=1024,
        validation_summary={"workflow": "BASIC_CENTRAL_V1"},
        uploaded_by=user.id,
        status="PROMOTED",
    )
    db.add(ib)
    db.flush()

    # Prev month stock statement
    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    st_batch = StockStatementBatch(
        id=uuid4(),
        statement_month=prev_month,
        statement_year=prev_year,
        statement_date=date(prev_year, prev_month, 30),
        source_filename="Opening_Stock.xlsx",
        file_hash="dummy_hash_st",
        status="active",
        uploaded_by=user.id,
    )
    db.add(st_batch)
    db.flush()

    # Parameter batch
    p_batch = StockParameterBatch(
        id=uuid4(),
        month=month,
        year=year,
        effective_date=date(year, month, 1),
        source_filename="Stockmgmt.xlsx",
        file_hash="dummy_hash_param",
        status="active",
        summary={"working_days": 27, "msl_days": 10},
        uploaded_by=user.id,
    )
    db.add(p_batch)
    db.flush()

    req_batch = RequirementRequestBatch(
        id=uuid4(),
        planning_month=month,
        planning_year=year,
        source_type="PLANT",
        source_code="P1",
        source_filename="Requests_Oct.xlsx",
        file_hash="dummy_hash_req",
        status="ACTIVE",
        uploaded_by=user.id,
    )
    db.add(req_batch)
    db.flush()

    return version, ib, st_batch, p_batch, req_batch


def _add_production_demand(db, version, ib, consumable, operations_qty, unit, tool_life=1):
    prod = Product(id=uuid4(), code=f"PROD_{consumable.item_id}", name="Test Product", uom="PCS")
    proc = Process(id=uuid4(), name=f"PROC_{consumable.item_id}")
    db.add_all([prod, proc])
    db.flush()

    header = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=version.id,
        import_batch_id=ib.id,
        planning_period=version.planning_period,
    )
    db.add(header)
    db.flush()

    item = PRDOrderItem(
        id=uuid4(),
        planning_version_id=version.id,
        header_id=header.id,
        source_row_number=1,
        product_code=prod.code,
        product_id=prod.id,
        plant_code="P1",
        planned_quantity=Decimal("100"),
        uom="PCS",
        target_period=version.planning_period,
    )
    db.add(item)
    db.flush()

    norm = ConsumptionNorm(
        id=uuid4(),
        consumable_id=consumable.id,
        rule_type="TOOL_LIFE" if tool_life and tool_life > 1 else "PRODUCTION_RATE",
        parameters={"tool_life": tool_life} if tool_life else {},
        unit_id=unit.id,
    )
    db.add(norm)
    db.flush()

    calc = CalculatedRequirement(
        id=uuid4(),
        planning_version_id=version.id,
        prd_order_item_id=item.id,
        product_id=prod.id,
        process_id=proc.id,
        consumable_id=consumable.id,
        rule_id=norm.id,
        rule_type="TOOL_LIFE" if tool_life and tool_life > 1 else "PRODUCTION_RATE",
        rule_version=1,
        parameters={"tool_life": tool_life} if tool_life else {},
        source_production_qty=Decimal("100"),
        raw_requirement=operations_qty,
        rounding_policy="CEIL",
        rounding_precision=0,
        calculated_qty=operations_qty,
        calculation_steps=[],
        explanation_payload={},
        unit_id=unit.id,
        uom=unit.code,
    )
    db.add(calc)
    db.flush()


# 1. TOOL_LIFE item: AAC100001QC
def test_1_tool_life_item_aac100001qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="AAC100001QC",
        name="Plug tap-IS II M2 M5X0.8mm 6G",
        category="Production consumables",
        type_of_material="Cutting Tools",
        rule_type="TOOL_LIFE",
        output_per_unit=Decimal("2000.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("246.00"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="AAC100001QC",
        min_order_qty=Decimal("10.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="AAC100001QC",
        closing_qty=Decimal("17.0000"),
        unit="NOS",
    )
    db.add_all([param, line])
    db.flush()

    _add_production_demand(db, version, ib, c, Decimal("5550.0000"), u_nos, tool_life=2000)
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "AAC100001QC")

    assert rec.required_qty == Decimal("3.0000")
    # MSL = CEILING(3 / (27/10)) = CEILING(1.1111) = 2
    assert rec.minimum_stock_level == Decimal("2.0000")
    assert rec.stock_qty == Decimal("17.0000")
    # Shortage = 2 + 3 - 17 = -12 <= 0 -> order 0
    assert rec.system_recommended_qty == Decimal("0.0000")


# 2. Direct plant request item: ABB100011QC (Welding wire)
def test_2_direct_plant_request_item_abb100011qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_kgs = db.query(Unit).filter_by(code="KGS").first()

    c = Consumable(
        id=uuid4(),
        item_id="ABB100011QC",
        name="Welding Wires Pail Pack",
        category="Production consumables",
        type_of_material="Welding Wires",
        rule_type="DIRECT",
        output_per_unit=Decimal("15.0000"),  # Informational pack size
        purchasing_unit="KGS",
        unit_id=u_kgs.id,
        rate=Decimal("120.00"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="ABB100011QC",
        min_order_qty=Decimal("250.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="ABB100011QC",
        closing_qty=Decimal("3595.0000"),
        unit="KGS",
    )
    # Direct plant request: Plant 5 requests 4100 kgs
    req = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P5",
        quantity=Decimal("4100.0000"),
        unit="KGS",
        status="ACTIVE",
    )
    db.add_all([param, line, req])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "ABB100011QC")

    # Direct request MUST NOT be divided by 15!
    assert rec.required_qty == Decimal("4100.0000")
    # MSL: 15-day policy for ABB... -> CEILING(4100 / (27/15)) = 2278
    assert rec.minimum_stock_level == Decimal("2278.0000")
    assert rec.stock_qty == Decimal("3595.0000")
    # Shortage = 2278 + 4100 - 3595 = 2783
    assert rec.system_recommended_qty == Decimal("2783.0000")


# 3. Stationery item previously zeroed: PEQ000075QC
def test_3_stationery_item_peq000075qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="PEQ000075QC",
        name="Under Process Tag",
        category="Stationary",
        type_of_material="Printed Items",
        rule_type="DIRECT",
        output_per_unit=None,  # Missing output per unit
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("1.50"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="PEQ000075QC",
        min_order_qty=Decimal("500.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="PEQ000075QC",
        closing_qty=Decimal("1800.0000"),
        unit="NOS",
    )
    req = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="DEPARTMENT",
        source_code="TOOL_ROOM",
        quantity=Decimal("1900.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    db.add_all([param, line, req])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "PEQ000075QC")

    # MUST NOT be zeroed out!
    assert rec.status != "OUTPUT_PER_UNIT_MISSING"
    assert rec.required_qty == Decimal("1900.0000")
    # MSL = CEILING(1900 / (27/10)) = 704
    assert rec.minimum_stock_level == Decimal("704.0000")
    assert rec.stock_qty == Decimal("1800.0000")
    # Order = 704 + 1900 - 1800 = 804
    assert rec.system_recommended_qty == Decimal("804.0000")


# 4. Chemical / area coverage item: AFE000001QC
def test_4_chemical_item_afe000001qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_kgs = db.query(Unit).filter_by(code="KGS").first()

    c = Consumable(
        id=uuid4(),
        item_id="AFE000001QC",
        name="Powder -Glossy Black PP jet",
        category="Powder coating Consumables",
        type_of_material="Powders",
        rule_type="AREA_COVERAGE",
        output_per_unit=Decimal("100.0000"),
        purchasing_unit="KGS",
        unit_id=u_kgs.id,
        rate=Decimal("250.00"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="AFE000001QC",
        min_order_qty=Decimal("20.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="AFE000001QC",
        closing_qty=Decimal("300.0000"),
        unit="KGS",
    )
    req = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P4",
        quantity=Decimal("1735.0000"),
        unit="KGS",
        status="ACTIVE",
    )
    db.add_all([param, line, req])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "AFE000001QC")

    assert rec.required_qty == Decimal("1735.0000")
    # MSL: CEILING(1735 / (27/10)) = 643
    assert rec.minimum_stock_level == Decimal("643.0000")
    assert rec.stock_qty == Decimal("300.0000")
    # Order = 643 + 1735 - 300 = 2078
    assert rec.system_recommended_qty == Decimal("2078.0000")


# 5. Packaging item: NBQ000032QC
def test_5_packaging_item_nbq000032qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="NBQ000032QC",
        name="Plastic Cap Dia 30mm",
        category="Production consumables",
        type_of_material="Packing Items",
        rule_type="PRODUCTION_RATE",
        output_per_unit=Decimal("1.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("2.00"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="NBQ000032QC",
        min_order_qty=Decimal("1000.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="NBQ000032QC",
        closing_qty=Decimal("7000.0000"),
        unit="NOS",
    )
    req = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P2",
        quantity=Decimal("4782.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    db.add_all([param, line, req])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "NBQ000032QC")

    assert rec.required_qty == Decimal("4782.0000")
    # MSL = CEILING(4782 / (27/10)) = 1772
    assert rec.minimum_stock_level == Decimal("1772.0000")
    assert rec.stock_qty == Decimal("7000.0000")
    # Gap = 1772 + 4782 - 7000 = -446 <= 0 -> Order 0
    assert rec.system_recommended_qty == Decimal("0.0000")


# 6. Spray item: GAQ000078QC
def test_6_spray_item_gaq000078qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="GAQ000078QC",
        name="Pvc Strapping",
        category="Production consumables",
        type_of_material="Packing Items",
        rule_type="DIRECT",
        output_per_unit=Decimal("1.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("350.00"),
    )
    db.add(c)
    db.flush()

    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="GAQ000078QC",
        closing_qty=Decimal("16.0000"),
        unit="NOS",
    )
    req = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P1",
        quantity=Decimal("4.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="GAQ000078QC",
        min_order_qty=Decimal("0.0000"),
    )
    db.add_all([param, line, req])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "GAQ000078QC")

    assert rec.required_qty == Decimal("4.0000")
    # MSL = CEILING(4 / (27/10)) = 2
    assert rec.minimum_stock_level == Decimal("2.0000")
    # Gap = 2 + 4 - 16 = -10 <= 0 -> Order 0
    assert rec.system_recommended_qty == Decimal("0.0000")


# 7. Machine tool: BAA110116QC
def test_7_machine_tool_baa110116qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="BAA110116QC",
        name="HSS Drill bit Dia:4.2mm",
        category="Production consumables",
        type_of_material="Cutting Tools",
        rule_type="TOOL_LIFE",
        output_per_unit=Decimal("840.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("95.00"),
    )
    db.add(c)
    db.flush()

    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="BAA110116QC",
        min_order_qty=Decimal("5.0000"),
    )
    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="BAA110116QC",
        closing_qty=Decimal("34.0000"),
        unit="NOS",
    )
    db.add_all([param, line])
    db.flush()

    # Production operations = 38160 -> 38160 / 840 = 45.4285 -> CEILING = 46
    _add_production_demand(db, version, ib, c, Decimal("38160.0000"), u_nos, tool_life=840)
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "BAA110116QC")

    assert rec.required_qty == Decimal("46.0000")
    # MSL = CEILING(46 / (27/10)) = 18
    assert rec.minimum_stock_level == Decimal("18.0000")
    assert rec.stock_qty == Decimal("34.0000")
    # Order = 18 + 46 - 34 = 30
    assert rec.system_recommended_qty == Decimal("30.0000")


# 8. Integer ceiling MSL and Order quantity: AAC100017QC
def test_8_tool_aac100017qc(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="AAC100017QC",
        name="Tap Set-M5 x 0.8mm",
        category="TFJ",
        type_of_material="TFJ Maint items",
        rule_type="TOOL_LIFE",
        output_per_unit=Decimal("1.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("150.00"),
    )
    db.add(c)
    db.flush()

    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="AAC100017QC",
        closing_qty=Decimal("0.0000"),
        unit="NOS",
    )
    req1 = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P2",
        quantity=Decimal("10.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    req2 = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="DEPARTMENT",
        source_code="TOOL_ROOM",
        quantity=Decimal("1.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="AAC100017QC",
        min_order_qty=Decimal("1.0000"),
    )
    db.add_all([param, line, req1, req2])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "AAC100017QC")

    assert rec.required_qty == Decimal("11.0000")
    # MSL = CEILING(11 / (27/10)) = CEILING(4.0741) = 5 (NOT 4.0741!)
    assert rec.minimum_stock_level == Decimal("5.0000")
    assert rec.stock_qty == Decimal("0.0000")
    # Order = 5 + 11 - 0 = 16
    assert rec.system_recommended_qty == Decimal("16.0000")


# 9. Zero-stock vs missing-stock behavior
def test_9_zero_stock_vs_missing_stock_behavior(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="ITEM_TEST_STOCK",
        name="Test Stock Item",
        category="General",
        type_of_material="General",
        rule_type="DIRECT",
        output_per_unit=None,
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("10.00"),
    )
    param = StockParameter(
        id=uuid4(),
        batch_id=p_batch.id,
        item_id="ITEM_TEST_STOCK",
        min_order_qty=Decimal("10.0000"),
    )
    db.add_all([c, param])
    db.commit()

    # Case A: treat_missing_as_zero=False -> Item missing from stock statement raises issue
    inputs_strict = MonthlyPurchaseInputs(db, month=10, year=2026, material_ids={c.id}, treat_missing_as_zero=False)
    calc_strict = inputs_strict.calculate(material_id=c.id, unit_id=u_nos.id, uom="NOS", required=Decimal("100.0000"))
    assert calc_strict["recommended_quantity"] is None
    assert any("missing from the" in issue for issue in calc_strict["input_issues"])

    # Case B: treat_missing_as_zero=True -> Missing item is treated as zero stock
    inputs_zero = MonthlyPurchaseInputs(db, month=10, year=2026, material_ids={c.id}, treat_missing_as_zero=True)
    calc_zero = inputs_zero.calculate(material_id=c.id, unit_id=u_nos.id, uom="NOS", required=Decimal("100.0000"))
    assert calc_zero["stock_qty"] == Decimal("0")
    assert calc_zero["recommended_quantity"] is not None


# 10. Integer ceiling vs fractional MSL
def test_10_integer_ceiling_vs_fractional_msl(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="ITEM_MSL_ROUND",
        name="Test MSL Rounding",
        category="General",
        type_of_material="General",
        rule_type="DIRECT",
        purchasing_unit="NOS",
        unit_id=u_nos.id,
    )
    db.add(c)
    db.commit()

    inputs = MonthlyPurchaseInputs(db, month=10, year=2026, material_ids={c.id}, treat_missing_as_zero=True)
    # Required = 1900. 1900 / (27/10) = 703.703703...
    res = inputs.calculate(material_id=c.id, unit_id=u_nos.id, uom="NOS", required=Decimal("1900.0000"))
    assert res["minimum_stock_level"] == Decimal("704.0000")


# 11. MOQ enforcement: Order Qty = IF(Net Need > 0, MAX(Net Need, MOQ), 0)
def test_11_moq_enforcement():
    # User Case 1: Net Need = 30, MOQ = 50 -> Order Qty = 50
    # MSL=10, Req=30, Stock=10 -> Net Need = 10 + 30 - 10 = 30
    res1 = calculate_monthly_purchase(
        required=Decimal("30.0000"),
        closing_stock=Decimal("10.0000"),
        msl=Decimal("10.0000"),
        moq=Decimal("50.0000"),
        rate=Decimal("10.00"),
    )
    assert res1["raw_quantity"] == Decimal("30.0000")
    assert res1["recommended_quantity"] == Decimal("50.0000")
    assert res1["purchase_value"] == Decimal("500.00")

    # User Case 2: Net Need = 120, MOQ = 50 -> Order Qty = 120 (NOT CEILING(120/50)*50 = 150)
    # MSL=20, Req=120, Stock=20 -> Net Need = 20 + 120 - 20 = 120
    res2 = calculate_monthly_purchase(
        required=Decimal("120.0000"),
        closing_stock=Decimal("20.0000"),
        msl=Decimal("20.0000"),
        moq=Decimal("50.0000"),
        rate=Decimal("10.00"),
    )
    assert res2["raw_quantity"] == Decimal("120.0000")
    assert res2["recommended_quantity"] == Decimal("120.0000")
    assert res2["recommended_quantity"] != Decimal("150.0000")
    assert res2["purchase_value"] == Decimal("1200.00")

    # User Case 3: Net Need = 200, MOQ = 50 -> Order Qty = 200
    # MSL=50, Req=200, Stock=50 -> Net Need = 50 + 200 - 50 = 200
    res3 = calculate_monthly_purchase(
        required=Decimal("200.0000"),
        closing_stock=Decimal("50.0000"),
        msl=Decimal("50.0000"),
        moq=Decimal("50.0000"),
        rate=Decimal("10.00"),
    )
    assert res3["raw_quantity"] == Decimal("200.0000")
    assert res3["recommended_quantity"] == Decimal("200.0000")
    assert res3["purchase_value"] == Decimal("2000.00")

    # User Case 4: Net Need = 0, MOQ = 50 -> Order Qty = 0 (MOQ does NOT trigger an order)
    # MSL=10, Req=20, Stock=30 -> Net Need = 10 + 20 - 30 = 0
    res4 = calculate_monthly_purchase(
        required=Decimal("20.0000"),
        closing_stock=Decimal("30.0000"),
        msl=Decimal("10.0000"),
        moq=Decimal("50.0000"),
        rate=Decimal("10.00"),
    )
    assert res4["raw_quantity"] == Decimal("0.0000")
    assert res4["recommended_quantity"] == Decimal("0.0000")
    assert res4["purchase_value"] is None or res4["purchase_value"] == Decimal("0.00")

    # Edge Case: Net Need < 0 (Over-stocked), MOQ = 50 -> Order Qty = 0
    res5 = calculate_monthly_purchase(
        required=Decimal("10.0000"),
        closing_stock=Decimal("50.0000"),
        msl=Decimal("5.0000"),
        moq=Decimal("50.0000"),
        rate=Decimal("10.00"),
    )
    assert res5["raw_quantity"] == Decimal("-35.0000")
    assert res5["recommended_quantity"] == Decimal("0.0000")


# 12. Multi-source demand consolidation
def test_12_multisource_demand_consolidation(db):
    version, ib, st_batch, p_batch, req_batch = _setup_month(db)
    u_nos = db.query(Unit).filter_by(code="NOS").first()

    c = Consumable(
        id=uuid4(),
        item_id="MULTI_SOURCE_ITEM",
        name="Multi Source Consumable",
        category="Production consumables",
        type_of_material="Cutting Tools",
        rule_type="TOOL_LIFE",
        output_per_unit=Decimal("100.0000"),
        purchasing_unit="NOS",
        unit_id=u_nos.id,
        rate=Decimal("50.00"),
    )
    db.add(c)
    db.flush()

    line = StockStatementLine(
        id=uuid4(),
        batch_id=st_batch.id,
        item_id="MULTI_SOURCE_ITEM",
        closing_qty=Decimal("10.0000"),
        unit="NOS",
    )
    db.add(line)
    db.flush()

    # Source A: Production ops = 1000 -> 1000 / 100 = 10 units
    _add_production_demand(db, version, ib, c, Decimal("1000.0000"), u_nos, tool_life=100)

    # Source B: Plant requests = 20 units
    req_plant = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="PLANT",
        source_code="P1",
        quantity=Decimal("20.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    # Source C: Dept requests = 5 units
    req_dept = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="DEPARTMENT",
        source_code="PMD",
        quantity=Decimal("5.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    # Source D: Auxiliary demand = 15 units
    req_aux = RequirementRequest(
        id=uuid4(),
        import_batch_id=req_batch.id,
        consumable_id=c.id,
        planning_month=10,
        planning_year=2026,
        source_type="AUXILIARY",
        source_code="POWDER_COATING",
        quantity=Decimal("15.0000"),
        unit="NOS",
        status="ACTIVE",
    )
    db.add_all([req_plant, req_dept, req_aux])
    db.commit()

    resp = list_purchase_workspace(db, month=10, year=2026, show_all=True)
    rec = next(r for r in resp.records if r.consumable_code == "MULTI_SOURCE_ITEM")

    # Production (10) + Plant (20) + Dept (5) + Aux (15) = 50
    assert rec.required_qty == Decimal("50.0000")
    assert rec.demand_source_type == "PRODUCTION_AND_REQUEST"
