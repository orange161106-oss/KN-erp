import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.auth import User, Role
from app.models.inventory_masters import Consumable, Unit
from app.models.prd import PlanningVersion, ImportBatch
from app.models.requirements import CalculatedRequirement
from app.models.stock_statements import StockStatementBatch, StockStatementLine, StockParameterBatch, StockParameter
from app.models.requirement_requests import RequirementRequestBatch, RequirementRequest
from app.services.purchase_workspace import list_purchase_workspace, export_purchase_workspace_excel
from app.services.requirements_workspace import load_workspace_view, export_requirements_excel
from app.services.requirement_requests import get_active_requirement_requests_map


from sqlalchemy import event

@pytest.fixture
def mem_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.create_function('btrim', 1, lambda v: v.strip() if v else '')
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    # Seed unit and version
    u_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
    u_kgs = Unit(id=uuid4(), code="KGS", name="Kilograms")
    u_ltrs = Unit(id=uuid4(), code="LTRS", name="Liters")
    session.add_all([u_nos, u_kgs, u_ltrs])
    session.flush()

    user = User(id=uuid4(), username="admin", password_hash="pw", is_super_admin=True)
    session.add(user)
    session.flush()

    version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        revision_label="R0",
        status="DRAFT",
        source_filename="Plan_Oct.xlsx",
        created_by=user.id,
    )
    session.add(version)
    session.flush()

    ib = ImportBatch(
        id=uuid4(),
        planning_version_id=version.id,
        filename="Plan_Oct.xlsx",
        file_size_bytes=1024,
        validation_summary={"workflow": "BASIC_CENTRAL_V1"},
        uploaded_by=user.id,
        status="PROMOTED",
    )
    session.add(ib)
    session.flush()

    # Consumables
    c_gloves = Consumable(id=uuid4(), item_id="ABK100003QC", name='Gloves - Knitted - 12"', unit_id=u_nos.id, purchasing_unit="Nos", is_active=True)
    c_tag = Consumable(id=uuid4(), item_id="PEQ000001QC", name="Accepted Tag", unit_id=u_nos.id, purchasing_unit="NOS", is_active=True)
    c_soap = Consumable(id=uuid4(), item_id="FDQ000003QC", name="Soap oil", unit_id=u_ltrs.id, purchasing_unit="Ltrs.", is_active=True)
    c_anabond = Consumable(id=uuid4(), item_id="BBG000090QC", name="Anabond - 202", unit_id=u_nos.id, purchasing_unit="NOS", rule_type="TOOL_LIFE", output_per_unit=Decimal("1"), is_active=True)
    c_cotton = Consumable(id=uuid4(), item_id="GAQ000023QC", name="Cotton Waste Big Size", unit_id=u_kgs.id, purchasing_unit="kgs.", is_active=True)
    session.add_all([c_gloves, c_tag, c_soap, c_anabond, c_cotton])

    # Stock statement for 2026-09
    stk_batch = StockStatementBatch(id=uuid4(), statement_month=9, statement_year=2026, statement_date=date(2026, 9, 30), file_hash="dummy_hash_stk", status="active", source_filename="Stock_Sep26.xlsx")
    session.add(stk_batch)
    session.add(StockStatementLine(id=uuid4(), batch_id=stk_batch.id, item_id="ABK100003QC", item_description='Gloves', unit="SETS", closing_qty=Decimal("345.0000"), item_class="CONSUMABLE"))
    session.add(StockStatementLine(id=uuid4(), batch_id=stk_batch.id, item_id="PEQ000001QC", item_description="Tag", unit="NOS", closing_qty=Decimal("4180.0000"), item_class="CONSUMABLE"))
    session.add(StockStatementLine(id=uuid4(), batch_id=stk_batch.id, item_id="FDQ000003QC", item_description="Soap oil", unit="LTRS", closing_qty=Decimal("2450.0000"), item_class="CONSUMABLE"))
    session.add(StockStatementLine(id=uuid4(), batch_id=stk_batch.id, item_id="BBG000090QC", item_description="Anabond", unit="NOS", closing_qty=Decimal("2.0000"), item_class="CONSUMABLE"))
    session.add(StockStatementLine(id=uuid4(), batch_id=stk_batch.id, item_id="GAQ000023QC", item_description="Cotton", unit="KGS", closing_qty=Decimal("0.0000"), item_class="CONSUMABLE"))

    # Stock parameter for 2026-10
    param_batch = StockParameterBatch(id=uuid4(), month=10, year=2026, effective_date=date(2026, 10, 1), file_hash="dummy_hash_param", status="active", summary={"working_days": 27, "msl_days": 10}, source_filename="Stock_Param.xlsx")
    session.add(param_batch)
    session.add(StockParameter(id=uuid4(), batch_id=param_batch.id, item_id="ABK100003QC", min_order_qty=Decimal("500.0000")))
    session.add(StockParameter(id=uuid4(), batch_id=param_batch.id, item_id="PEQ000001QC", min_order_qty=Decimal("500.0000")))
    session.add(StockParameter(id=uuid4(), batch_id=param_batch.id, item_id="FDQ000003QC", min_order_qty=Decimal("35.0000")))
    session.add(StockParameter(id=uuid4(), batch_id=param_batch.id, item_id="BBG000090QC", min_order_qty=Decimal("1.0000")))
    session.add(StockParameter(id=uuid4(), batch_id=param_batch.id, item_id="GAQ000023QC", min_order_qty=Decimal("10.0000")))

    # Requirement Requests for October 2026
    req_batch = RequirementRequestBatch(id=uuid4(), planning_month=10, planning_year=2026, source_type="PLANT", source_code="P2", status="ACTIVE", source_filename="Plan_Oct.xlsx", file_hash="dummy_hash")
    session.add(req_batch)

    # T1: Gloves: P2=2400, P3=800, P4=2820, P5=1800, TOOL=120, PMD=150, SALES=150, NPD=200, HRD=100, QAD=630
    gloves_sources = [
        ("P2", Decimal("2400"), "NOS"), ("P3", Decimal("800"), "NOS"), ("P4", Decimal("2820"), "NOS"),
        ("P5", Decimal("1800"), "NOS"), ("TOOL_ROOM", Decimal("120"), "NOS"), ("PMD", Decimal("150"), "NOS"),
        ("SALES", Decimal("150"), "Sets"), ("NPD", Decimal("200"), "SETS"), ("HRD", Decimal("100"), "Sets"),
        ("QAD", Decimal("630"), "NOS")
    ]
    for src, qty, u in gloves_sources:
        session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT" if src not in ("P1","P2","P3","P4","P5") else "PLANT", source_code=src, consumable_id=c_gloves.id, quantity=qty, unit=u, import_batch_id=req_batch.id, status="ACTIVE"))

    # T2: PEQ000001QC: QAD=2100
    session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT", source_code="QAD", consumable_id=c_tag.id, quantity=Decimal("2100"), unit="NOS", import_batch_id=req_batch.id, status="ACTIVE"))

    # T3: FDQ000003QC: HRD=910
    session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT", source_code="HRD", consumable_id=c_soap.id, quantity=Decimal("910"), unit="Ltrs.", import_batch_id=req_batch.id, status="ACTIVE"))

    # T4: BBG000090QC: TOOL_ROOM=2, PMD=2
    session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT", source_code="TOOL_ROOM", consumable_id=c_anabond.id, quantity=Decimal("2"), unit="NOS", import_batch_id=req_batch.id, status="ACTIVE"))
    session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT", source_code="PMD", consumable_id=c_anabond.id, quantity=Decimal("2"), unit="NOS", import_batch_id=req_batch.id, status="ACTIVE"))

    # T5: GAQ000023QC: TOOL_ROOM=10, PMD=11, SALES=20, HRD=1, P3=15, P4=10 = 67
    t5_sources = [("TOOL_ROOM", Decimal("10")), ("PMD", Decimal("11")), ("SALES", Decimal("20")), ("HRD", Decimal("1")), ("P3", Decimal("15")), ("P4", Decimal("10"))]
    for src, qty in t5_sources:
        session.add(RequirementRequest(id=uuid4(), planning_month=10, planning_year=2026, source_type="DEPARTMENT" if src not in ("P1","P2","P3","P4","P5") else "PLANT", source_code=src, consumable_id=c_cotton.id, quantity=qty, unit="kgs.", import_batch_id=req_batch.id, status="ACTIVE"))

    session.commit()
    yield session
    session.close()


