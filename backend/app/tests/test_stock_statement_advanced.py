import io
from decimal import Decimal
from uuid import UUID, uuid4
import openpyxl
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Unit
from app.models.stock_statements import StockStatementBatch, StockStatementLine
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import (
    StockStatementConfirmRequest,
    PromoteConsumablesRequest,
    PromoteConsumableItem,
    DemoteConsumableRequest,
)
from app.security.passwords import PasswordService
from app.services import stock_statement_service as service
from app.services import stock_management_service


PERMISSIONS_FOR_TESTS = [
    "inventory.stock.read",
    "inventory.stock.import",
    "inventory.read",
    "inventory.update",
    "inventory.create",
    "inventory.delete",
    "masters.read",
    "masters.create",
    "masters.update",
]


def create_grouped_opening_stock_wb(
    groups: dict[str, list[dict]],
    banner_loc: str = "Loc. Id. : CONSUMABLES STORE",
    corrupt_group_total: bool = False,
    corrupt_grand_total: bool = False,
) -> bytes:
    """Generate an in-memory grouped Opening_Stock.xlsx workbook for testing."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Row 1: Headers
    ws.append([
        "Item Id.", "Item Description", "Cust.  Part No.", "Unit",
        "Opening Qty.", "Opening Value", "Receipt Qty.", "Receipt Value",
        "Issue Qty.", "Issue Value", "Closing Qty.", "Closing Value"
    ])
    # Row 2: Banner
    ws.append(["KNITVEL NEEDLES"])
    # Row 3: Banner Loc
    ws.append([banner_loc])

    grand_opening_qty = Decimal("0")
    grand_opening_val = Decimal("0")
    grand_closing_qty = Decimal("0")
    grand_closing_val = Decimal("0")

    for grp_name, items in groups.items():
        # Group heading row
        ws.append([grp_name])

        grp_opening_qty = Decimal("0")
        grp_opening_val = Decimal("0")
        grp_closing_qty = Decimal("0")
        grp_closing_val = Decimal("0")

        for item in items:
            oq = Decimal(str(item.get("opening_qty", 0)))
            ov = Decimal(str(item.get("opening_value", 0)))
            rq = Decimal(str(item.get("receipt_qty", 0)))
            rv = Decimal(str(item.get("receipt_value", 0)))
            iq = Decimal(str(item.get("issue_qty", 0)))
            iv = Decimal(str(item.get("issue_value", 0)))
            cq = Decimal(str(item.get("closing_qty", 0)))
            cv = Decimal(str(item.get("closing_value", 0)))

            grp_opening_qty += oq
            grp_opening_val += ov
            grp_closing_qty += cq
            grp_closing_val += cv

            grand_opening_qty += oq
            grand_opening_val += ov
            grand_closing_qty += cq
            grand_closing_val += cv

            ws.append([
                item.get("item_id", ""),
                item.get("description", "Desc"),
                item.get("cust_part_no", ""),
                item.get("unit", "NOS"),
                float(oq), float(ov), float(rq), float(rv),
                float(iq), float(iv), float(cq), float(cv),
            ])

        # Group Total row
        reported_grp_closing_val = float(grp_closing_val + (100 if corrupt_group_total else 0))
        ws.append([
            "Total :", "", "", "",
            float(grp_opening_qty), float(grp_opening_val),
            0.0, 0.0,
            0.0, 0.0,
            float(grp_closing_qty), reported_grp_closing_val,
        ])

    # Grand Total row
    reported_grand_val = float(grand_closing_val + (500 if corrupt_grand_total else 0))
    ws.append([
        "Grand Total :", "", "", "",
        float(grand_opening_qty), float(grand_opening_val),
        0.0, 0.0,
        0.0, 0.0,
        float(grand_closing_qty), reported_grand_val,
    ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def stock_adv_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value)
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    passwords = PasswordService()
    with Session(engine, expire_on_commit=False) as session:
        grants = [Permission(code=p, description=f"Grant {p}") for p in PERMISSIONS_FOR_TESTS]
        role = Role(code="INVENTORY_ADMIN", name="Inventory Admin", permissions=grants)
        user = User(
            username="inv_admin",
            password_hash=passwords.hash("secret123"),
            roles=[role],
        )
        session.add_all([role, user] + grants)

        unit_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
        unit_pcs = Unit(id=uuid4(), code="PCS", name="Pieces")
        session.add_all([unit_nos, unit_pcs])
        session.flush()

        # Create known master consumables
        con1 = Consumable(
            id=uuid4(),
            item_id="CON-001",
            name="Grinding Wheel",
            description="Grinding Wheel 100mm",
            category="CUTTING TOOL",
            unit_id=unit_nos.id,
            rate=Decimal("150.00"),
            is_active=True,
        )
        con2 = Consumable(
            id=uuid4(),
            item_id="CON-002",
            name="Hydraulic Oil 68",
            description="Hydraulic Oil 68 20L",
            category="OIL & GREASES",
            unit_id=unit_nos.id,
            rate=Decimal("3500.00"),
            is_active=True,
        )
        # Inactive dummy rows (like Salt, 1, 2)
        dummy_salt = Consumable(
            id=uuid4(),
            item_id="SALT",
            name="Salt",
            description="Inactive dummy Salt",
            category="MISC",
            unit_id=unit_nos.id,
            rate=Decimal("10.00"),
            is_active=False,
        )
        session.add_all([con1, con2, dummy_salt])
        session.commit()

    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)


# -----------------------------------------------------------------------------
# 1. Grouped Opening Stock Parsing & Reconciliation Tests
# -----------------------------------------------------------------------------
def test_grouped_opening_stock_preview_success(stock_adv_db):
    with Session(stock_adv_db) as session:
        groups = {
            "CUTTING TOOL": [
                {"item_id": "CON-001", "description": "Grinding Wheel", "opening_qty": 10, "opening_value": 1500, "closing_qty": 10, "closing_value": 1500},
                {"item_id": "PRD-TOOL-99", "description": "Custom Bending Tool", "opening_qty": 2, "opening_value": 8000, "closing_qty": 2, "closing_value": 8000},
            ],
            "OIL & GREASES": [
                {"item_id": "CON-002", "description": "Hydraulic Oil", "opening_qty": 5, "opening_value": 17500, "closing_qty": 5, "closing_value": 17500},
            ]
        }
        content = create_grouped_opening_stock_wb(groups)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )

        assert preview.total_rows == 3
        assert preview.consumable_count == 2
        assert preview.product_or_other_count == 1
        assert len(preview.errors) == 0
        assert preview.can_confirm is True


def test_grouped_opening_stock_group_total_mismatch_blocks(stock_adv_db):
    with Session(stock_adv_db) as session:
        groups = {
            "CUTTING TOOL": [
                {"item_id": "CON-001", "description": "Grinding Wheel", "opening_qty": 10, "opening_value": 1500, "closing_qty": 10, "closing_value": 1500},
            ]
        }
        content = create_grouped_opening_stock_wb(groups, corrupt_group_total=True)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )

        assert preview.can_confirm is False
        assert any(e.code == "GROUP_TOTAL_MISMATCH" for e in preview.errors)


def test_grouped_opening_stock_grand_total_mismatch_blocks(stock_adv_db):
    with Session(stock_adv_db) as session:
        groups = {
            "CUTTING TOOL": [
                {"item_id": "CON-001", "description": "Grinding Wheel", "opening_qty": 10, "opening_value": 1500, "closing_qty": 10, "closing_value": 1500},
            ]
        }
        content = create_grouped_opening_stock_wb(groups, corrupt_grand_total=True)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )

        assert preview.can_confirm is False
        assert any(e.code == "GRAND_TOTAL_MISMATCH" for e in preview.errors)


# -----------------------------------------------------------------------------
# 2. Storage of Other Items & Live Class Derivation
# -----------------------------------------------------------------------------
def test_all_rows_stored_and_live_derived(stock_adv_db):
    with Session(stock_adv_db) as session:
        user = session.execute(select(User).where(User.username == "inv_admin")).scalar_one()
        curr_user = CurrentUser(id=user.id, username=user.username, roles=["INVENTORY_ADMIN"], permissions=PERMISSIONS_FOR_TESTS)

        groups = {
            "CUTTING TOOL": [
                {"item_id": "CON-001", "description": "Grinding Wheel", "opening_qty": 10, "opening_value": 1500, "closing_qty": 10, "closing_value": 1500},
                {"item_id": "OTHER-PART-X", "description": "Non-consumable component", "opening_qty": 5, "opening_value": 2500, "closing_qty": 5, "closing_value": 2500},
            ]
        }
        content = create_grouped_opening_stock_wb(groups)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )

        confirm_req = StockStatementConfirmRequest(
            file_token=preview.file_token,
            statement_month=9,
            statement_year=2026,
            replace_confirmed=True,
        )
        res = service.confirm_stock_statement_import(session=session, payload=confirm_req, user=curr_user)
        session.commit()

        # Both rows stored!
        batch_lines = session.execute(
            select(StockStatementLine).where(StockStatementLine.batch_id == UUID(str(res.metadata.batch_id)))
        ).scalars().all()
        assert len(batch_lines) == 2
        line_map = {l.item_id: l for l in batch_lines}
        assert "CON-001" in line_map
        assert "OTHER-PART-X" in line_map
        assert line_map["OTHER-PART-X"].store_group == "CUTTING TOOL"

        # Query via service to verify live derivation
        query_res = service.get_stock_statement(
            session=session,
            month=9,
            year=2026,
            item_class_filter="ALL",
        )
        assert query_res.metadata.row_count == 2
        assert query_res.metadata.consumable_count == 1
        assert query_res.metadata.product_or_other_count == 1
        record_map = {r.item_id: r for r in query_res.records}
        assert record_map["CON-001"].item_class == "CONSUMABLE"
        assert record_map["OTHER-PART-X"].item_class == "OTHER_ITEM"


# -----------------------------------------------------------------------------
# 3. Promote & Demote Workflows
# -----------------------------------------------------------------------------
def test_promote_and_demote_workflow(stock_adv_db):
    with Session(stock_adv_db) as session:
        user = session.execute(select(User).where(User.username == "inv_admin")).scalar_one()
        curr_user = CurrentUser(id=user.id, username=user.username, roles=["INVENTORY_ADMIN"], permissions=PERMISSIONS_FOR_TESTS)

        groups = {
            "PRESS TOOLS": [
                {"item_id": "NEW-PROMOTED-01", "description": "Press Tool Part", "opening_qty": 4, "opening_value": 4000, "closing_qty": 4, "closing_value": 4000},
            ]
        }
        content = create_grouped_opening_stock_wb(groups)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )
        service.confirm_stock_statement_import(
            session=session,
            payload=StockStatementConfirmRequest(file_token=preview.file_token, statement_month=9, statement_year=2026, replace_confirmed=True),
            user=curr_user,
        )
        session.commit()

        # Before promotion: OTHER_ITEM
        statement = service.get_stock_statement(session=session, month=9, year=2026, item_class_filter="ALL")
        assert statement.records[0].item_class == "OTHER_ITEM"

        # Promote NEW-PROMOTED-01
        promote_payload = PromoteConsumablesRequest(
            items=[
                PromoteConsumableItem(
                    item_id="NEW-PROMOTED-01",
                    name="Press Tool Part",
                    description="Press Tool Part",
                    category="PRESS TOOLS",
                    unit_code="NOS",
                    rate=Decimal("1000.00"),
                )
            ]
        )
        promote_res = service.promote_statement_items_to_consumables(
            session=session,
            payload=promote_payload,
            user=curr_user,
        )
        session.commit()
        assert promote_res.promoted_count == 1

        # Check Consumable Master
        con = session.execute(select(Consumable).where(Consumable.item_id == "NEW-PROMOTED-01")).scalar_one()
        assert con.is_active is True
        assert con.source == "stock_statement"

        # Immediately live-derived as CONSUMABLE across stock statements!
        statement_after = service.get_stock_statement(session=session, month=9, year=2026, item_class_filter="ALL")
        assert statement_after.records[0].item_class == "CONSUMABLE"

        # Demote NEW-PROMOTED-01
        demote_payload = DemoteConsumableRequest(
            item_id="NEW-PROMOTED-01",
            reason="Added in error, actually a tooling asset",
        )
        demote_res = service.demote_consumable_item(
            session=session,
            payload=demote_payload,
            user=curr_user,
        )
        session.commit()
        assert demote_res.demoted is True

        # Now inactive in master, so derived as OTHER_ITEM again!
        session.refresh(con)
        assert con.is_active is False
        statement_demoted = service.get_stock_statement(session=session, month=9, year=2026, item_class_filter="ALL")
        assert statement_demoted.records[0].item_class == "OTHER_ITEM"


# -----------------------------------------------------------------------------
# 4. Missing Consumables Query
# -----------------------------------------------------------------------------
def test_missing_consumables_query(stock_adv_db):
    with Session(stock_adv_db) as session:
        user = session.execute(select(User).where(User.username == "inv_admin")).scalar_one()
        curr_user = CurrentUser(id=user.id, username=user.username, roles=["INVENTORY_ADMIN"], permissions=PERMISSIONS_FOR_TESTS)

        # Import statement that contains CON-001, but NOT CON-002
        groups = {
            "CUTTING TOOL": [
                {"item_id": "CON-001", "description": "Grinding Wheel", "opening_qty": 10, "opening_value": 1500, "closing_qty": 10, "closing_value": 1500},
            ]
        }
        content = create_grouped_opening_stock_wb(groups)
        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=content,
            filename="Opening_Stock.xlsx",
            month=9,
            year=2026,
        )
        service.confirm_stock_statement_import(
            session=session,
            payload=StockStatementConfirmRequest(file_token=preview.file_token, statement_month=9, statement_year=2026, replace_confirmed=True),
            user=curr_user,
        )
        session.commit()

        missing = service.get_missing_consumables(session=session, month=9, year=2026)
        # CON-002 is active in master, but not in statement
        missing_ids = [m.item_id for m in missing.items]
        assert "CON-002" in missing_ids
        assert "CON-001" not in missing_ids
        # Inactive master items (SALT) should NOT be in missing list
        assert "SALT" not in missing_ids


# -----------------------------------------------------------------------------
# 5. Stock Management Upload Blocks Inactive/Invalid Placeholders
# -----------------------------------------------------------------------------
def test_stock_management_blocks_invalid_item_id(stock_adv_db):
    with Session(stock_adv_db) as session:
        # Create stock management workbook with "SALT" (inactive dummy)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Item Id", "Category", "Item Description", "Type of Material", "Min Stock Level", "Max Stock Level", "MOQ", "Lead time"])
        ws.append(["SALT", "MISC", "Invalid Salt Placeholder", "General", 10, 50, 10, 5])
        buf = io.BytesIO()
        wb.save(buf)

        preview = stock_management_service.parse_and_preview_stock_parameters(
            session=session,
            content=buf.getvalue(),
            filename="Stockmanagement.xlsx",
            month=10,
            year=2026,
        )
        # Must flag SALT as blocking error because it is not an active consumable
        assert preview.can_confirm is False
        assert any(e.code == "UNKNOWN_ITEM_ID" and "SALT" in e.description for e in preview.errors)
