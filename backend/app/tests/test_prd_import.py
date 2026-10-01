from decimal import Decimal
import io
from uuid import uuid4
import openpyxl
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import ApplicationError
from app.db.base import Base
from app.models.auth import User
from app.models.masters import Product
from app.models.prd import ImportBatch, ImportError, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.services.prd import (
    PRDValidationError,
    promote_batch_to_planning_version,
    stage_and_validate_prd_file,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("btrim", 1, lambda s: s.strip() if s is not None else None)

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_excel_bytes(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(username="test_planner", password_hash="dummy_hash", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def seed_products(db_session: Session) -> list[Product]:
    p1 = Product(code="BRACKET-01", name="Bracket Type 1", uom="PCS", is_active=True)
    p2 = Product(code="BRACKET-02", name="Bracket Type 2", uom="PCS", is_active=True)
    db_session.add_all([p1, p2])
    db_session.commit()
    return [p1, p2]


def test_valid_file(db_session: Session, test_user: User, seed_products: list[Product]):
    content = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "UOM", "Target Period"],
        ["BRACKET-01", "PLANT-1", 100, "PCS", "2026-10"],
        ["BRACKET-02", "PLANT-1", 250.5, "PCS", "2026-10"],
    ])

    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="valid_prd.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )

    assert batch.status == "VALIDATED"
    assert batch.row_count == 2
    assert batch.valid_row_count == 2
    assert batch.error_row_count == 0
    assert len(batch.errors) == 0

    # Promote to planning version
    version, header, line_count = promote_batch_to_planning_version(
        db=db_session,
        batch_id=batch.id,
        user_id=test_user.id,
        planning_period="2026-10",
        revision_label="R0",
    )

    assert version.status == "VALIDATED"
    assert version.revision_label == "R0"
    assert header.total_planned_qty == Decimal("350.5000")
    assert header.total_line_items == 2
    assert line_count == 2

    # Check canonical items
    items = db_session.scalars(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == version.id)).all()
    assert len(items) == 2
    assert {i.product_code for i in items} == {"BRACKET-01", "BRACKET-02"}


def test_missing_header(db_session: Session, test_user: User, seed_products: list[Product]):
    # Missing 'Plant Code'
    content = create_excel_bytes([
        ["Product Code", "Planned Quantity", "Target Period"],
        ["BRACKET-01", 100, "2026-10"],
    ])

    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="missing_header.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )

    assert batch.status == "FAILED"
    assert batch.error_row_count == 1
    assert len(batch.errors) == 1
    assert batch.errors[0].error_code == "MISSING_HEADERS"
    assert "Plant Code" in batch.errors[0].error_message


def test_invalid_qty(db_session: Session, test_user: User, seed_products: list[Product]):
    content = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "Target Period"],
        ["BRACKET-01", "PLANT-1", -15, "2026-10"],       # Negative qty
        ["BRACKET-01", "PLANT-2", "not_a_number", "2026-10"], # String qty
        ["BRACKET-02", "PLANT-1", 0, "2026-10"],         # Zero qty
    ])

    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="invalid_qty.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )

    assert batch.status == "FAILED"
    assert batch.error_row_count == 3
    error_codes = [e.error_code for e in batch.errors]
    assert error_codes == ["INVALID_QUANTITY", "INVALID_QUANTITY", "INVALID_QUANTITY"]


def test_duplicate_row(db_session: Session, test_user: User, seed_products: list[Product]):
    content = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "Target Period"],
        ["BRACKET-01", "PLANT-1", 100, "2026-10"],
        ["BRACKET-01", "PLANT-1", 200, "2026-10"],  # Duplicate product+plant+period
    ])

    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="duplicate.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )

    assert batch.status == "FAILED"
    assert any(e.error_code == "DUPLICATE_ROW" for e in batch.errors)


def test_unknown_product(db_session: Session, test_user: User, seed_products: list[Product]):
    content = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "Target Period"],
        ["BRACKET-UNKNOWN-999", "PLANT-1", 100, "2026-10"],
    ])

    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="unknown_product.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )

    assert batch.status == "FAILED"
    assert any(e.error_code == "UNKNOWN_PRODUCT" for e in batch.errors)

    # Verify BRACKET-UNKNOWN-999 was NOT auto-created
    unknown = db_session.scalars(select(Product).where(Product.code == "BRACKET-UNKNOWN-999")).first()
    assert unknown is None


def test_empty_file(db_session: Session, test_user: User):
    # 0 bytes
    with pytest.raises(PRDValidationError) as exc_info:
        stage_and_validate_prd_file(
            db=db_session,
            file_bytes=b"",
            filename="empty.xlsx",
            planning_period="2026-10",
            user_id=test_user.id,
        )
    assert exc_info.value.code == "EMPTY_FILE"

    # Headers only, 0 data rows
    content = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "Target Period"],
    ])
    batch = stage_and_validate_prd_file(
        db=db_session,
        file_bytes=content,
        filename="headers_only.xlsx",
        planning_period="2026-10",
        user_id=test_user.id,
    )
    assert batch.status == "FAILED"
    assert any(e.error_code == "NO_DATA_ROWS" for e in batch.errors)


def test_wrong_type(db_session: Session, test_user: User):
    with pytest.raises(PRDValidationError) as exc_info:
        stage_and_validate_prd_file(
            db=db_session,
            file_bytes=b"some,csv,data\n1,2,3",
            filename="data.csv",
            planning_period="2026-10",
            user_id=test_user.id,
        )
    assert exc_info.value.code == "INVALID_FILE_TYPE"
