"""Dynamic Sales Schedule Parser and Verification Tests.

Verifies that the importer does NOT rely on hardcoded row numbers, counts, or totals:
- Test A: Rows shifted down by 10 rows (header on row 14).
- Test B: Dynamic customer blocks, closing row wording, extra R1 revision column.
- Test C: Variable customer composition (no Job Work, no Greaves/Minda, Nov'26).
- Test D: Month mismatch blocking error.
- Test E: Changes vs previous month comparison diffing logic.
- Test F: Dynamic ConsumptionNorm match (non-blocking, no ProductPlant required).
"""
import io
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
import openpyxl
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import ApplicationError
from app.db.base import Base
from app.models.auth import Permission, Role, User
from app.models.masters import Customer, CustomerAlias, Product
from app.models.prd import ImportBatch, PlanningVersion, PRDRecord
from app.models.rules import ConsumptionNorm
from app.models.inventory_masters import Consumable, Unit
from app.models.production import Process
from app.services.sales_schedule_parser import (
    parse_sales_schedule_data,
    read_workbook_rows,
    seed_default_customers_and_aliases,
)
from app.services.prd_workspace import (
    compute_changes_vs_previous_month,
    confirm_sales_schedule_import,
    preview_sales_schedule_upload,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else "")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        seed_default_customers_and_aliases(session)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def test_actor(db_session):
    u = User(
        username="dynamic_importer",
        password_hash="mock",
        is_super_admin=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


def build_excel_bytes(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Schedule"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# TEST A: Rows shifted down by 10 rows (header on row 14)
# ---------------------------------------------------------------------------
def test_rows_shifted_down_by_10_rows(db_session):
    """The importer must dynamically scan and find the header row at row 14."""
    rows = []
    # 10 dummy banner/empty rows
    for i in range(10):
        rows.append([f"Banner note {i+1}", None, None, None, None])

    # Row 11: Schedule given on
    rows.append(["Schedule given on", None, None, None, "01.10.2026"])
    # Row 12: Month
    rows.append(["Month", None, None, None, "Oct'26"])
    # Row 13: Empty
    rows.append([None, None, None, None, None])

    # Row 14: Header row (0-indexed 13)
    rows.append(["S.No.", "Part No.", "Item ID", "Description", "Oct'26 (R0)"])

    # Ashok Leyland block
    rows.append(["ASHOK LEYLAND - CHILD PARTS", None, None, None, None])
    rows.append([1, "AL-PART-1", "AL-ITEM-1", "Bracket Front", 120])
    rows.append([2, "AL-PART-2", "AL-ITEM-2", "Bracket Rear", 180])
    rows.append(["ASHOK LEYLAND - TOTAL", None, None, None, 300])

    # TAFE block
    rows.append(["TAFE FED ASSY PART", None, None, None, None])
    rows.append([1, "TF-PART-1", "TF-ITEM-1", "Needle Shaft", 50])
    rows.append(["TAFE FED Assy Part - Total", None, None, None, 50])

    # Grand Total
    rows.append(["GRAND TOTAL", None, None, None, 350])

    file_bytes = build_excel_bytes(rows)
    sheet_name, workbook_rows = read_workbook_rows(file_bytes, "test_shifted.xlsx")

    res = parse_sales_schedule_data(workbook_rows, session=db_session, target_period="2026-10")

    assert res["header_row_index"] == 14  # Row 14 (1-indexed Excel row)
    assert len(res["blocks"]) == 2
    assert res["blocks"][0]["heading_text"] == "ASHOK LEYLAND - CHILD PARTS"
    assert res["blocks"][0]["part_count"] == 2
    assert res["blocks"][0]["reconciliation_ok"] is True
    assert res["blocks"][1]["part_count"] == 1
    assert res["blocks"][1]["reconciliation_ok"] is True
    assert res["grand_total"]["reconciliation_ok"] is True
    assert res["total_part_rows"] == 3
    assert res["can_confirm"] is True
    assert res["errors"] == []


# ---------------------------------------------------------------------------
# TEST B: Dynamic blocks, new customer heading, closing wording, R1 column
# ---------------------------------------------------------------------------
def test_dynamic_blocks_closing_wording_and_extra_revision(db_session):
    """Different closing row wording, extra revision column R1, and unmapped customer."""
    rows = [
        ["Month", None, None, None, "Oct'26", "Oct'26"],
        ["Schedule given on", None, None, None, "01.10.2026", "05.10.2026"],
        [None, None, None, None, None, None],
        ["S.No.", "Part No.", "Item ID", "Description", "Oct'26 (R0)", "Oct'26 (R1)"],
        # Ashok Leyland
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None, None],
        [1, "AL-PART-1", "AL-ITEM-1", "Bracket Front", 100, 110],
        ["ASHOK LEYLAND - TOTAL", None, None, None, 100, 110],
        # TAFE with different closing wording: "TAFE FED Component - Total"
        ["TAFE FED COMPONENT", None, None, None, None, None],
        [1, "TF-PART-2", "TF-ITEM-2", "Needle Gear", 40, 45],
        ["TAFE FED Component - Total", None, None, None, 40, 45],
        # New customer heading not yet in alias database
        ["UNKNOWN MOTORS PVT LTD", None, None, None, None, None],
        [1, "UM-PART-1", "UM-ITEM-1", "Hub Plate", 60, 70],
        ["UNKNOWN MOTORS PVT LTD - TOTAL", None, None, None, 60, 70],
        # Grand total
        ["GRAND TOTAL", None, None, None, 200, 225],
    ]

    file_bytes = build_excel_bytes(rows)
    sheet_name, workbook_rows = read_workbook_rows(file_bytes, "test_b.xlsx")

    res = parse_sales_schedule_data(workbook_rows, session=db_session, target_period="2026-10")

    # Available revisions should have both R0 and R1
    rev_labels = [r["revision_label"] for r in res["available_revisions"]]
    assert "R0" in rev_labels
    assert "R1" in rev_labels

    # TAFE closing row wording should reconcile cleanly
    tafe_block = next(b for b in res["blocks"] if "TAFE" in b["heading_text"])
    assert tafe_block["reconciliation_ok"] is True

    # UNKNOWN MOTORS should be flagged as unmapped alias
    assert "UNKNOWN MOTORS PVT LTD" in res["unmapped_aliases"]
    assert res["can_confirm"] is False


# ---------------------------------------------------------------------------
# TEST C: Variable customer composition (No Job Work, no Greaves, Nov'26)
# ---------------------------------------------------------------------------
def test_variable_customer_composition_and_banner_month(db_session):
    """Works when Job Work or Greaves/Minda are absent and month is Nov'26."""
    rows = [
        ["Month", None, None, None, "Nov'26"],
        ["Schedule given on", None, None, None, "01.11.2026"],
        [None, None, None, None, None],
        ["Sl No", "Part Number", "Item ID", "Description", "Nov'26 (R0)"],
        # Only Ashok Leyland present
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None],
        [1, "AL-PART-1", "AL-ITEM-1", "Bracket Front", 250],
        ["ASHOK LEYLAND - TOTAL", None, None, None, 250],
        ["GRAND TOTAL", None, None, None, 250],
    ]

    file_bytes = build_excel_bytes(rows)
    sheet_name, workbook_rows = read_workbook_rows(file_bytes, "test_nov.xlsx")

    res = parse_sales_schedule_data(workbook_rows, session=db_session, target_period="2026-11")

    assert res["active_revisions"][0]["planning_period"] == "2026-11"
    assert len(res["blocks"]) == 1
    assert res["grand_total"]["reconciliation_ok"] is True
    assert res["can_confirm"] is True


