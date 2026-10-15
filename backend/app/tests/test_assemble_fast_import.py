import io
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductProcessConsumable
from app.models.masters import Product
from app.models.production import Process
from app.services import product_master_service as service


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda val: val.strip() if val else "")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        user = User(id=uuid4(), username="admin", password_hash="secret", is_super_admin=True)
        session.add(user)
        session.commit()
        yield session, engine, user


def make_assemble_workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_fast_parse_streaming_drops_banners_and_stops_on_empty():
    """Verify openpyxl streaming finds header below banners and stops early on trailing blank rows."""
    banner_rows = [
        ["COMPANY CONFIDENTIAL", "", ""],
        ["REPORT: BILL OF MATERIALS", "DATE: 2026-10-13", ""],
        ["", "", ""],
        [
            "Consumable Description",
            "Part No. of saleable item",
            "Used for- Name of Saleable part",
            "Used Part no (prd order)",
            "Process name",
            "Material thickness in mm / Gsm",
            "No of process per part",
            "Output/ Unit",
            "Rate",
        ],
        ["Oil ISO VG 68", "PN-101", "Cylinder Block", "PRD-01", "ASSEMBLY", "1.5mm", "2.0", "L", "350.00"],
        ["Bolt M12x40", "PN-102", "Flywheel", "PRD-02", "ASSEMBLY", "", "4.0", "PCS", "12.50"],
    ]
    # Add 500 blank trailing rows to simulate inflated used range
    for _ in range(500):
        banner_rows.append([None, None, None, None, None, None, None, None, None])

    file_bytes = make_assemble_workbook(banner_rows)

    start = time.perf_counter()
    header_row, matched_cols, parsed_rows, issues = service.fast_parse_assemble_excel(file_bytes, "test.xlsx")
    elapsed = time.perf_counter() - start

    assert header_row == 4
    assert "consumable_item" in matched_cols
    assert "part_no_saleable_item" in matched_cols
    assert len(parsed_rows) == 2
    assert elapsed < 0.25, f"Expected streaming parse in < 0.25s, got {elapsed:.3f}s"


def test_constant_sql_query_count_for_large_batches(test_db):
    """Verify constant O(1) query count regardless of row count (e.g. 50 vs 200 vs 500 rows)."""
    session, engine, user = test_db

    for count in [50, 150, 300]:
        rows = [
            [
                "Consumable Description",
                "Part No. of saleable item",
                "Used for- Name of Saleable part",
                "Process name",
                "No of process per part",
                "Output/ Unit",
                "Rate",
            ]
        ]
        for i in range(count):
            rows.append([
                f"Consumable_{i % 10}",
                f"Part_{i}",
                f"Description for part {i}",
                "ASSEMBLY",
                "1.0",
                "PCS",
                "100.00",
            ])
        file_bytes = make_assemble_workbook(rows)
        _hr, _mc, parsed_rows, _iss = service.fast_parse_assemble_excel(file_bytes)

        query_count = 0

        @event.listens_for(engine, "before_cursor_execute")
        def count_queries(conn, cursor, statement, parameters, context, executemany):
            nonlocal query_count
            query_count += 1

        service.execute_assemble_import_batch(session, parsed_rows, user.id)

        event.remove(engine, "before_cursor_execute", count_queries)

        # For any row count up to 500, total SQL statements must be constant (<= 15 queries)
        assert query_count <= 15, f"Expected <= 15 queries for {count} rows, got {query_count}"


def test_idempotent_upsert_and_preview_classification(test_db):
    """Verify that uploading twice updates records rather than duplicating, and preview detects adds vs updates."""
    session, engine, user = test_db

    rows = [
        ["Consumable Description", "Part No. of saleable item", "Rate"],
        ["Lubricant Grease", "PN-2001", "50.00"],
        ["Lock Nut M8", "PN-2002", "5.50"],
    ]
    file_bytes = make_assemble_workbook(rows)

    # 1. Preview first upload: both should be additions
    preview1 = service.preview_assemble_import(session, file_bytes, "first.xlsx", user.id)
    assert preview1.rows_to_add == 2
    assert preview1.rows_to_update == 0

    # Confirm and execute first upload
    res1 = service.confirm_assemble_import(session, preview1.file_token, user.id)
    assert res1.upserted == 2

    # 2. Preview second upload (with updated rate on row 1 and same row 2): both should be updates
    rows_update = [
        ["Consumable Description", "Part No. of saleable item", "Rate"],
        ["Lubricant Grease", "PN-2001", "75.00"],
        ["Lock Nut M8", "PN-2002", "5.50"],
    ]
    file_bytes_up = make_assemble_workbook(rows_update)
    preview2 = service.preview_assemble_import(session, file_bytes_up, "second.xlsx", user.id)
    assert preview2.rows_to_update == 2
    assert preview2.rows_to_add == 0

    # Confirm and execute second upload
    res2 = service.confirm_assemble_import(session, preview2.file_token, user.id)
    assert res2.upserted == 2

    # Verify no duplicates in database
    mappings = session.scalars(select(ProductProcessConsumable)).all()
    assert len(mappings) == 2
    updated_rec = session.scalars(
        select(ProductProcessConsumable).where(ProductProcessConsumable.part_no_saleable_item == "PN-2001")
    ).first()
    assert updated_rec.rate == Decimal("75.00")


def test_validation_reporting_and_excel_export(test_db):
    """Verify that row issues are reported and error excel is generated correctly."""
    session, engine, user = test_db

    rows = [
        ["Consumable Description", "Part No. of saleable item", "Qty", "Rate"],
        ["", "PN-3001", "1", "10"],               # Missing consumable
        ["Grease", "", "2", "20"],                # Missing part no
        ["Grease", "PN-3002", "invalid_qty", "30"], # Invalid qty
        ["Grease", "PN-3002", "1", "40"],         # Duplicate row in file
    ]
    file_bytes = make_assemble_workbook(rows)
    preview = service.preview_assemble_import(session, file_bytes, "issues.xlsx", user.id)

    assert preview.error_count >= 2
    assert preview.warning_count >= 2

    # Export errors to Excel
    issues = service._ASSEMBLE_PREVIEW_STORE[preview.file_token]["issues"]
    excel_bytes = service.export_assemble_errors_excel(issues)
    assert len(excel_bytes) > 0

    # Parse generated Excel
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active
    assert ws.title == "Validation Issues"
    assert ws.cell(row=1, column=1).value == "Row"
    assert ws.cell(row=1, column=3).value == "Error Code"
    assert ws.max_row >= 4


def test_confirm_job_threshold_and_status(test_db):
    """Verify synchronous execution for <= 200 rows and job status reporting."""
    session, engine, user = test_db

    rows = [
        ["Consumable Description", "Part No. of saleable item"],
        ["Hex Bolt", "PN-4001"],
    ]
    file_bytes = make_assemble_workbook(rows)
    preview = service.preview_assemble_import(session, file_bytes, "small.xlsx", user.id)

    # Confirm import
    job_res = service.confirm_assemble_import(
        session,
        preview.file_token,
        user.id,
    )
    assert job_res.status == "completed"
    assert job_res.upserted == 1
    assert job_res.progress_percent == 100

    # Query job status
    status_res = service.get_assemble_job_status(job_res.job_id)
    assert status_res.status == "completed"


def test_db_retry_helper():
    """Verify execute_with_db_retry retries on transient OperationalError."""
    call_count = 0

    def flaky_db_op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OperationalError("connection lost", {}, Exception())
        return "SUCCESS"

    result = service.execute_with_db_retry(flaky_db_op, max_retries=1)
    assert result == "SUCCESS"
    assert call_count == 2
