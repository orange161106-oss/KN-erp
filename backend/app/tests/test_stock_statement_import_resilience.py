import io
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4
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
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Unit
from app.models.stock_statements import StockStatementBatch, StockStatementLine
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import StockStatementConfirmRequest
from app.security.passwords import PasswordService
from app.security.tokens import create_access_token
from app.services import stock_statement_service as service


PERMISSIONS_FOR_IMPORT = [
    "inventory.stock.read",
    "inventory.stock.import",
    "inventory.read",
]


def create_sample_stock_statement_wb(
    rows: list[dict],
    title: str = "STOCK STATEMENT FOR THE MONTH OF SEPTEMBER 2026",
) -> bytes:
    """Generate an in-memory Stock Statement Excel spreadsheet for testing."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Stock Statement"

    ws.append([title])
    ws.append([
        "Item Id", "Item Description", "Cust. Part No.", "Unit",
        "Opening Qty.", "Opening Value", "Receipt Qty.", "Receipt Value",
        "Issue Qty.", "Issue Value", "Closing Qty.", "Closing Value"
    ])

    for r in rows:
        ws.append([
            r.get("item_id", ""),
            r.get("description", "Test Description"),
            r.get("cust_part_no", "CP-001"),
            r.get("unit", "NOS"),
            r.get("opening_qty", 100),
            r.get("opening_value", 5000),
            r.get("receipt_qty", 20),
            r.get("receipt_value", 1000),
            r.get("issue_qty", 10),
            r.get("issue_value", 500),
            r.get("closing_qty", 110),
            r.get("closing_value", 5500),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def stock_statement_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    passwords = PasswordService()
    with Session(engine, expire_on_commit=False) as session:
        grants = [Permission(code=p, description=f"Test grant {p}") for p in PERMISSIONS_FOR_IMPORT]
        role = Role(code="INVENTORY_MGR", name="Inventory Manager", permissions=grants)
        user = User(
            username="inv_operator",
            password_hash=passwords.hash("password"),
            roles=[role],
        )
        session.add_all([role, user] + grants)

        unit_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
        unit_pcs = Unit(id=uuid4(), code="PCS", name="Pieces")
        session.add_all([unit_nos, unit_pcs])
        session.flush()

        consumable1 = Consumable(
            id=uuid4(),
            item_id="LRM120300AA",
            name="Welding Wire 1.2mm",
            unit_id=unit_nos.id,
            is_active=True,
        )
        consumable2 = Consumable(
            id=uuid4(),
            item_id="CN-SPACE-ITEM",
            name="Cleaning Chemical Solv",
            unit_id=unit_nos.id,
            is_active=True,
        )
        session.add_all([consumable1, consumable2])
        session.commit()

    yield engine
    engine.dispose()


@pytest.fixture
def test_actor(stock_statement_db):
    with Session(stock_statement_db) as session:
        user = session.scalar(select(User).where(User.username == "inv_operator"))
        return CurrentUser(
            id=user.id,
            username=user.username,
            roles=["INVENTORY_MGR"],
            permissions=PERMISSIONS_FOR_IMPORT,
        )


def test_valid_item_id_matches_consumable_master(stock_statement_db):
    """Row with valid Item Id matching Consumable Master is parsed with zero blocking errors."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "description": "Welding Wire 1.2mm", "unit": "NOS"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        assert len(preview.errors) == 0
        assert preview.can_confirm is True
        assert preview.total_rows == 1
        assert preview.lines_preview[0].item_id == "LRM120300AA"
        assert preview.lines_preview[0].consumable_id is not None
        # Check token stored
        assert preview.file_token in service._PREVIEW_STORE
        token_entry = service._PREVIEW_STORE[preview.file_token]
        assert token_entry["can_confirm"] is True


def test_unknown_item_id_classified_as_unknown_and_produces_warning(stock_statement_db):
    """Row with Item Id not present in Consumable Master is classified as UNKNOWN with a review warning (does not block confirm)."""
    with Session(stock_statement_db) as session:
        missing_id = "LRM120307QQ"
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": missing_id, "description": "Non-existent child part"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        assert len(preview.errors) == 0
        assert preview.can_confirm is True
        assert preview.unknown_count == 1
        assert missing_id in preview.unknown_items
        assert len(preview.warnings) == 1
        assert preview.warnings[0].severity == "WARNING"
        assert preview.warnings[0].code == "ITEM_UNKNOWN_IN_MASTER"
        assert preview.warnings[0].item_class == "UNKNOWN"

        # Token must still be stored so user can download error report
        assert preview.file_token in service._PREVIEW_STORE
        stored = service._PREVIEW_STORE[preview.file_token]
        assert stored["can_confirm"] is True
        assert len(stored["issues"]) >= 1