# ---------------------------------------------------------------------------
# TEST D: Month mismatch blocking error
# ---------------------------------------------------------------------------
def test_month_mismatch_blocking_error(db_session):
    """File contains Nov'26 but user selected 2026-10 -> blocking error."""
    rows = [
        ["Month", None, None, None, "Nov'26"],
        ["Schedule given on", None, None, None, "01.11.2026"],
        [None, None, None, None, None],
        ["Sl No", "Part Number", "Item ID", "Description", "Nov'26 (R0)"],
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None],
        [1, "AL-PART-1", "AL-ITEM-1", "Bracket Front", 250],
        ["ASHOK LEYLAND - TOTAL", None, None, None, 250],
        ["GRAND TOTAL", None, None, None, 250],
    ]

    file_bytes = build_excel_bytes(rows)
    sheet_name, workbook_rows = read_workbook_rows(file_bytes, "test_nov.xlsx")

    # Target period mismatch: passed 2026-10 while file has Nov'26 (2026-11)
    res = parse_sales_schedule_data(workbook_rows, session=db_session, target_period="2026-10")

    assert res["can_confirm"] is False
    assert any("Month mismatch" in e for e in res["errors"])


def period_workbook(month_label, quantity=100, revised_quantity=None):
    rows = [
        ["S.No.", "Part No.", "Item ID", "Description", f"{month_label} (R0)"],
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None],
        [1, "PERIOD-PART", "PERIOD-ITEM", "Period bracket", quantity],
        ["ASHOK LEYLAND - TOTAL", None, None, None, quantity],
        ["GRAND TOTAL", None, None, None, quantity],
    ]
    if revised_quantity is not None:
        for row, value in zip(rows, [f"{month_label} (R1)", None, revised_quantity, revised_quantity, revised_quantity]):
            row.append(value)
    return build_excel_bytes(rows)


