import io
from uuid import uuid4
from fastapi.testclient import TestClient
import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import Role, User
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
def test_data(db_session):
    settings = app.state.settings

    # Roles
    admin_role = Role(code="ADMIN", name="Administrator")
    user_role = Role(code="USER", name="Standard User")
    db_session.add_all([admin_role, user_role])

    # Users
    admin_user = User(
        username="admin_user",
        password_hash="secret",
        is_super_admin=True,
        roles=[admin_role],
    )
    plant_1_user = User(
        username="plant_incharge_1",
        password_hash="secret",
        is_super_admin=False,
        roles=[user_role],
        assigned_plant="PLANT_I",
    )
    plant_2_user = User(
        username="plant_incharge_2",
        password_hash="secret",
        is_super_admin=False,
        roles=[user_role],
        assigned_plant="PLANT_II",
    )
    unassigned_user = User(
        username="unassigned_worker",
        password_hash="secret",
        is_super_admin=False,
        roles=[user_role],
        assigned_plant=None,
    )
    db_session.add_all([admin_user, plant_1_user, plant_2_user, unassigned_user])

    # Consumables Unit
    unit = Unit(code="NOS", name="Numbers")
    db_session.add(unit)
    db_session.flush()

    # Consumables
    c1 = Consumable(
        item_id="CON-001",
        name="Coolant Oil A",
        unit_id=unit.id,
    )
    c2 = Consumable(
        item_id="CON-002",
        name="Welding Wire B",
        unit_id=unit.id,
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    admin_token = create_access_token(admin_user.id, settings)
    plant_1_token = create_access_token(plant_1_user.id, settings)
    plant_2_token = create_access_token(plant_2_user.id, settings)
    unassigned_token = create_access_token(unassigned_user.id, settings)

    return {
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "plant_1_headers": {"Authorization": f"Bearer {plant_1_token}"},
        "plant_2_headers": {"Authorization": f"Bearer {plant_2_token}"},
        "unassigned_headers": {"Authorization": f"Bearer {unassigned_token}"},
        "c1": c1,
        "c2": c2,
    }


def test_create_monthly_plan_and_uniqueness(client, test_data):
    # 1. Create plan for PLANT_I
    payload = {
        "plant_id": "PLANT_I",
        "month": 10,
        "year": 2026,
    }
    res = client.post("/api/v1/plans", json=payload, headers=test_data["admin_headers"])
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["plant_id"] == "PLANT_I"
    assert data["month"] == 10
    assert data["year"] == 2026
    assert data["status"] == "DRAFT"

    dup_res = client.post("/api/v1/plans", json=payload, headers=test_data["admin_headers"])
    assert dup_res.status_code == 409
    err_msg = dup_res.json().get("detail") or dup_res.json().get("message") or ""
    assert "already exists" in err_msg.lower()


    # 3. Create plan for another plant (PLANT_II) -> 201 Created
    res_plant_2 = client.post("/api/v1/plans", json={"plant_id": "PLANT_II", "month": 10, "year": 2026}, headers=test_data["admin_headers"])
    assert res_plant_2.status_code == 201


def test_upsert_single_item(client, test_data):
    # Create plan
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 11, "year": 2026}, headers=test_data["admin_headers"])
    assert res_plan.status_code == 201
    plan_id = res_plan.json()["id"]

    c1 = test_data["c1"]

    # 1. Insert item
    item_payload = {
        "consumable_id": str(c1.id),
        "requested_qty": 45.5,
    }
    res_item = client.post(f"/api/v1/plans/{plan_id}/items/single", json=item_payload, headers=test_data["admin_headers"])
    assert res_item.status_code == 200, res_item.text
    data = res_item.json()
    assert data["plan_id"] == plan_id
    assert data["consumable_id"] == str(c1.id)
    assert data["requested_qty"] == 45.5
    assert data["item_id"] == "CON-001"

    # 2. Update same item (upsert)
    update_payload = {
        "consumable_id": str(c1.id),
        "requested_qty": 90.0,
    }
    res_update = client.post(f"/api/v1/plans/{plan_id}/items/single", json=update_payload, headers=test_data["admin_headers"])
    assert res_update.status_code == 200
    assert res_update.json()["requested_qty"] == 90.0

    # 3. Check plan line_items count remains 1
    plans_res = client.get("/api/v1/plans", headers=test_data["admin_headers"])
    plan_data = next(p for p in plans_res.json() if p["id"] == plan_id)
    assert len(plan_data["line_items"]) == 1
    assert plan_data["line_items"][0]["requested_qty"] == 90.0


