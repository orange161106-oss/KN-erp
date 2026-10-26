"""Automated test suite verifying departmental and maintenance consumable planning (Tool Room, PMD, NPD, HRD, QAD, Accounts, Sales)."""
from datetime import date, datetime, timezone
from decimal import Decimal
import io
from uuid import uuid4

import openpyxl
import pytest
from sqlalchemy import select

from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.prd import PlanningVersion
from app.models.production import Plant
from app.models.requirements import MonthlyRequirementRecord
from app.models.stock_statements import StockStatementBatch, StockStatementLine
from app.services.purchase_workspace import (
    export_purchase_workspace_excel,
    list_purchase_workspace,
)
from app.services.requirements_workspace import (
    calculate_workspace_requirements,
    ensure_operational_units,
    import_monthly_requirements,
    inspect_excel_file,
    recalculate_monthly_requirements,
)
from app.schemas.requirements_workspace import RequirementImportRequest
from app.tests.test_permission_foundation import db, actor
from app.tests.test_central_basic_planning import catalog


def test_operational_units_seeding_is_idempotent(db):
    """Department cost centers are seeded as valid operational units in plants table without schema migration."""
    ensure_operational_units(db)
    plants = db.scalars(select(Plant.name)).all()
    plants_upper = {p.upper() for p in plants}

    for expected in ["TOOL ROOM", "PMD", "NPD", "HRD", "QAD", "ACCOUNTS", "SALES"]:
        assert expected in plants_upper

    count_before = len(plants)
    ensure_operational_units(db)
    count_after = len(db.scalars(select(Plant.name)).all())
    assert count_before == count_after


def test_departmental_sheet_ingestion_and_norm_exemption(db, catalog):
    """Departmental sheets parse dynamically and are exempt from finished-good norms."""
    user = catalog[0]

    # 1. Build an in-memory workbook with Tool Room and PMD tabs
    wb = openpyxl.Workbook()
    # Tool Room Sheet
    ws_tr = wb.active
    ws_tr.title = "TOOL ROOM"
    ws_tr.cell(1, 2, "Dept: Tool Room")
    ws_tr.cell(1, 6, "Oct'26")
    ws_tr.cell(2, 2, "S.No")
    ws_tr.cell(2, 3, "Item Id.")
    ws_tr.cell(2, 4, "Description")
    ws_tr.cell(2, 5, "Unit")
    ws_tr.cell(2, 6, "Qty")

    ws_tr.cell(3, 1, "TOOL ROOM")
    ws_tr.cell(3, 2, 1)
    ws_tr.cell(3, 3, "BBG000150QC")
    ws_tr.cell(3, 4, "Anabond 412")
    ws_tr.cell(3, 5, "NOS")
    ws_tr.cell(3, 6, 5)

    ws_tr.cell(4, 1, "TOOL ROOM")
    ws_tr.cell(4, 2, 2)
    ws_tr.cell(4, 3, "GAQ000023QC")
    ws_tr.cell(4, 4, "Cotton Waste - Big size")
    ws_tr.cell(4, 5, "KGS")
    ws_tr.cell(4, 6, 20)

    # PMD Sheet
    ws_pmd = wb.create_sheet(title="PMD")
    ws_pmd.cell(1, 3, "PMD & TOOL MAINTENANCE")
    ws_pmd.cell(1, 6, "Oct'26")
    ws_pmd.cell(2, 1, "To Location")
    ws_pmd.cell(2, 2, "Item Id.")
    ws_pmd.cell(2, 3, "Item Description")
    ws_pmd.cell(2, 4, "Part No.")
    ws_pmd.cell(2, 5, "Unit")
    ws_pmd.cell(2, 6, "Qty")

    ws_pmd.cell(3, 1, "PMD")
    ws_pmd.cell(3, 2, "ABK100003QC")
    ws_pmd.cell(3, 3, "Gloves - Knitted - 12\"")
    ws_pmd.cell(3, 5, "NOS")
    ws_pmd.cell(3, 6, 150)

    stream = io.BytesIO()
    wb.save(stream)
    file_bytes = stream.getvalue()

    # 2. Inspect excel file
    inspected = inspect_excel_file(file_bytes, "oct_dept_plan.xlsx", 10, 2026, db)
    assert inspected.error_count == 0
    assert len(inspected.preview_rows) == 3

    # Check that rows have departmental classification
    tr_row = next(r for r in inspected.preview_rows if r["consumable_code"] == "BBG000150QC")
    assert tr_row["part_name"] == "Tool Room"
    assert tr_row["part_number"] == "DEPARTMENT_INDENT"
    assert tr_row["process_name"] == "DEPARTMENT_INDENT"
    assert tr_row["rule_type"] == "PLANT_REQUEST"
    assert tr_row["scheduled_consumable_qty"] == "5.0000"

    pmd_row = next(r for r in inspected.preview_rows if r["consumable_code"] == "ABK100003QC")
    assert pmd_row["part_name"] == "PMD"
    assert pmd_row["process_name"] == "MAINTENANCE"
    assert pmd_row["scheduled_consumable_qty"] == "150.0000"

    # 3. Import requirements
    count, meta = import_monthly_requirements(
        db,
        user.id,
        RequirementImportRequest(
            planning_month=10,
            planning_year=2026,
            source_filename="oct_dept_plan.xlsx",
            records=inspected.preview_rows,
            overwrite=True,
        ),
    )
    assert count == 3

    # 4. Calculate workspace requirements
    results = calculate_workspace_requirements(db, month=10, year=2026)
    assert len(results) == 3
    for r in results:
        # Must never trigger configuration errors or missing norm errors
        assert r.status in ("Normal", "Calculated", "Low", "Critical shortage")
        assert r.rule_type == "PLANT_REQUEST"
        assert r.part_number == "DEPARTMENT_INDENT"

    # 5. Recalculate requirements: must not error or flag missing norm
    recalc = recalculate_monthly_requirements(db, user.id, 10, 2026)
    assert recalc.record_count == 3
    for r in recalc.records:
        assert r.status != "Configuration required"
        assert "Departmental indent" in (r.remarks or "")


