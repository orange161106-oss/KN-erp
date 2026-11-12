from datetime import datetime
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
from app.models.grn import GRNLineItem, GRNRecord
from app.models.inventory_masters import Consumable, Unit
from app.models.requirements import MonthlyRequirementPlan, RequirementLineItem, RequirementStatus
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

    # Roles
    admin_role = Role(code="ADMIN", name="Administrator")
    planner_role = Role(code="PLANNER", name="Planner")
    user_role = Role(code="USER", name="Standard User")
    db_session.add_all([admin_role, planner_role, user_role])

    # Users
    admin_user = User(
        username="admin_user",
        password_hash="secret",
        is_super_admin=True,
        roles=[admin_role],
    )
    planner_user = User(
        username="planner_user",
        password_hash="secret",
        is_super_admin=False,
        roles=[planner_role],
    )
    standard_user = User(
        username="standard_worker",
        password_hash="secret",
        is_super_admin=False,
        roles=[user_role],
        assigned_plant="PLANT_I",
    )
    db_session.add_all([admin_user, planner_user, standard_user])

    # Consumables Unit
    unit = Unit(code="NOS", name="Numbers")
    db_session.add(unit)
    db_session.flush()

    # Consumables
    c1 = Consumable(
        item_id="CON-001",
        name="Coolant Oil A",
        description="Premium industrial coolant",
        unit_id=unit.id,
        output_unit="NOS",
        rate=100.0,
        latest_grn_rate=0.0,
    )
    c2 = Consumable(
        item_id="CON-002",
        name="Hydraulic Fluid H",
        description="Heavy-duty hydraulic fluid",
        unit_id=unit.id,
        output_unit="NOS",
        rate=50.0,
        latest_grn_rate=0.0,
    )
    db_session.add_all([c1, c2])

    # Requirement Plan for Oct 2026 (Plant I)
    plan1 = MonthlyRequirementPlan(
        plant_id="PLANT_I",
        month=10,
        year=2026,
        status=RequirementStatus.DRAFT,
    )
    db_session.add(plan1)
    db_session.flush()

    r1 = RequirementLineItem(
        plan_id=plan1.id,
        consumable_id=c1.id,
        serial_no=1,
        formula_qty=100.0,
        requested_qty=100.0,
        rate=0.0,
        receipt_qty=0.0,
        receipt_value=0.0,
    )
    r2 = RequirementLineItem(
        plan_id=plan1.id,
        consumable_id=c2.id,
        serial_no=2,
        formula_qty=50.0,
        requested_qty=50.0,
        rate=0.0,
        receipt_qty=0.0,
        receipt_value=0.0,
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    admin_token = create_access_token(admin_user.id, settings)
    standard_token = create_access_token(standard_user.id, settings)

    return {
        "admin_token": admin_token,
        "standard_token": standard_token,
        "c1": c1,
        "c2": c2,
        "plan1": plan1,
    }


def test_grn_excel_upload_and_rate_cascade(client, db_session, test_setup):
    admin_token = test_setup["admin_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create in-memory Excel workbook for GRN
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GRN Receipts"

    # Header row
    ws.append(["GRN No", "GRN Date", "Vendor Name", "Item Code", "Item Description", "Receipt Qty", "Unit Rate"])
    # Data row 1: CON-001
    ws.append(["GRN-2026-901", "2026-10-15", "Apex Industrial Lubricants", "CON-001", "Coolant Oil A", 45, 165.50])
    # Data row 2: CON-002
    ws.append(["GRN-2026-901", "2026-10-15", "Apex Industrial Lubricants", "CON-002", "Hydraulic Fluid H", 20, 58.75])

    excel_io = io.BytesIO()
    wb.save(excel_io)
    excel_io.seek(0)

    response = client.post(
        "/api/v1/requirements/grn/upload",
        files={"file": ("grn_oct_2026.xlsx", excel_io.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params={"month": 10, "year": 2026},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["grn_no"] == "GRN-2026-901"
    assert data["total_items"] == 2
    assert data["total_receipt_qty"] == 65.0
    assert data["consumables_updated"] == 2
    assert data["requirement_lines_updated"] == 2

    # Check database consumables latest_grn_rate
    c1 = db_session.get(Consumable, test_setup["c1"].id)
    c2 = db_session.get(Consumable, test_setup["c2"].id)
    assert float(c1.latest_grn_rate) == 165.50
    assert float(c2.latest_grn_rate) == 58.75

    # Check RequirementLineItem records updated
    req_items = db_session.scalars(
        select(RequirementLineItem).where(RequirementLineItem.plan_id == test_setup["plan1"].id)
    ).all()
    r1 = next(r for r in req_items if r.consumable_id == c1.id)
    r2 = next(r for r in req_items if r.consumable_id == c2.id)

    assert r1.rate == 165.50
    assert r1.receipt_qty == 45.0
    assert r1.receipt_value == round(45.0 * 165.50, 2)

    assert r2.rate == 58.75
    assert r2.receipt_qty == 20.0
    assert r2.receipt_value == round(20.0 * 58.75, 2)

    # Check GET /plans reflects order value and receipt values
    get_res = client.get("/api/v1/requirements/plans?month=10&year=2026", headers=headers)
    assert get_res.status_code == 200
    plan_data = get_res.json()[0]
    line_data = next(it for it in plan_data["line_items"] if it["item_code"] == "CON-001")
    assert line_data["rate"] == 165.50
    assert line_data["receipt_qty"] == 45.0
    assert line_data["receipt_value"] == round(45.0 * 165.50, 2)
    assert line_data["order_value"] == round(100.0 * 165.50, 2)


def test_grn_csv_upload_and_aggregation(client, db_session, test_setup):
    admin_token = test_setup["admin_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    csv_content = (
        "Item Id,Accepted Qty,Unit Price,Doc No,Date\n"
        "CON-001,30,170.00,GRN-CSV-01,2026-10-18\n"
        "CON-001,20,170.00,GRN-CSV-01,2026-10-18\n"
    )

    response = client.post(
        "/api/v1/requirements/grn/upload",
        files={"file": ("receipts.csv", csv_content.encode("utf-8"), "text/csv")},
        params={"month": 10, "year": 2026},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_items"] == 1
    assert data["total_receipt_qty"] == 50.0  # 30 + 20 aggregated
    assert data["total_receipt_value"] == round(50.0 * 170.0, 2)

    # Verify GRN records created in DB
    grn_rec = db_session.scalar(select(GRNRecord).where(GRNRecord.grn_no == "GRN-CSV-01"))
    assert grn_rec is not None
    assert len(grn_rec.line_items) == 1
    assert grn_rec.line_items[0].received_qty == 50.0
    assert grn_rec.line_items[0].unit_rate == 170.0


def test_grn_rbac_unauthorized_rejected(client, test_setup):
    standard_token = test_setup["standard_token"]
    headers = {"Authorization": f"Bearer {standard_token}"}

    csv_content = "Item Id,Qty,Rate\nCON-001,10,100\n"
    response = client.post(
        "/api/v1/requirements/grn/upload",
        files={"file": ("unauthorized.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert response.status_code == 403
    assert "Admin or Planner role required" in response.text