def test_empty_item_id_triggers_blocking_error(stock_statement_db):
    """Row with empty Item Id triggers blocking error and blocks confirm."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "", "description": "Row with missing ID"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        assert len(preview.errors) == 1
        assert preview.can_confirm is False
        assert preview.errors[0].severity == "ERROR"
        assert preview.errors[0].code == "EMPTY_ITEM_ID"


def test_item_id_whitespace_and_unicode_space_normalization(stock_statement_db):
    """Leading, trailing, and unicode non-breaking spaces are normalized safely."""
    with Session(stock_statement_db) as session:
        # Non-breaking space \u00a0 and leading/trailing whitespace
        spaced_id = "  CN-SPACE-ITEM \u00a0"
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": spaced_id, "description": "Cleaning Chemical Solv"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        assert len(preview.errors) == 0
        assert preview.can_confirm is True
        assert preview.lines_preview[0].item_id == "CN-SPACE-ITEM"


def test_preview_token_allows_error_report_excel_download(stock_statement_db, test_actor):
    """Uploading a file with validation errors generates a token that yields a formatted Excel error report with 7 columns."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "receipt_qty": -5, "description": "Negative receipt part"},
            {"item_id": "UNKNOWN_PART_1", "description": "Part 1"},
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        assert preview.can_confirm is False
        token = preview.file_token

        # Download error report
        token_entry = service._PREVIEW_STORE.get(token)
        assert token_entry is not None
        issues = token_entry["issues"]
        assert len(issues) >= 2

        report_bytes, filename = service.export_error_report_excel(issues, "Opening Stock.xlsx")
        assert filename == "Error_Report_Opening Stock.xlsx"
        assert not filename.endswith(".xlsx.xlsx")

        # Verify Excel content
        wb = openpyxl.load_workbook(io.BytesIO(report_bytes))
        assert "Validation Issues" in wb.sheetnames
        ws = wb["Validation Issues"]
        assert ws.cell(row=1, column=1).value == "Excel Row"
        assert ws.cell(row=1, column=2).value == "Column"
        assert ws.cell(row=1, column=3).value == "Severity"
        assert ws.cell(row=1, column=4).value == "Code"
        assert ws.cell(row=1, column=5).value == "Item Id"
        assert ws.cell(row=1, column=6).value == "Item Class"
        assert ws.cell(row=1, column=7).value == "Description"

        # Check data rows
        severities = [ws.cell(row=r, column=3).value for r in range(2, ws.max_row + 1)]
        assert "ERROR" in severities
        assert "WARNING" in severities


def test_missing_or_expired_token_returns_404():
    """Attempting to download error report or confirm with expired/invalid token raises 404."""
    # 1. Non-existent token
    fake_token = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ApplicationError) as exc_info:
        # Check confirmation
        fake_req = StockStatementConfirmRequest(
            file_token=fake_token,
            statement_month=9,
            statement_year=2026,
        )
        fake_user = CurrentUser(id=uuid4(), username="test", roles=[], permissions=[])
        service.confirm_stock_statement_import(None, payload=fake_req, user=fake_user)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "EXPIRED_TOKEN"

    # 2. Expired TTL token
    expired_token = "expired-token-123"
    service._PREVIEW_STORE[expired_token] = {
        "created_at": time.time() - 4000,  # Older than 3600s
        "can_confirm": True,
        "month": 9,
        "year": 2026,
    }
    with pytest.raises(ApplicationError) as exc_info2:
        fake_req2 = StockStatementConfirmRequest(
            file_token=expired_token,
            statement_month=9,
            statement_year=2026,
        )
        service.confirm_stock_statement_import(None, payload=fake_req2, user=fake_user)
    assert exc_info2.value.status_code == 404
    assert exc_info2.value.code == "EXPIRED_TOKEN"
    assert expired_token not in service._PREVIEW_STORE


def test_confirmation_blocked_when_blocking_errors_exist(stock_statement_db, test_actor):
    """Direct confirm call on a preview session with errors is rejected with 422 VALIDATION_FAILED."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "receipt_qty": -10, "description": "Negative receipt"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )
        assert preview.can_confirm is False

        confirm_req = StockStatementConfirmRequest(
            file_token=preview.file_token,
            statement_month=9,
            statement_year=2026,
        )

        with pytest.raises(ApplicationError) as exc_info:
            service.confirm_stock_statement_import(
                session=session,
                payload=confirm_req,
                user=test_actor,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "VALIDATION_FAILED"

        # Check that no batches or lines were inserted in database
        batches = session.scalars(select(StockStatementBatch)).all()
        assert len(batches) == 0


def test_preview_is_strictly_read_only(stock_statement_db):
    """Calling preview never creates or modifies database records."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "description": "Welding Wire 1.2mm"}
        ])

        service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )

        batches = session.scalars(select(StockStatementBatch)).all()
        lines = session.scalars(select(StockStatementLine)).all()
        assert len(batches) == 0
        assert len(lines) == 0


