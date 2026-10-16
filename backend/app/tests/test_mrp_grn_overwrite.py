from datetime import datetime, timezone
from decimal import Decimal
import io
from uuid import uuid4

from fastapi.testclient import TestClient
import openpyxl
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import Role, User
from app.models.inventory_masters import Consumable, Unit
from app.models.prd import PlanningVersion
from app.models.requirements import MonthlyRequirementRecord
from app.security.tokens import create_access_token


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda val: val.strip() if val else "")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_setup(db_session):
    settings = app.state.settings

    admin_role = Role(code="ADMIN", name="Administrator")
    db_session.add(admin_role)

    admin_user = User(
        id=uuid4(),
        username="admin_user",
        password_hash="secret",
        is_super_admin=True,
        roles=[admin_role],
    )
    db_session.add(admin_user)

    unit_nos = Unit(name="NOS", code="NOS")
    db_session.add(unit_nos)

    c1 = Consumable(
        id=uuid4(),
        code="WLD-WIRE-01",
        name="MIG Welding Wire 1.2mm",
        output_unit="NOS",
        latest_grn_rate=Decimal("400.00"),
    )
    c2 = Consumable(
        id=uuid4(),
        code="PNT-THIN-01",
        name="Industrial Thinner",
        output_unit="NOS",
        latest_grn_rate=Decimal("150.00"),
    )
    db_session.add_all([c1, c2])

    version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        status="DRAFT",
        revision_label="R0",
        source_filename="test_october.xlsx",
        created_by=admin_user.id,
    )
    db_session.add(version)

    # Pre-existing monthly requirement record for WLD-WIRE-01
    rec1 = MonthlyRequirementRecord(
        id=uuid4(),
        planning_version_id=version.id,
        planning_period="2026-10",
        planning_month=10,
        planning_year=2026,
        part_name="Door Panel",
        part_number="DP-100",
        consumable_code="WLD-WIRE-01",
        consumable_name="MIG Welding Wire 1.2mm",
        process_name="Welding",
        unit="NOS",
        plant="Plant 1",
        plant_id="PLANT_1",
        scheduled_consumable_qty=Decimal("1000.0000"),
        gross_requirement=Decimal("1000.0000"),
        opening_stock=Decimal("200.0000"),
        grn_received_qty=Decimal("100.0000"),  # Tentative prior value
        consumed_qty=Decimal("50.0000"),
        closing_stock=Decimal("250.0000"),  # (200 + 100) - 50 = 250
        net_order_requirement=Decimal("750.0000"),  # max(0, 1000 - 250) = 750
        stock_qty=Decimal("250.0000"),
        shortage_qty=Decimal("750.0000"),
    )
    db_session.add(rec1)
    db_session.commit()

    token = create_access_token(admin_user.id, settings)
    auth_headers = {"Authorization": f"Bearer {token}"}

    return {
        "admin_user": admin_user,
        "auth_headers": auth_headers,
        "consumable_1": c1,
        "consumable_2": c2,
        "version": version,
        "rec1": rec1,
    }