def test_confirmation_enforces_selected_month_without_writing_records(db_session, test_actor):
    inspected = preview_sales_schedule_upload(
        db_session, period_workbook("Nov'26"), "synthetic.xlsx", target_period="2026-10",
    )
    assert not inspected.can_confirm
    with pytest.raises(ApplicationError, match="Month mismatch"):
        confirm_sales_schedule_import(
            db_session, inspected.file_token, inspected.sheet_name, "2026-10", "R0", "Plant 1", test_actor.id,
        )
    assert not db_session.scalars(select(PRDRecord)).all()
    assert not db_session.scalars(select(PlanningVersion)).all()


def test_uploads_for_different_months_and_years_preserve_existing_periods(db_session, test_actor):
    for period, label, quantity in [("2026-10", "Oct'26", 100), ("2026-11", "Nov'26", 200), ("2027-10", "Oct'27", 300)]:
        inspected = preview_sales_schedule_upload(
            db_session, period_workbook(label, quantity), "synthetic.xlsx", target_period=period, revision_label="R0",
        )
        assert inspected.can_confirm
        confirm_sales_schedule_import(
            db_session, inspected.file_token, inspected.sheet_name, period, "R0", "Plant 1", test_actor.id,
        )
    saved = db_session.scalars(select(PRDRecord).order_by(PRDRecord.target_period)).all()
    assert [(row.target_period, row.revision, row.planned_quantity) for row in saved] == [
        ("2026-10", "R0", Decimal("100")), ("2026-11", "R0", Decimal("200")), ("2027-10", "R0", Decimal("300")),
    ]
    assert len(db_session.scalars(select(PlanningVersion)).all()) == 3


def test_confirmation_requires_one_revision_in_the_selected_month(db_session, test_actor):
    inspected = preview_sales_schedule_upload(
        db_session, period_workbook("Oct'26", revised_quantity=150), "synthetic.xlsx", target_period="2026-10",
    )
    assert inspected.can_confirm
    assert len(inspected.active_revisions) == 2
    with pytest.raises(ApplicationError, match="Choose one planning month and revision"):
        confirm_sales_schedule_import(
            db_session, inspected.file_token, inspected.sheet_name, "2026-10", None, "Plant 1", test_actor.id,
        )
    assert not db_session.scalars(select(PRDRecord)).all()
    assert not db_session.scalars(select(PlanningVersion)).all()


