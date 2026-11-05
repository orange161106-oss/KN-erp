import io
from decimal import Decimal
from uuid import uuid4

import openpyxl
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import ApplicationError
from app.db.base import Base
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.requirement_requests import RequirementRequest, RequirementRequestBatch
from app.schemas.auth import CurrentUser
from app.services import requirement_requests as service


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.create_function('btrim', 1, lambda v: v.strip())
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _create_mock_excel(sheets_data: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets_data.items():
        ws = wb.create_sheet(title=title)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def mock_consumables(db):
    u_nos = Unit(id=uuid4(), code="NOS", name="Numbers")
    u_kgs = Unit(id=uuid4(), code="KGS", name="Kilograms")
    u_ltrs = Unit(id=uuid4(), code="LTRS", name="Liters")
    db.add_all([u_nos, u_kgs, u_ltrs])
    db.flush()

    c1 = Consumable(
        id=uuid4(),
        item_id="ABK100003QC",
        name='Gloves - Knitted - 12"',
        unit_id=u_nos.id,
        purchasing_unit="NOS",
        is_active=True,
    )
    c2 = Consumable(
        id=uuid4(),
        item_id="PEQ000001QC",
        name="Accepted Tag",
        unit_id=u_nos.id,
        purchasing_unit="NOS",
        is_active=True,
    )
    c3 = Consumable(
        id=uuid4(),
        item_id="BBG000090QC",
        name="Anabond - 202",
        unit_id=u_kgs.id,
        purchasing_unit="KGS",
        is_active=True,
    )
    c4 = Consumable(
        id=uuid4(),
        item_id="FDQ000003QC",
        name="Soap oil",
        unit_id=u_ltrs.id,
        purchasing_unit="LTRS",
        is_active=True,
    )
    db.add_all([c1, c2, c3, c4])
    db.commit()
    return {"ABK100003QC": c1, "PEQ000001QC": c2, "BBG000090QC": c3, "FDQ000003QC": c4}


def test_dynamic_header_and_shifted_columns(db, mock_consumables):
    data = {
        "Plant 1": [
            [None, None, None, None, None, "Month", "Oct'26", "Sept'26"],
            [None, "S.no.", "Item Id.", "Item Description", "Part No.", "Unit", "QTY", "QTY"],
            ["PLANT I", 1, "ABK100003QC", 'Gloves - Knitted - 12"', None, "NOS", 100, 50],
            ["PLANT I", 2, "PEQ000001QC", "Accepted Tag", None, "NOS", 0, 10],  # zero qty -> skip
            ["PLANT I", 3, "UNKNOWN01QC", "Unknown Item", None, "NOS", 25, 25],  # unknown -> listed
        ],
        "PMD": [
            [None, ",", "PMD & TOOL MAINTENANCE", None, None, "Oct' 26"],
            ["To Location", "Item Id.", "Item Description", "Part No.", "Unit", "Qty"],
            ["PMD", "ABK100003QC", 'Gloves - Knitted - 12"', None, "NOS", 150],
            ["PMD", "ABK100003QC", 'Gloves - Knitted - 12"', None, "NOS", 50],  # duplicate in sheet -> skip
        ],
        "HRD": [
            [None, None],
            ["HRD", None],
            [None, None, None, None, "Oct'26"],
            ["ITEM ID", "DESCRIPTION", "PART NO", "UNIT ", "Qty"],
            ["FDQ000003QC", "Soap oil", None, "LTRS", 910],
            ["Resharpenning", "Invalid item", None, "NOS", 10],  # invalid ID format -> skip
        ],
    }
    content = _create_mock_excel(data)

    preview = service.preview_requirement_requests_workbook(
        session=db,
        file_bytes=content,
        filename="Oct_Requests.xlsx",
        planning_month=10,
        planning_year=2026,
    )

    assert preview.can_confirm is True
    assert preview.total_valid_requests == 3  # Plant 1 ABK, PMD ABK, HRD FDQ
    assert preview.total_unknown_ids == 1
    assert preview.unknown_items[0].item_id == "UNKNOWN01QC"
    assert preview.total_zero_skipped >= 1
    assert len(preview.duplicates) == 1
    assert preview.duplicates[0].item_id == "ABK100003QC"

    # Create user in DB
    user = User(
        id=uuid4(),
        username="planner_user",
        password_hash="hash",
        requests_create=True,
        requests_read=True,
    )
    db.add(user)
    db.commit()

    actor = CurrentUser(
        id=user.id,
        username=user.username,
        roles=["PLANNER"],
        permissions=["requests:create"],
        requests_create=True,
        requests_read=True,
    )

    confirm_res = service.confirm_requirement_requests(
        session=db,
        request=service.RequirementRequestConfirmRequest(
            filename="Oct_Requests.xlsx",
            planning_month=10,
            planning_year=2026,
            file_hash=preview.file_hash,
            review_token=preview.review_token,
        ),
        preview=preview,
        actor=actor,
    )

    assert confirm_res.imported_row_count == 3
    assert confirm_res.imported_batch_count == 3

    # Check database state
    active_reqs = db.scalars(
        select(RequirementRequest).where(
            RequirementRequest.planning_month == 10,
            RequirementRequest.planning_year == 2026,
            RequirementRequest.status == "ACTIVE",
        )
    ).all()
    assert len(active_reqs) == 3

    # Verify unknown item export CSV
    csv_bytes = service.export_unknown_items_csv(preview.unknown_items)
    csv_text = csv_bytes.decode("utf-8")
    assert "UNKNOWN01QC" in csv_text
    assert "Item ID not found in consumable master" in csv_text


def test_t6_reimport_does_not_double(db, mock_consumables):
    """T6: Importing the same month and source twice does not double the quantities."""
    data = {
        "Plant 1": [
            [None, None, None, None, None, "Month", "Oct'26"],
            [None, "S.no.", "Item Id.", "Item Description", "Part No.", "Unit", "QTY"],
            ["PLANT I", 1, "ABK100003QC", "Gloves", None, "NOS", 100],
        ]
    }
    content = _create_mock_excel(data)

    user = User(
        id=uuid4(),
        username="planner_user_t6",
        password_hash="hash",
        requests_create=True,
        requests_read=True,
    )
    db.add(user)
    db.commit()

    actor = CurrentUser(
        id=user.id,
        username=user.username,
        roles=["PLANNER"],
        permissions=["requests:create"],
        requests_create=True,
        requests_read=True,
    )

    # First import
    preview1 = service.preview_requirement_requests_workbook(db, content, "Oct.xlsx", 10, 2026)
    service.confirm_requirement_requests(
        db,
        service.RequirementRequestConfirmRequest(
            filename="Oct.xlsx",
            planning_month=10,
            planning_year=2026,
            file_hash=preview1.file_hash,
            review_token=preview1.review_token,
        ),
        preview1,
        actor,
    )

    reqs_after_1 = db.scalars(
        select(RequirementRequest).where(
            RequirementRequest.planning_month == 10,
            RequirementRequest.planning_year == 2026,
            RequirementRequest.source_code == "P1",
            RequirementRequest.status == "ACTIVE",
        )
    ).all()
    assert len(reqs_after_1) == 1
    assert reqs_after_1[0].quantity == Decimal("100.0000")

    # Second import with updated quantity 120
    data["Plant 1"][2][6] = 120
    content2 = _create_mock_excel(data)
    preview2 = service.preview_requirement_requests_workbook(db, content2, "Oct_v2.xlsx", 10, 2026)
    assert preview2.existing_batches_warning is not None

    service.confirm_requirement_requests(
        db,
        service.RequirementRequestConfirmRequest(
            filename="Oct_v2.xlsx",
            planning_month=10,
            planning_year=2026,
            file_hash=preview2.file_hash,
            review_token=preview2.review_token,
        ),
        preview2,
        actor,
    )

    # Active requests must be 1, NOT 2, and quantity must be replaced with 120
    active_reqs = db.scalars(
        select(RequirementRequest).where(
            RequirementRequest.planning_month == 10,
            RequirementRequest.planning_year == 2026,
            RequirementRequest.source_code == "P1",
            RequirementRequest.status == "ACTIVE",
        )
    ).all()
    assert len(active_reqs) == 1
    assert active_reqs[0].quantity == Decimal("120.0000")

    # Superseded requests exist for history
    superseded = db.scalars(
        select(RequirementRequest).where(
            RequirementRequest.planning_month == 10,
            RequirementRequest.planning_year == 2026,
            RequirementRequest.source_code == "P1",
            RequirementRequest.status == "SUPERSEDED",
        )
    ).all()
    assert len(superseded) == 1
    assert superseded[0].quantity == Decimal("100.0000")


def test_t10_permission_and_audit(db, mock_consumables):
    """T10: A user without the 'requests' permission gets 403 on import/edit; every change is audit-logged."""
    data = {
        "PMD": [
            [None, ",", "PMD & TOOL MAINTENANCE", None, None, "Oct'26"],
            ["To Location", "Item Id.", "Item Description", "Part No.", "Unit", "Qty"],
            ["PMD", "ABK100003QC", "Gloves", None, "NOS", 150],
        ]
    }
    content = _create_mock_excel(data)
    preview = service.preview_requirement_requests_workbook(db, content, "PMD.xlsx", 10, 2026)

    # User without requests_create permission
    unauthorized_user = CurrentUser(
        id=uuid4(),
        username="unauthorized_operator",
        roles=["OPERATOR"],
        permissions=[],
        requests_create=False,
        requests_read=True,
    )

    with pytest.raises(ApplicationError) as exc_info:
        service.confirm_requirement_requests(
            session=db,
            request=service.RequirementRequestConfirmRequest(
                filename="PMD.xlsx",
                planning_month=10,
                planning_year=2026,
                file_hash=preview.file_hash,
                review_token=preview.review_token,
            ),
            preview=preview,
            actor=unauthorized_user,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"
    assert exc_info.value.status_code == 403

    # Authorized user
    user = User(
        id=uuid4(),
        username="plant_incharge_user",
        password_hash="hash",
        requests_create=True,
        requests_read=True,
    )
    db.add(user)
    db.commit()

    authorized_user = CurrentUser(
        id=user.id,
        username=user.username,
        roles=["PLANT_INCHARGE"],
        permissions=["requests:create"],
        requests_create=True,
        requests_read=True,
    )

    res = service.confirm_requirement_requests(
        session=db,
        request=service.RequirementRequestConfirmRequest(
            filename="PMD.xlsx",
            planning_month=10,
            planning_year=2026,
            file_hash=preview.file_hash,
            review_token=preview.review_token,
        ),
        preview=preview,
        actor=authorized_user,
    )
    assert res.imported_row_count == 1

    # Verify audit log was recorded
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_id == authorized_user.id,
            AuditLog.action == "IMPORT_REQUIREMENT_REQUESTS",
        )
    )
    assert audit is not None
    assert audit.entity_type == "requirement_request_batch"