def test_t2_stock_baseline_and_purchase_matrix_consolidation(db, catalog):
    """T-2 (August) stock baseline is sourced and purchase workspace consolidates AT:AX and AY:BF into BG."""
    user = catalog[0]

    # 1. Seed active units and consumables
    u_nos = Unit(id=uuid4(), code="NOS", name="Numbers", is_active=True)
    u_kgs = Unit(id=uuid4(), code="KGS", name="Kilograms", is_active=True)
    db.add_all([u_nos, u_kgs])
    db.flush()

    c_glove = Consumable(
        id=uuid4(),
        code="ABK100003QC",
        name="Gloves - Knitted - 12\"",
        unit_id=u_nos.id,
        is_active=True,
        latest_grn_rate=Decimal("45.5000"),
    )
    db.add(c_glove)
    db.flush()

    # 2. Seed T-2 (August 2026) Stock Statement Line for ABK100003QC
    stmt_batch = StockStatementBatch(
        id=uuid4(),
        statement_month=8,
        statement_year=2026,
        statement_date=date(2026, 8, 31),
        source_filename="august_2026_stock.xlsx",
        file_hash="mock_hash_august_2026",
        status="active",
        created_by=user.id,
    )
    db.add(stmt_batch)
    db.flush()

    stmt_line = StockStatementLine(
        id=uuid4(),
        batch_id=stmt_batch.id,
        source_row=1,
        item_id="ABK100003QC",
        item_description="Gloves - Knitted - 12\"",
        item_class="CONSUMABLE",
        unit="NOS",
        closing_qty=Decimal("80.0000"),
        closing_value=Decimal("3640.0000"),
    )
    db.add(stmt_line)
    db.flush()

    # 3. Create October 2026 Planning Version and MonthlyRequirementRecords
    # Plant 1 demands 100, Plant 2 demands 50, Tool Room demands 20, PMD demands 30
    p_version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        revision_label="R1",
        source_filename="oct_2026_plan.xlsx",
        status="DRAFT",
        created_by=user.id,
        planning_month=10,
        planning_year=2026,
    )
    db.add(p_version)
    db.flush()

    rows = [
        # Production Plants (AT:AX)
        MonthlyRequirementRecord(
            planning_version_id=p_version.id,
            planning_period="2026-10",
            planning_month=10,
            planning_year=2026,
            row_index=1,
            part_name="Bracket Assy",
            part_number="BRK-001",
            consumable_code="ABK100003QC",
            consumable_name="Gloves - Knitted - 12\"",
            process_name="Welding",
            scheduled_consumable_qty=Decimal("100.0000"),
            gross_requirement=Decimal("100.0000"),
            unit="NOS",
            plant="Plant 1",
            plant_id="PLANT_1",
            status="Calculated",
        ),
        MonthlyRequirementRecord(
            planning_version_id=p_version.id,
            planning_period="2026-10",
            planning_month=10,
            planning_year=2026,
            row_index=2,
            part_name="Frame Assy",
            part_number="FRM-001",
            consumable_code="ABK100003QC",
            consumable_name="Gloves - Knitted - 12\"",
            process_name="Assembly",
            scheduled_consumable_qty=Decimal("50.0000"),
            gross_requirement=Decimal("50.0000"),
            unit="NOS",
            plant="Plant 2",
            plant_id="PLANT_2",
            status="Calculated",
        ),
        # Departmental Indents (AY:BF)
        MonthlyRequirementRecord(
            planning_version_id=p_version.id,
            planning_period="2026-10",
            planning_month=10,
            planning_year=2026,
            row_index=3,
            part_name="Tool Room",
            part_number="DEPARTMENT_INDENT",
            consumable_code="ABK100003QC",
            consumable_name="Gloves - Knitted - 12\"",
            process_name="DEPARTMENT_INDENT",
            scheduled_consumable_qty=Decimal("20.0000"),
            gross_requirement=Decimal("20.0000"),
            unit="NOS",
            plant="Tool Room",
            plant_id="TOOL_ROOM",
            status="CALCULATED",
        ),
        MonthlyRequirementRecord(
            planning_version_id=p_version.id,
            planning_period="2026-10",
            planning_month=10,
            planning_year=2026,
            row_index=4,
            part_name="PMD",
            part_number="DEPARTMENT_INDENT",
            consumable_code="ABK100003QC",
            consumable_name="Gloves - Knitted - 12\"",
            process_name="MAINTENANCE",
            scheduled_consumable_qty=Decimal("30.0000"),
            gross_requirement=Decimal("30.0000"),
            unit="NOS",
            plant="PMD",
            plant_id="PMD",
            status="CALCULATED",
        ),
    ]
    db.add_all(rows)
    db.commit()

    # 4. Check workspace requirements: opening stock should reflect August baseline (80.0000)
    reqs = calculate_workspace_requirements(db, month=10, year=2026)
    assert len(reqs) == 4
    for r in reqs:
        assert r.opening_stock == "80.0000"

    # 5. Check purchase workspace consolidation
    current_u = actor(is_super_admin=True)
    pw = list_purchase_workspace(db, month=10, year=2026, current_user=current_u)
    assert len(pw.records) == 1
    p_rec = pw.records[0]

    # Verify Plant Demands (AT:AX)
    assert p_rec.plant_demands["PLANT_1"] == Decimal("100.0000")
    assert p_rec.plant_demands["PLANT_2"] == Decimal("50.0000")
    assert p_rec.total_plant_qty == Decimal("150.0000")

    # Verify Department Demands (AY:BF)
    assert p_rec.dept_demands["TOOL_ROOM"] == Decimal("20.0000")
    assert p_rec.dept_demands["PMD"] == Decimal("30.0000")
    assert p_rec.total_dept_qty == Decimal("50.0000")

    # Verify Total Gross Requirement (BG = Plants + Departments = 150 + 50 = 200)
    assert p_rec.required_qty == Decimal("200.0000")
    # Stock Qty should be T-2 August statement stock: 80.0000
    assert p_rec.stock_qty == Decimal("80.0000")

    # 6. Verify Excel Export Matrix Structure
    excel_bytes = export_purchase_workspace_excel(db, month=10, year=2026, current_user=current_u)
    wb_export = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Purchase Recommendations" in wb_export.sheetnames
    assert "Consolidated Matrix (AT-BG)" in wb_export.sheetnames

    ws_mat = wb_export["Consolidated Matrix (AT-BG)"]
    # Check headers in row 4
    headers = [ws_mat.cell(4, c).value for c in range(1, 19)]
    assert "Plant I (AT)" in headers
    assert "Plant II (AU)" in headers
    assert "Total Plant Qty (AT:AX)" in headers
    assert "Tool Room (AY)" in headers
    assert "PMD (BA)" in headers
    assert "Total Dept Qty (AY:BE)" in headers
    assert "Total Gross Requirement (BG)" in headers

    # Check row 5 data
    assert ws_mat.cell(5, 1).value == "ABK100003QC"
    # Plant 1 (AT) is col 4
    assert ws_mat.cell(5, 4).value == Decimal("100.0000")
    # Plant 2 (AU) is col 5
    assert ws_mat.cell(5, 5).value == Decimal("50.0000")
    # Total Plant (AT:AX) is col 9
    assert ws_mat.cell(5, 9).value == Decimal("150.0000")
    # Tool Room (AY) is col 10
    assert ws_mat.cell(5, 10).value == Decimal("20.0000")
    # PMD (BA) is col 12
    assert ws_mat.cell(5, 12).value == Decimal("30.0000")
    # Total Dept is col 17
    assert ws_mat.cell(5, 17).value == Decimal("50.0000")
    # Total Gross Requirement (BG) is col 18
    assert ws_mat.cell(5, 18).value == Decimal("200.0000")