# ---------------------------------------------------------------------------
# TEST E: Changes vs previous month diff logic
# ---------------------------------------------------------------------------
def test_changes_vs_previous_month_diff_logic(db_session, test_actor):
    """Correctly detects parts added, removed, changed quantities, and blocks diff."""
    # Seed previous month (2026-09) records in PRDRecord
    db_session.add_all([
        PRDRecord(
            id=uuid4(),
            row_index=1,
            plant="Plant 1",
            customer="Ashok Leyland",
            product_code="PART-A",
            description="Bracket A",
            planned_quantity=Decimal("100.0000"),
            uom="Nos",
            target_period="2026-09",
            planning_version="R0",
            created_by=test_actor.id,
            is_deleted=False,
        ),
        PRDRecord(
            id=uuid4(),
            row_index=2,
            plant="Plant 1",
            customer="Ashok Leyland",
            product_code="PART-B",
            description="Bracket B",
            planned_quantity=Decimal("50.0000"),
            uom="Nos",
            target_period="2026-09",
            planning_version="R0",
            created_by=test_actor.id,
            is_deleted=False,
        ),
        PRDRecord(
            id=uuid4(),
            row_index=3,
            plant="Plant 1",
            customer="Greaves Mobility",
            product_code="PART-G",
            description="Greaves Needle",
            planned_quantity=Decimal("30.0000"),
            uom="Nos",
            target_period="2026-09",
            planning_version="R0",
            created_by=test_actor.id,
            is_deleted=False,
        ),
    ])
    db_session.commit()

    # Current month (2026-10) flat rows:
    # - PART-A quantity changed from 100 to 120
    # - PART-C is newly added (qty 80)
    # - PART-B is missing (removed!)
    # - Greaves Mobility is missing (block removed!)
    # - TAFE is newly added (block added!)
    current_flat_rows = [
        {
            "customer": "Ashok Leyland",
            "part_no": "PART-A",
            "item_id": "",
            "description": "Bracket A",
            "planned_quantity": "120.0000",
        },
        {
            "customer": "Ashok Leyland",
            "part_no": "PART-C",
            "item_id": "",
            "description": "Bracket C",
            "planned_quantity": "80.0000",
        },
        {
            "customer": "TAFE",
            "part_no": "PART-T",
            "item_id": "",
            "description": "TAFE Part",
            "planned_quantity": "40.0000",
        },
    ]
    current_blocks = [
        {"customer_name": "Ashok Leyland"},
        {"customer_name": "TAFE"},
    ]

    diff = compute_changes_vs_previous_month(
        session=db_session,
        current_period="2026-10",
        current_flat_rows=current_flat_rows,
        current_blocks=current_blocks,
    )

    assert diff["has_previous_data"] is True
    assert diff["previous_period"] == "2026-09"
    # PART-C and PART-T are added
    assert diff["added_count"] == 2
    # PART-B and PART-G are removed
    assert diff["removed_count"] == 2
    # PART-A is changed
    assert diff["changed_count"] == 1
    assert diff["parts_quantity_changed"][0]["part_no"] == "PART-A"
    assert diff["parts_quantity_changed"][0]["old_quantity"] == "100.0000"
    assert diff["parts_quantity_changed"][0]["new_quantity"] == "120.0000"
    # Blocks added / removed
    assert "TAFE" in diff["blocks_added"]
    assert "Greaves Mobility" in diff["blocks_removed"]


# ---------------------------------------------------------------------------
# TEST F: Dynamic ConsumptionNorm Match (Non-blocking, no ProductPlant required)
# ---------------------------------------------------------------------------
def test_dynamic_consumption_norm_match_non_blocking(db_session, test_actor):
    """Verifies that norm matching computes dynamically without ProductPlant or Route."""
    # Create product and consumable masters
    prod_a = Product(id=uuid4(), code="PROD-A", part_number="PART-A", item_id="ITEM-A", name="Product A", uom="Nos")
    prod_b = Product(id=uuid4(), code="PROD-B", part_number="PART-B", item_id="ITEM-B", name="Product B", uom="Nos")
    unit = Unit(id=uuid4(), code="KGS", name="Kilograms")
    proc = Process(id=uuid4(), name="Machining")
    db_session.add_all([prod_a, prod_b, unit, proc])
    db_session.flush()

    mat = Consumable(id=uuid4(), code="OIL-01", name="Coolant Oil", unit_id=unit.id)
    db_session.add(mat)
    db_session.flush()

    # Add a norm ONLY for prod_a (prod_b has none)
    norm = ConsumptionNorm(
        id=uuid4(),
        product_id=prod_a.id,
        process_id=proc.id,
        consumable_id=mat.id,
        unit_id=unit.id,
        rule_type="PRODUCTION_RATE",
        parameters={"rate": "0.0500"},
        effective_from=date(2026, 1, 1),
        is_active=True,
    )
    db_session.add(norm)
    db_session.commit()

    rows = [
        ["Month", None, None, None, "Oct'26"],
        ["Schedule given on", None, None, None, "01.10.2026"],
        [None, None, None, None, None],
        ["S.No.", "Part No.", "Item ID", "Description", "Oct'26 (R0)"],
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None],
        [1, "PART-A", "ITEM-A", "Product A Description", 100],
        [2, "PART-B", "ITEM-B", "Product B Description", 200],
        ["ASHOK LEYLAND - TOTAL", None, None, None, 300],
        ["GRAND TOTAL", None, None, None, 300],
    ]
    file_bytes = build_excel_bytes(rows)

    preview_resp = preview_sales_schedule_upload(
        session=db_session,
        file_bytes=file_bytes,
        filename="sales_schedule_test.xlsx",
        target_period="2026-10",
    )

    assert preview_resp.can_confirm is True
    assert preview_resp.total_part_rows == 2

    # Check sample_rows for norm_match chips
    row_a = next(r for r in preview_resp.sample_rows if r["part_no"] == "PART-A")
    row_b = next(r for r in preview_resp.sample_rows if r["part_no"] == "PART-B")

    assert row_a["norm_match"] == "Matched"
    assert row_b["norm_match"] == "No norms found"

    # Now confirm the import (with require_route_mapping=False)
    # Neither ProductPlant nor Route exists, yet import MUST succeed!
    confirm_resp = confirm_sales_schedule_import(
        session=db_session,
        file_token=preview_resp.file_token,
        sheet_name=preview_resp.sheet_name,
        target_period="2026-10",
        revision_label="R0",
        plant_code="Plant 1",
        actor=test_actor.id,
        require_route_mapping=False,
    )

    assert confirm_resp.imported_count == 2

    # Check that batch has workflow: BASIC_CENTRAL_V1
    batch = db_session.scalar(select(ImportBatch).order_by(ImportBatch.uploaded_at.desc()))
    assert batch is not None
    assert (batch.validation_summary or {}).get("workflow") == "BASIC_CENTRAL_V1"