def test_confirmation_atomic_commit_and_token_consumption(stock_statement_db, test_actor):
    """Confirmation commits valid batch, marks existing superseded, and consumes token."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "description": "Welding Wire 1.2mm"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )
        assert preview.can_confirm is True
        token = preview.file_token
        assert token in service._PREVIEW_STORE

        confirm_req = StockStatementConfirmRequest(
            file_token=token,
            statement_month=9,
            statement_year=2026,
        )

        result = service.confirm_stock_statement_import(
            session=session,
            payload=confirm_req,
            user=test_actor,
        )

        assert result.metadata.has_statement is True
        assert result.metadata.statement_month == 9
        assert result.metadata.statement_year == 2026
        assert len(result.records) == 1
        assert result.records[0].item_id == "LRM120300AA"

        # Check DB records
        batches = session.scalars(select(StockStatementBatch).where(StockStatementBatch.status == "active")).all()
        assert len(batches) == 1
        assert batches[0].statement_month == 9

        # Verify token was consumed upon confirmation
        assert token not in service._PREVIEW_STORE

        # Retry confirmation with same consumed token must fail
        with pytest.raises(ApplicationError) as exc_info:
            service.confirm_stock_statement_import(
                session=session,
                payload=confirm_req,
                user=test_actor,
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "EXPIRED_TOKEN"


def test_confirmation_rolls_back_on_failure(stock_statement_db, test_actor):
    """If an unhandled database exception occurs during confirmation, transaction rolls back."""
    with Session(stock_statement_db) as session:
        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "description": "Welding Wire 1.2mm"}
        ])

        preview = service.parse_and_preview_stock_statement(
            session=session,
            content=excel_bytes,
            filename="Opening Stock.xlsx",
            month=9,
            year=2026,
        )
        token = preview.file_token

        confirm_req = StockStatementConfirmRequest(
            file_token=token,
            statement_month=9,
            statement_year=2026,
        )

        # Force a database error during session.commit
        with patch.object(session, "commit", side_effect=RuntimeError("Simulated DB commit error")):
            with pytest.raises(RuntimeError, match="Simulated DB commit error"):
                service.confirm_stock_statement_import(
                    session=session,
                    payload=confirm_req,
                    user=test_actor,
                )

        # Verify no batch was persisted
        batches = session.scalars(select(StockStatementBatch)).all()
        assert len(batches) == 0


def test_http_preview_and_preview_errors_endpoint(stock_statement_db):
    """End-to-end HTTP integration test: upload preview with errors, then download error report."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user@127.0.0.1/kn_unit_test",
        auth_secret_key="test-secret-key-for-stock-statement-testing-32b",
    )
    with Session(stock_statement_db) as session:
        user = session.scalar(select(User).where(User.username == "inv_operator"))
        app = create_app(settings)

        def override_db():
            with Session(stock_statement_db, expire_on_commit=False, autoflush=False) as s:
                yield s

        app.dependency_overrides[get_db] = override_db
        token = create_access_token(user.id, settings)

        excel_bytes = create_sample_stock_statement_wb([
            {"item_id": "LRM120300AA", "receipt_qty": -10, "description": "Negative Receipt"}
        ])

        with TestClient(app) as client:
            client.headers.update({"Authorization": f"Bearer {token}"})

            # 1. POST /preview
            preview_res = client.post(
                "/api/v1/inventory/statement/preview",
                data={"statement_month": 9, "statement_year": 2026},
                files={"file": ("Opening Stock.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
            assert preview_res.status_code == 200
            data = preview_res.json()
            assert data["can_confirm"] is False
            file_token = data["file_token"]
            assert file_token

            # 2. GET /preview-errors
            err_res = client.get(f"/api/v1/inventory/statement/preview-errors?file_token={file_token}")
            assert err_res.status_code == 200
            assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in err_res.headers["content-type"]
            assert "attachment;" in err_res.headers["content-disposition"]
            assert ("Error_Report_Opening Stock.xlsx" in err_res.headers["content-disposition"]
                    or "Error_Report_Opening%20Stock.xlsx" in err_res.headers["content-disposition"])

            # Parse returned spreadsheet
            wb = openpyxl.load_workbook(io.BytesIO(err_res.content))
            assert "Validation Issues" in wb.sheetnames
            ws = wb["Validation Issues"]
            assert ws.cell(row=1, column=1).value == "Excel Row"
            assert ws.cell(row=1, column=3).value == "Severity"
            assert ws.cell(row=1, column=4).value == "Code"
            assert ws.cell(row=2, column=3).value == "ERROR"
            assert ws.cell(row=2, column=4).value == "NEGATIVE_RECEIPT"

            # 3. GET /preview-errors with non-existent token returns 404
            bad_res = client.get("/api/v1/inventory/statement/preview-errors?file_token=non-existent-token")
            assert bad_res.status_code == 404
            bad_data = bad_res.json()
            assert bad_data["code"] == "EXPIRED_TOKEN"