def test_t1_t5_acceptance_tests(mem_db):
    pw = list_purchase_workspace(mem_db, month=10, year=2026, show_all=True)
    records = {r.consumable_code: r for r in pw.records}

    # T1 ABK100003QC
    g = records["ABK100003QC"]
    assert g.total_requirement_qty == Decimal("9170.0000")
    assert g.stock_qty == Decimal("345.0000")
    assert round(g.minimum_stock_level, 1) == Decimal("3396.3")
    assert g.minimum_order_qty == Decimal("500.0000")
    assert round(g.system_recommended_qty, 1) == Decimal("12221.3")
    assert g.unit_conflict is True
    assert "Sets" in g.unit_conflict_details

    # T2 PEQ000001QC
    tag = records["PEQ000001QC"]
    assert tag.qad_qty == Decimal("2100.0000")
    assert tag.total_requirement_qty == Decimal("2100.0000")
    assert tag.stock_qty == Decimal("4180.0000")
    assert round(tag.minimum_stock_level, 0) == Decimal("778")
    assert tag.system_recommended_qty == Decimal("0.0000")

    # T3 FDQ000003QC
    soap = records["FDQ000003QC"]
    assert soap.hrd_qty == Decimal("910.0000")
    assert soap.total_requirement_qty == Decimal("910.0000")
    assert soap.stock_qty == Decimal("2450.0000")
    assert round(soap.minimum_stock_level, 0) == Decimal("337")
    assert soap.system_recommended_qty == Decimal("0.0000")

    # T4 BBG000090QC
    ana = records["BBG000090QC"]
    assert ana.tool_room_qty == Decimal("2.0000")
    assert ana.pmd_qty == Decimal("2.0000")
    assert ana.total_requirement_qty == Decimal("4.0000")
    assert ana.stock_qty == Decimal("2.0000")
    assert ana.minimum_stock_level == Decimal("2.0000")
    assert ana.system_recommended_qty == Decimal("4.0000")

    # T5 GAQ000023QC
    cot = records["GAQ000023QC"]
    assert cot.total_requirement_qty == Decimal("67.0000")
    assert cot.stock_qty == Decimal("0.0000")
    assert round(cot.minimum_stock_level, 1) == Decimal("24.8")
    assert cot.minimum_order_qty == Decimal("10.0000")
    assert round(cot.system_recommended_qty, 1) == Decimal("91.8")