# ---------------------------------------------------------------------------
# TEST G: Revisions R0 and R1 are preserved as separate records
# ---------------------------------------------------------------------------
def test_revisions_r0_r1_kept_separate_and_not_summed(db_session, test_actor):
    """Verifies that R0 and R1 are saved as separate planning versions and never summed."""
    rows = [
        ["Month", None, None, None, "Oct'26", "Oct'26"],
        ["Schedule given on", None, None, None, "01.10.2026", "05.10.2026"],
        [None, None, None, None, None, None],
        ["S.No.", "Part No.", "Item ID", "Description", "Oct'26 (R0)", "Oct'26 (R1)"],
        ["ASHOK LEYLAND - CHILD PARTS", None, None, None, None, None],
        [1, "REV-PART-1", "REV-ITEM-1", "Revision Bracket", 100, 150],
        ["ASHOK LEYLAND - TOTAL", None, None, None, 100, 150],
        ["GRAND TOTAL", None, None, None, 100, 150],
    ]
    file_bytes = build_excel_bytes(rows)

    # Preview R0
    preview_r0 = preview_sales_schedule_upload(
        session=db_session,
        file_bytes=file_bytes,
        filename="sales_schedule_revs.xlsx",
        target_period="2026-10",
        revision_label="R0",
    )
    confirm_sales_schedule_import(
        session=db_session,
        file_token=preview_r0.file_token,
        sheet_name=preview_r0.sheet_name,
        target_period="2026-10",
        revision_label="R0",
        plant_code="Plant 1",
        actor=test_actor.id,
    )

    # Preview R1
    preview_r1 = preview_sales_schedule_upload(
        session=db_session,
        file_bytes=file_bytes,
        filename="sales_schedule_revs.xlsx",
        target_period="2026-10",
        revision_label="R1",
    )
    confirm_sales_schedule_import(
        session=db_session,
        file_token=preview_r1.file_token,
        sheet_name=preview_r1.sheet_name,
        target_period="2026-10",
        revision_label="R1",
        plant_code="Plant 1",
        actor=test_actor.id,
    )

    # Query PRDRecord
    r0_records = db_session.scalars(
        select(PRDRecord).where(PRDRecord.target_period == "2026-10", PRDRecord.revision == "R0")
    ).all()
    r1_records = db_session.scalars(
        select(PRDRecord).where(PRDRecord.target_period == "2026-10", PRDRecord.revision == "R1")
    ).all()

    assert len(r0_records) == 1
    assert len(r1_records) == 1
    # Distinct planned quantities, NOT summed (100 and 150, not 250)
    assert r0_records[0].planned_quantity == Decimal("100.0000")
    assert r1_records[0].planned_quantity == Decimal("150.0000")