def test_mrp_grn_overwrite_and_deterministic_recalc(client, db_session, test_setup):
    headers = test_setup["auth_headers"]

    # 1. Upload GRN CSV with updated received qty of 500 for WLD-WIRE-01
    csv_content = (
        "item_code,grn_qty,invoice_no,grn_date,rate\n"
        "WLD-WIRE-01,500.00,INV-OCT-001,2026-10-15,450.00\n"
    )
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    response = client.post(
        "/api/v1/mrp/upload-grn",
        headers=headers,
        data={
            "plant_id": "PLANT_1",
            "planning_month": 10,
            "planning_year": 2026,
        },
        files={"file": ("store_grn_oct.csv", csv_file, "text/csv")},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert data["updated_count"] == 1
    assert data["inserted_count"] == 0
    assert data["period"] == "2026-10"

    # Verify database state for WLD-WIRE-01:
    rec = db_session.scalar(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.consumable_code == "WLD-WIRE-01",
            MonthlyRequirementRecord.planning_month == 10,
            MonthlyRequirementRecord.planning_year == 2026,
        )
    )
    assert rec is not None
    # Overwrite check: was 100, now must be 500 (NOT 600)
    assert rec.grn_received_qty == Decimal("500.0000")
    # Recalculation: closing = (opening 200 + grn 500) - consumed 50 = 650
    assert rec.closing_stock == Decimal("650.0000")
    assert rec.stock_qty == Decimal("650.0000")
    # Net order requirement: max(0, gross 1000 - closing 650) = 350
    assert rec.net_order_requirement == Decimal("350.0000")
    assert rec.shortage_qty == Decimal("350.0000")
    assert rec.grn_source_file == "store_grn_oct.csv"
    assert rec.invoice_no == "INV-OCT-001"
    assert rec.last_synced_at is not None

    # Check consumable catalog rate was also updated
    c1 = db_session.get(Consumable, test_setup["consumable_1"].id)
    assert c1.latest_grn_rate == Decimal("450.00")


def test_mrp_grn_reupload_replaces_prior_values_without_duplicates(client, db_session, test_setup):
    headers = test_setup["auth_headers"]

    # 1. First upload: 500 qty
    csv1 = io.BytesIO(b"item_code,grn_qty\nWLD-WIRE-01,500.00\n")
    client.post(
        "/api/v1/mrp/upload-grn",
        headers=headers,
        data={"plant_id": "Plant 1", "planning_month": 10, "planning_year": 2026},
        files={"file": ("grn_v1.csv", csv1, "text/csv")},
    )

    # 2. Second upload (re-upload for month-end adjustment): 750 qty
    csv2 = io.BytesIO(b"item_code,grn_qty\nWLD-WIRE-01,750.00\n")
    r2 = client.post(
        "/api/v1/mrp/upload-grn",
        headers=headers,
        data={"plant_id": "Plant 1", "planning_month": 10, "planning_year": 2026},
        files={"file": ("grn_v2.csv", csv2, "text/csv")},
    )
    assert r2.status_code == 200

    # Ensure no duplicate rows were created
    rows = db_session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.consumable_code == "WLD-WIRE-01",
            MonthlyRequirementRecord.planning_month == 10,
            MonthlyRequirementRecord.planning_year == 2026,
            MonthlyRequirementRecord.is_deleted == False,
        )
    ).all()
    assert len(rows) == 1
    # Check that value was overwritten with 750
    assert rows[0].grn_received_qty == Decimal("750.0000")
    # closing = 200 + 750 - 50 = 900
    assert rows[0].closing_stock == Decimal("900.0000")
    # net_order = max(0, 1000 - 900) = 100
    assert rows[0].net_order_requirement == Decimal("100.0000")


def test_mrp_grn_inserts_new_record_if_not_present(client, db_session, test_setup):
    headers = test_setup["auth_headers"]

    # Ingest PNT-THIN-01 which doesn't have an existing MonthlyRequirementRecord
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Item ID", "Received Qty", "Invoice No", "Unit Rate"])
    ws.append(["PNT-THIN-01", 120.0, "INV-999", 165.5])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    res = client.post(
        "/api/v1/requirements/upload-grn",
        headers=headers,
        data={"plant_id": "PLANT_1", "planning_month": 10, "planning_year": 2026},
        files={"file": ("grn_new.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["inserted_count"] == 1

    rec = db_session.scalar(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.consumable_code == "PNT-THIN-01",
            MonthlyRequirementRecord.planning_month == 10,
            MonthlyRequirementRecord.planning_year == 2026,
        )
    )
    assert rec is not None
    assert rec.grn_received_qty == Decimal("120.0000")
    assert rec.closing_stock == Decimal("120.0000")
    assert rec.stock_qty == Decimal("120.0000")
    assert rec.net_order_requirement == Decimal("0.0000")
    assert rec.shortage_qty == Decimal("0.0000")
    assert rec.invoice_no == "INV-999"