def test_t9_per_source_sum_equals_total(mem_db):
    pw = list_purchase_workspace(mem_db, month=10, year=2026, show_all=True)
    for r in pw.records:
        part_sum = (
            r.production_qty + r.plant_1_qty + r.plant_2_qty + r.plant_3_qty + r.plant_4_qty + r.plant_5_qty
            + r.tool_room_qty + r.pmd_qty + r.sales_qty + r.npd_qty + r.hrd_qty + r.qad_qty
        )
        assert part_sum == r.total_requirement_qty


def test_t11_api_and_export_consistency(mem_db):
    pw = list_purchase_workspace(mem_db, month=10, year=2026, show_all=True)
    excel_bytes = export_purchase_workspace_excel(mem_db, month=10, year=2026, show_all=True)
    assert len(excel_bytes) > 1000

    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb.active
    # Row 4 is header, row 5+ is data
    for r_idx, r in enumerate(pw.records[:20], 5):
        # Cell values
        item_id = ws.cell(r_idx, 3).value if ws.title != "Purchase Recommendations" else ws.cell(r_idx, 1).value
        assert item_id == r.consumable_code


def test_t12_scope_filtering_and_counts(mem_db):
    pw_default = list_purchase_workspace(mem_db, month=10, year=2026, show_all=False)
    pw_all = list_purchase_workspace(mem_db, month=10, year=2026, show_all=True)

    assert pw_default.total_items_count == 5
    assert pw_default.listed_items_count == len(pw_default.records)
    assert pw_all.total_items_count == 5
    assert pw_all.listed_items_count == 5
