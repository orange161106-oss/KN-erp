import io
from decimal import Decimal
from uuid import uuid4
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.audit import AuditLog
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.prd import PlanningVersion
from app.models.requirements import MonthlyRequirementRecord
from app.models.stock_statements import StockParameter, StockParameterBatch
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import (
    RowIssue,
    RowResolutionInput,
    StockParameterConfirmRequest,
)
from app.security.passwords import PasswordService
from app.security.tokens import create_access_token
from app.services import purchase_workspace
from app.services import stock_management_service as service


PERMISSIONS_FOR_IMPORT = [
    "inventory.stock.read",
    "inventory.stock.import",
    "inventory.read",
    "inventory.create",
    "inventory.update",
]


def create_synthetic_stock_management_wb(
    rows: list[dict],
    headers: list[str] | None = None,
    title: str | None = None,
) -> bytes:
    """Build an in-memory Stockmanagement.xlsx workbook matching real KNL header & row patterns."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    if title:
        ws.append([title])

    if headers is None:
        # Exact KNL header variants with trailing spaces and 'quanity' typo
        headers = [
            "Item Id",
            "Category",
            "Type of material",
            "Description",
            "Minimum stock level ",
            "Maximum stock level",
            "Minimum order quanity",
            "Lead time to supply in days ",
        ]
    ws.append(headers)

    for r in rows:
        ws.append([
            r.get("item_id", None),
            r.get("category", None),
            r.get("type_of_material", None),
            r.get("description", None),
            r.get("min_stock_level", None),
            r.get("max_stock_level", None),
            r.get("min_order_qty", None),
            r.get("lead_time_days", None),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def stock_mgmt_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else "")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    passwords = PasswordService()
    with Session(engine, expire_on_commit=False) as session:
        grants = [Permission(code=p, description=f"Grant {p}") for p in PERMISSIONS_FOR_IMPORT]
        role = Role(code="INVENTORY_MGR", name="Inventory Manager", permissions=grants)
        user = User(
            username="inv_operator",
            full_name="Inventory Operator",
            password_hash=passwords.hash("password"),
            roles=[role],
        )
        unit_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
        unit_kgs = Unit(id=uuid4(), code="KGS", name="Kilograms")
        supplier = Supplier(code="SUP-KNL", name="KNL Industrial Supplies")
        session.add_all([role, user, unit_nos, unit_kgs, supplier] + grants)
        session.flush()

        c_nbq = Consumable(
            id=uuid4(),
            item_id="NBQ000044QC",
            name='Polythene Bag 15" x 26"',
            category="Packing Consumables",
            type_of_material="Packing",
            unit_id=unit_nos.id,
            is_active=True,
        )
        c_baa = Consumable(
            id=uuid4(),
            item_id="BAA120006QC",
            name="Carbide Insert CNMG",
            category="Production consumables",
            type_of_material="Cutting Tools",
            unit_id=unit_nos.id,
            is_active=True,
        )
        c_bac = Consumable(
            id=uuid4(),
            item_id="BAC000002QC",
            name="HSS Drill Bit 6.5mm",
            category="Production consumables",
            type_of_material="Cutting Tools",
            unit_id=unit_nos.id,
            is_active=True,
        )
        c_lpg = Consumable(
            id=uuid4(),
            item_id="ABA100009QC",
            name="Liquefied Petroleum Gas(LPG)",
            category="Powder coating Consumables",
            type_of_material="Fuel & Gas",
            unit_id=unit_kgs.id,
            is_active=True,
        )
        c_cutter = Consumable(
            id=uuid4(),
            item_id="CUT560001QC",
            name="Milling Cutter Dia 56mm",
            category="Production consumables",
            type_of_material="Cutting Tools",
            unit_id=unit_nos.id,
            is_active=True,
        )
        session.add_all([c_nbq, c_baa, c_bac, c_lpg, c_cutter])
        session.flush()

        for c in (c_nbq, c_baa, c_bac, c_lpg, c_cutter):
            session.add(SupplierConsumable(consumable_id=c.id, supplier_id=supplier.id))

        session.commit()

    yield engine
    engine.dispose()


@pytest.fixture
def test_actor(stock_mgmt_db):
    with Session(stock_mgmt_db) as session:
        user = session.scalar(select(User).where(User.username == "inv_operator"))
        return CurrentUser(
            id=user.id,
            username=user.username,
            roles=["INVENTORY_MGR"],
            permissions=PERMISSIONS_FOR_IMPORT,
        )


def test_normalize_header_variants_and_typos():
    """Header matching is tolerant of trailing spaces, case differences, and 'Minimum order quanity' typo."""
    assert service.normalize_header("Category") == "category"
    assert service.normalize_header("Type of Material") == "type of material"
    assert service.normalize_header("Item Id") == "item id"
    assert service.normalize_header("Description") == "description"
    assert service.normalize_header("Minimum stock level ") == "minimum stock level"
    assert service.normalize_header("Maximum stock level") == "maximum stock level"
    assert service.normalize_header("Minimum order quanity") == "minimum order quanity"
    assert service.normalize_header("Lead time to supply in days ") == "lead time to supply in days"


def test_parse_raw_int():
    issues: list[RowIssue] = []

    assert service.parse_raw_int(15, 1, "Lead Time in Days", issues) == 15
    assert service.parse_raw_int("30", 2, "Lead Time in Days", issues) == 30
    assert service.parse_raw_int("-", 3, "Lead Time in Days", issues) == 0
    assert service.parse_raw_int("", 4, "Lead Time in Days", issues) is None
    assert service.parse_raw_int(None, 5, "Lead Time in Days", issues) is None

    issues_frac: list[RowIssue] = []
    res = service.parse_raw_int("14.5", 6, "Lead Time in Days", issues_frac)
    assert res is None
    assert len(issues_frac) == 1
    assert issues_frac[0].severity == "ERROR"
    assert "whole number" in issues_frac[0].description


def test_get_previous_month():
    assert service.get_previous_month(10, 2026) == (9, 2026)
    assert service.get_previous_month(1, 2026) == (12, 2025)
    assert service.get_previous_month(5, 2024) == (4, 2024)


def test_exact_duplicate_row_warning_and_skipped_after_confirm(stock_mgmt_db, test_actor):
    """Exact duplicate (same Item Id, Category, Type, limits; description spacing differs) -> warning, skipped on confirm."""
    with Session(stock_mgmt_db) as session:
        wb_bytes = create_synthetic_stock_management_wb([
            {
                "item_id": "NBQ000044QC",
                "category": "Packing Consumables",
                "type_of_material": "Packing",
                "description": 'Polythene Bag 15" x 26"',
                "min_stock_level": 500,
                "max_stock_level": 1000,
                "min_order_qty": 500,
                "lead_time_days": 7,
            },
            {
                "item_id": "NBQ000044QC",
                "category": "Packing Consumables",
                "type_of_material": "Packing",
                "description": 'Polythene Bag 15"x26"',  # spacing difference around quotes
                "min_stock_level": 500,
                "max_stock_level": 1000,
                "min_order_qty": 500,
                "lead_time_days": 7,
            },
        ])

        preview = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )

        # Must NOT be a blocking error; must be a WARNING with code EXACT_DUPLICATE
        assert len(preview.errors) == 0
        assert preview.can_confirm is True
        dup_warnings = [w for w in preview.warnings if w.code == "EXACT_DUPLICATE"]
        assert len(dup_warnings) == 1
        dw = dup_warnings[0]
        assert dw.row == 3
        assert dw.conflicting_row == 2
        assert "Row 3 repeats row 2" in dw.description
        assert dw.default_action == "KEEP_FIRST"
        assert dw.row_content["item_id"] == "NBQ000044QC"

        # Confirm with user confirming KEEP_FIRST
        confirm_res = service.confirm_stock_parameters_import(
            session=session,
            payload=StockParameterConfirmRequest(
                file_token=preview.file_token,
                month=10,
                year=2026,
                resolutions=[RowResolutionInput(row=3, action="KEEP_FIRST")],
            ),
            user=test_actor,
        )

        assert len(confirm_res.records) == 1
        assert confirm_res.records[0].item_id == "NBQ000044QC"
        assert confirm_res.records[0].source_row == 2
        assert confirm_res.records[0].resolution_applied == "KEPT_FIRST"
        assert confirm_res.summary.skipped_rows_count == 1
        assert confirm_res.metadata.skipped_rows[0]["row"] == 3


def test_same_item_different_category_both_kept_with_warning(stock_mgmt_db, test_actor):
    """Same Item Id under two categories (BAA120006QC, BAC000002QC) -> valid data, both kept, warning shown."""
    with Session(stock_mgmt_db) as session:
        wb_bytes = create_synthetic_stock_management_wb([
            {
                "item_id": "BAA120006QC",
                "category": "Production consumables",
                "type_of_material": "Cutting Tools",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 50,
                "max_stock_level": 100,
                "min_order_qty": 50,
                "lead_time_days": 10,
            },
            {
                "item_id": "BAA120006QC",
                "category": "TFJ",
                "type_of_material": "TFJ Maint items",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 50,
                "max_stock_level": 100,
                "min_order_qty": 50,
                "lead_time_days": 10,
            },
        ])

        preview = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )

        assert len(preview.errors) == 0
        assert preview.can_confirm is True
        mc_warnings = [w for w in preview.warnings if w.code == "MULTI_CATEGORY_ITEM"]
        assert len(mc_warnings) == 1
        assert "appears under 2 categories" in mc_warnings[0].description

        confirm_res = service.confirm_stock_parameters_import(
            session=session,
            payload=StockParameterConfirmRequest(
                file_token=preview.file_token,
                month=10,
                year=2026,
            ),
            user=test_actor,
        )

        # Both rows are saved in stock_parameters
        assert len(confirm_res.records) == 2
        assert confirm_res.summary.multi_category_items_count == 1
        assert confirm_res.summary.ambiguous_limits_items_count == 0
        assert all(r.category_count == 2 for r in confirm_res.records)


def test_same_item_and_category_different_limits_blocking_conflict(stock_mgmt_db, test_actor):
    """Same Item Id AND same Category with different limits -> blocking error until user chooses which row to keep."""
    with Session(stock_mgmt_db) as session:
        wb_bytes = create_synthetic_stock_management_wb([
            {
                "item_id": "BAA120006QC",
                "category": "Production consumables",
                "type_of_material": "Cutting Tools",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 50,
                "max_stock_level": 100,
                "min_order_qty": 50,
                "lead_time_days": 10,
            },
            {
                "item_id": "BAA120006QC",
                "category": "Production consumables",
                "type_of_material": "Cutting Tools",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 80,
                "max_stock_level": 200,
                "min_order_qty": 100,
                "lead_time_days": 14,
            },
        ])

        preview = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )

        assert preview.can_confirm is False
        conflict_errors = [e for e in preview.errors if e.code == "SAME_CATEGORY_CONFLICT"]
        assert len(conflict_errors) == 1
        ce = conflict_errors[0]
        assert ce.row == 3
        assert ce.conflicting_row == 2
        assert ce.conflicting_row_content["min_stock_level"] == "50"
        assert ce.row_content["min_stock_level"] == "80"

        # Attempting to confirm without resolution fails with 422
        with pytest.raises(ApplicationError) as exc_info:
            service.confirm_stock_parameters_import(
                session=session,
                payload=StockParameterConfirmRequest(
                    file_token=preview.file_token,
                    month=10,
                    year=2026,
                ),
                user=test_actor,
            )
        assert exc_info.value.status_code == 422

        # Re-preview and resolve by choosing KEEP_SECOND (row 3)
        preview2 = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )
        confirm_res = service.confirm_stock_parameters_import(
            session=session,
            payload=StockParameterConfirmRequest(
                file_token=preview2.file_token,
                month=10,
                year=2026,
                resolutions=[RowResolutionInput(row=3, action="KEEP_SECOND")],
            ),
            user=test_actor,
        )
        assert len(confirm_res.records) == 1
        assert confirm_res.records[0].source_row == 3
        assert confirm_res.records[0].min_stock_level == Decimal("80")
        assert confirm_res.records[0].resolution_applied == "KEPT_SECOND"


def test_incomplete_line_and_missing_item_id_with_hint_and_resolutions(stock_mgmt_db, test_actor):
    """
    - Row with description only ('Milling Cutter Dia 56mm') -> INCOMPLETE_LINE blocking error until skipped.
    - Row without Item Id ('Liquefied Petroleum Gas(LPG)') matching Row 2 -> hint shown, never auto-assigned;
      assigning invalid ID fails; assigning valid ID ABA100009QC succeeds and saves both category rows.
    """
    with Session(stock_mgmt_db) as session:
        wb_bytes = create_synthetic_stock_management_wb([
            # Row 2: Incomplete line (like Row 24 in Stockmanagement.xlsx)
            {
                "item_id": None,
                "category": None,
                "type_of_material": None,
                "description": "Unlisted Special Tool Dia 99mm",
                "min_stock_level": None,
                "max_stock_level": None,
                "min_order_qty": None,
                "lead_time_days": None,
            },
            # Row 3: Valid LPG under Powder coating Consumables (like Row 211)
            {
                "item_id": "ABA100009QC",
                "category": "Powder coating Consumables",
                "type_of_material": "Fuel & Gas",
                "description": "Liquefied Petroleum Gas(LPG)",
                "min_stock_level": 1016,
                "max_stock_level": 1967,
                "min_order_qty": 950,
                "lead_time_days": 3,
            },
            # Row 4: Missing Item Id for LPG under Needles production Consumables (like Row 376)
            {
                "item_id": None,
                "category": "Needles production Consumables",
                "type_of_material": "Fuel & Gas",
                "description": "Liquefied Petroleum Gas(LPG)",
                "min_stock_level": 950,
                "max_stock_level": 1900,
                "min_order_qty": 950,
                "lead_time_days": 3,
            },
        ])

        preview = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )

        assert preview.can_confirm is False
        assert len(preview.errors) == 2

        err_row2 = next(e for e in preview.errors if e.row == 2)
        assert err_row2.code == "INCOMPLETE_LINE"
        assert "incomplete line" in err_row2.description.lower()

        err_row4 = next(e for e in preview.errors if e.row == 4)
        assert err_row4.code == "MISSING_ITEM_ID"
        # Hint must show ABA100009QC from Row 3 with its category and limits, but NEVER auto-assign it
        assert len(err_row4.possible_matches) >= 1
        hint = err_row4.possible_matches[0]
        assert hint["item_id"] == "ABA100009QC"
        assert hint["category"] == "Powder coating Consumables"
        assert hint["min_stock_level"] == "1016"
        assert hint["max_stock_level"] == "1967"
        assert len(preview.lines_preview) == 1  # Only Row 3 is in lines_preview; Row 4 was NOT auto-filled

        # 1. Assigning an invalid Item Id is rejected by the server
        with pytest.raises(ApplicationError) as exc_bad_id:
            service.confirm_stock_parameters_import(
                session=session,
                payload=StockParameterConfirmRequest(
                    file_token=preview.file_token,
                    month=10,
                    year=2026,
                    resolutions=[
                        RowResolutionInput(row=2, action="SKIP_ROW"),
                        RowResolutionInput(row=4, action="ASSIGN_ITEM_ID", assigned_item_id="NOT_A_REAL_ITEM_999"),
                    ],
                ),
                user=test_actor,
            )
        assert exc_bad_id.value.status_code == 422
        assert exc_bad_id.value.code == "INVALID_ASSIGNED_ITEM_ID"

        # 2. Re-preview and confirm with valid resolutions: Skip Row 2, Assign ABA100009QC to Row 4
        preview2 = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )
        confirm_res = service.confirm_stock_parameters_import(
            session=session,
            payload=StockParameterConfirmRequest(
                file_token=preview2.file_token,
                month=10,
                year=2026,
                resolutions=[
                    RowResolutionInput(row=2, action="SKIP_ROW"),
                    RowResolutionInput(row=4, action="ASSIGN_ITEM_ID", assigned_item_id="ABA100009QC"),
                ],
            ),
            user=test_actor,
        )

        # Both category rows for ABA100009QC are saved; Row 2 is in skipped_rows and audit log
        assert len(confirm_res.records) == 2
        row4_saved = next(r for r in confirm_res.records if r.source_row == 4)
        assert row4_saved.item_id == "ABA100009QC"
        assert row4_saved.category == "Needles production Consumables"
        assert row4_saved.min_stock_level == Decimal("950")
        assert row4_saved.resolution_applied == "ASSIGNED_ITEM_ID"
        assert row4_saved.resolved_by_name == "Inventory Operator"

        assert confirm_res.summary.skipped_rows_count == 1
        assert confirm_res.metadata.skipped_rows[0]["row"] == 2
        assert confirm_res.summary.ambiguous_limits_items_count == 1  # Different limits across the 2 categories!

        # Check Audit Log
        audit_entry = session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "StockParameterBatch",
                AuditLog.action == "CREATE",
            )
        )
        assert audit_entry is not None
        assert audit_entry.new_values["skipped_rows_count"] == 1
        assert len(audit_entry.new_values["resolutions_applied"]) == 2


def test_purchase_workspace_reads_right_row_per_category_and_flags_ambiguous_limits(stock_mgmt_db, test_actor):
    """
    Purchase planning:
    - If item has multiple categories with IDENTICAL limits (BAA120006QC), uses those limits cleanly.
    - If item has multiple categories with DIFFERENT limits (ABA100009QC):
      - Without category context: flags the item as ambiguous for review and does NOT choose silently.
      - With category context ('Needles production Consumables'): uses that category's row (Min 950, Max 1900).
    """
    with Session(stock_mgmt_db) as session:
        wb_bytes = create_synthetic_stock_management_wb([
            {
                "item_id": "BAA120006QC",
                "category": "Production consumables",
                "type_of_material": "Cutting Tools",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 50,
                "max_stock_level": 100,
                "min_order_qty": 60,
                "lead_time_days": 10,
            },
            {
                "item_id": "BAA120006QC",
                "category": "TFJ",
                "type_of_material": "TFJ Maint items",
                "description": "Carbide Insert CNMG",
                "min_stock_level": 50,
                "max_stock_level": 100,
                "min_order_qty": 60,
                "lead_time_days": 10,
            },
            {
                "item_id": "ABA100009QC",
                "category": "Powder coating Consumables",
                "type_of_material": "Fuel & Gas",
                "description": "Liquefied Petroleum Gas(LPG)",
                "min_stock_level": 1016,
                "max_stock_level": 1967,
                "min_order_qty": 1200,
                "lead_time_days": 3,
            },
            {
                "item_id": "ABA100009QC",
                "category": "Needles production Consumables",
                "type_of_material": "Fuel & Gas",
                "description": "Liquefied Petroleum Gas(LPG)",
                "min_stock_level": 950,
                "max_stock_level": 1900,
                "min_order_qty": 950,
                "lead_time_days": 3,
            },
        ])

        preview = service.parse_and_preview_stock_parameters(
            session=session,
            content=wb_bytes,
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )
        service.confirm_stock_parameters_import(
            session=session,
            payload=StockParameterConfirmRequest(
                file_token=preview.file_token,
                month=10,
                year=2026,
            ),
            user=test_actor,
        )

        # Create a planning version and requirement records for Oct 2026
        version = PlanningVersion(
            planning_period="2026-10",
            version_number=0,
            revision_label="R0",
            source_filename="oct_plan.xlsx",
            status="CALCULATED",
            planning_month=10,
            planning_year=2026,
            created_by=test_actor.id,
        )
        session.add(version)
        session.flush()

        session.add_all([
            MonthlyRequirementRecord(
                planning_version_id=version.id,
                planning_period="2026-10",
                planning_month=10,
                planning_year=2026,
                row_index=1,
                part_name="Needle Body",
                part_number="NDL-01",
                consumable_code="BAA120006QC",
                consumable_name="Carbide Insert CNMG",
                process_name="Turning",
                production_order_qty=Decimal("1000"),
                scheduled_consumable_qty=Decimal("40"),
                stock_qty=Decimal("10"),
                po_pending_qty=Decimal("0"),
                shortage_qty=Decimal("30"),
                unit="NOS",
                status="Shortage",
                created_by=test_actor.id,
            ),
            MonthlyRequirementRecord(
                planning_version_id=version.id,
                planning_period="2026-10",
                planning_month=10,
                planning_year=2026,
                row_index=2,
                part_name="Coated Frame",
                part_number="FRM-01",
                consumable_code="ABA100009QC",
                consumable_name="Liquefied Petroleum Gas(LPG)",
                process_name="Heating",
                production_order_qty=Decimal("500"),
                scheduled_consumable_qty=Decimal("800"),
                stock_qty=Decimal("100"),
                po_pending_qty=Decimal("0"),
                shortage_qty=Decimal("700"),
                unit="KGS",
                status="Shortage",
                created_by=test_actor.id,
            ),
        ])
        session.commit()

        # 1. Without category context:
        # BAA120006QC has identical limits (MOQ=60), so recommended is raised from shortage 30 to MOQ 60.
        # ABA100009QC has different limits (MOQ 1200 vs 950), so it is flagged as ambiguous and NOT silently guessed!
        pw_no_cat = purchase_workspace.list_purchase_workspace(session, month=10, year=2026)
        rec_baa = next(r for r in pw_no_cat.records if r.consumable_code == "BAA120006QC")
        assert rec_baa.system_recommended_qty == Decimal("60.0000")
        assert "Limits (" in (rec_baa.remarks or "")

        rec_lpg = next(r for r in pw_no_cat.records if r.consumable_code == "ABA100009QC")
        assert "Ambiguous stock limits across 2 categories" in (rec_lpg.remarks or "")
        assert rec_lpg.system_recommended_qty == Decimal("700.0000")  # Not guessed to 1200 or 950

        # 2. With category context ('Needles production Consumables'):
        # ABA100009QC resolves to Needles production Consumables (MOQ=950, Min=950, Max=1900)
        pw_needles = purchase_workspace.list_purchase_workspace(
            session,
            month=10,
            year=2026,
            category="Needles production Consumables",
        )
        rec_lpg_needles = next(r for r in pw_needles.records if r.consumable_code == "ABA100009QC")
        assert rec_lpg_needles.system_recommended_qty == Decimal("950.0000")
        assert "Limits (Needles production Consumables): Min=950.0000, Max=1900.0000, MOQ=950.0000" in (rec_lpg_needles.remarks or "")


def test_http_error_report_and_import_summary_excel_downloads(stock_mgmt_db):
    """End-to-end HTTP test for preview-errors (.xlsx) and import-summary (.xlsx) downloads."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user@127.0.0.1/kn_unit_test",
        auth_secret_key="test-secret-key-for-stock-management-testing-32b",
    )
    with Session(stock_mgmt_db) as session:
        user = session.scalar(select(User).where(User.username == "inv_operator"))
        app = create_app(settings)

        def override_db():
            with Session(stock_mgmt_db, expire_on_commit=False, autoflush=False) as s:
                yield s

        app.dependency_overrides[get_db] = override_db
        token = create_access_token(user.id, settings)

        wb_bytes = create_synthetic_stock_management_wb([
            # Row 2: Incomplete line
            {"description": "Milling Cutter Dia 56mm"},
            # Row 3: Valid item
            {
                "item_id": "NBQ000044QC",
                "category": "Packing Consumables",
                "type_of_material": "Packing",
                "description": 'Polythene Bag 15" x 26"',
                "min_stock_level": 500,
                "max_stock_level": 1000,
                "min_order_qty": 500,
                "lead_time_days": 7,
            },
            # Row 4: Exact duplicate of Row 3
            {
                "item_id": "NBQ000044QC",
                "category": "Packing Consumables",
                "type_of_material": "Packing",
                "description": 'Polythene Bag 15"x26"',
                "min_stock_level": 500,
                "max_stock_level": 1000,
                "min_order_qty": 500,
                "lead_time_days": 7,
            },
        ])

        with TestClient(app) as client:
            client.headers.update({"Authorization": f"Bearer {token}"})

            # 1. Preview
            prev_res = client.post(
                "/api/v1/inventory/management/preview",
                data={"month": 10, "year": 2026},
                files={"file": ("Stockmanagement.xlsx", wb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
            assert prev_res.status_code == 200
            prev_data = prev_res.json()
            file_token = prev_data["file_token"]
            assert prev_data["can_confirm"] is False

            # 2. Download Error Report (.xlsx)
            err_res = client.get(f"/api/v1/inventory/management/preview-errors?file_token={file_token}")
            assert err_res.status_code == 200
            err_wb = openpyxl.load_workbook(io.BytesIO(err_res.content))
            assert "Validation Issues" in err_wb.sheetnames
            ws_err = err_wb["Validation Issues"]
            assert ws_err.cell(row=1, column=1).value == "Excel Row"
            assert ws_err.cell(row=1, column=8).value == "Description"
            # Verify problem rows and full row content are in the Excel sheet
            exported_descriptions = [ws_err.cell(row=r, column=8).value for r in range(2, ws_err.max_row + 1)]
            assert "Milling Cutter Dia 56mm" in exported_descriptions

            # 3. Confirm with resolution (Skip Row 2, Keep First on Row 4)
            conf_res = client.post(
                "/api/v1/inventory/management/confirm",
                json={
                    "file_token": file_token,
                    "month": 10,
                    "year": 2026,
                    "replace_confirmed": False,
                    "resolutions": [
                        {"row": 2, "action": "SKIP_ROW"},
                        {"row": 4, "action": "KEEP_FIRST"},
                    ],
                },
            )
            assert conf_res.status_code == 201
            conf_json = conf_res.json()
            assert len(conf_json["records"]) == 1
            assert conf_json["summary"]["skipped_rows_count"] == 2

            # 4. Download Import Summary (.xlsx)
            sum_res = client.get("/api/v1/inventory/management/import-summary?month=10&year=2026")
            assert sum_res.status_code == 200
            sum_wb = openpyxl.load_workbook(io.BytesIO(sum_res.content))
            assert "Skipped & Resolved Rows" in sum_wb.sheetnames
            assert "Imported Parameters" in sum_wb.sheetnames
            ws_skipped = sum_wb["Skipped & Resolved Rows"]
            assert ws_skipped.max_row == 3  # Header + 2 skipped/resolved rows (Row 2 and Row 4)