def test_bulk_upload_csv_items(client, test_data):
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 12, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    csv_content = b"Item ID,QTY\nCON-001,150.5\nCON-002,250.0\nNON_EXISTENT_ITEM,40.0\n"

    files = {"file": ("items.csv", io.BytesIO(csv_content), "text/csv")}
    upload_res = client.post(f"/api/v1/plans/{plan_id}/items/bulk", files=files, headers=test_data["admin_headers"])
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["total_rows"] == 3
    assert data["upserted"] == 2
    assert len(data["errors"]) == 1
    assert "NON_EXISTENT_ITEM" in data["errors"][0]

    # Verify line items in plan
    plans_res = client.get("/api/v1/plans", headers=test_data["admin_headers"])
    plan_data = next(p for p in plans_res.json() if p["id"] == plan_id)
    assert len(plan_data["line_items"]) == 2


def test_bulk_upload_excel_items(client, test_data):
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 1, "year": 2027}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    df = pd.DataFrame([
        {"Item ID": "CON-001", "QTY": 320.0},
        {"Item ID": "CON-002", "QTY": 500.0},
    ])
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)

    files = {"file": ("upload.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = client.post(f"/api/v1/plans/{plan_id}/items/bulk", files=files, headers=test_data["admin_headers"])
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["total_rows"] == 2
    assert data["upserted"] == 2
    assert len(data["errors"]) == 0


def test_rbac_filtering_standard_user_vs_admin(client, test_data):
    # Create two plans for different plants
    client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 5, "year": 2026}, headers=test_data["admin_headers"])
    client.post("/api/v1/plans", json={"plant_id": "PLANT_II", "month": 5, "year": 2026}, headers=test_data["admin_headers"])

    # 1. Admin gets all plans
    admin_res = client.get("/api/v1/plans", headers=test_data["admin_headers"])
    assert admin_res.status_code == 200
    plants_in_admin = {p["plant_id"] for p in admin_res.json()}
    assert "PLANT_I" in plants_in_admin
    assert "PLANT_II" in plants_in_admin

    # 2. Plant 1 incharge gets only PLANT_I
    p1_res = client.get("/api/v1/plans", headers=test_data["plant_1_headers"])
    assert p1_res.status_code == 200
    p1_plants = {p["plant_id"] for p in p1_res.json()}
    assert p1_plants == {"PLANT_I"}

    # 3. Plant 2 incharge gets only PLANT_II
    p2_res = client.get("/api/v1/plans", headers=test_data["plant_2_headers"])
    assert p2_res.status_code == 200
    p2_plants = {p["plant_id"] for p in p2_res.json()}
    assert p2_plants == {"PLANT_II"}

    # 4. Unassigned user gets empty list
    unassigned_res = client.get("/api/v1/plans", headers=test_data["unassigned_headers"])
    assert unassigned_res.status_code == 200
    assert len(unassigned_res.json()) == 0


def test_requirements_prefix_alias_routes(client, test_data):
    # Verify that /api/v1/requirements/plans also returns the list
    req_res = client.get("/api/v1/requirements/plans", headers=test_data["admin_headers"])
    assert req_res.status_code == 200
    assert isinstance(req_res.json(), list)
