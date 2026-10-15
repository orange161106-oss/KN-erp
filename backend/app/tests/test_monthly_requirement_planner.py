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


def test_approval_state_machine_transitions(client, test_data):
    # 1. Create a DRAFT plan
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 3, "year": 2026}, headers=test_data["admin_headers"])
    assert res_plan.status_code == 201
    plan_id = res_plan.json()["id"]
    assert res_plan.json()["status"] == "DRAFT"

    # 2. Plant 2 incharge cannot submit Plant 1 plan (403 Forbidden)
    res_p2_submit = client.patch(f"/api/v1/plans/{plan_id}/submit", headers=test_data["plant_2_headers"])
    assert res_p2_submit.status_code == 403

    # 3. Plant 1 incharge can submit their own plant plan
    res_p1_submit = client.patch(f"/api/v1/plans/{plan_id}/submit", headers=test_data["plant_1_headers"])
    assert res_p1_submit.status_code == 200
    assert res_p1_submit.json()["status"] == "SUBMITTED"

    # 4. Trying to submit again from SUBMITTED returns 400 Bad Request
    res_dup_submit = client.patch(f"/api/v1/plans/{plan_id}/submit", headers=test_data["plant_1_headers"])
    assert res_dup_submit.status_code == 400
    assert "only draft plans" in res_dup_submit.text.lower()

    # 5. Plant Incharge cannot approve (Requires Admin/Planner)
    res_unauth_approve = client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["plant_1_headers"])
    assert res_unauth_approve.status_code == 403

    # 6. Admin can approve -> status becomes APPROVED
    res_approve = client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["admin_headers"])
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] == "APPROVED"

    # 7. Trying to approve already APPROVED plan returns 400 Bad Request
    res_dup_approve = client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["admin_headers"])
    assert res_dup_approve.status_code == 400


def test_cross_plant_aggregation_math(client, test_data):
    c1 = test_data["c1"]
    c2 = test_data["c2"]

    # 1. Create and approve Plan 1 for Period 8/2026 (Plant I)
    res_p1 = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 8, "year": 2026}, headers=test_data["admin_headers"])
    p1_id = res_p1.json()["id"]
    client.post(f"/api/v1/plans/{p1_id}/items/single", json={"consumable_id": str(c1.id), "requested_qty": 100.0}, headers=test_data["admin_headers"])
    client.post(f"/api/v1/plans/{p1_id}/items/single", json={"consumable_id": str(c2.id), "requested_qty": 50.0}, headers=test_data["admin_headers"])
    client.patch(f"/api/v1/plans/{p1_id}/submit", headers=test_data["plant_1_headers"])
    client.patch(f"/api/v1/plans/{p1_id}/approve", headers=test_data["admin_headers"])

    # 2. Create and approve Plan 2 for Period 8/2026 (Plant II)
    res_p2 = client.post("/api/v1/plans", json={"plant_id": "PLANT_II", "month": 8, "year": 2026}, headers=test_data["admin_headers"])
    p2_id = res_p2.json()["id"]
    client.post(f"/api/v1/plans/{p2_id}/items/single", json={"consumable_id": str(c1.id), "requested_qty": 200.0}, headers=test_data["admin_headers"])
    client.post(f"/api/v1/plans/{p2_id}/items/single", json={"consumable_id": str(c2.id), "requested_qty": 75.0}, headers=test_data["admin_headers"])
    client.patch(f"/api/v1/plans/{p2_id}/submit", headers=test_data["plant_2_headers"])
    client.patch(f"/api/v1/plans/{p2_id}/approve", headers=test_data["admin_headers"])

    # 3. Standard user cannot trigger aggregation
    agg_unauth = client.post("/api/v1/aggregate/8/2026", headers=test_data["plant_1_headers"])
    assert agg_unauth.status_code == 403

    # 4. Admin triggers aggregation
    agg_res = client.post("/api/v1/aggregate/8/2026", headers=test_data["admin_headers"])
    assert agg_res.status_code == 200, agg_res.text
    data = agg_res.json()
    assert data["month"] == 8
    assert data["year"] == 2026
    assert data["total_approved_plans"] == 2
    assert data["total_aggregated_consumables"] == 2

    # Check the cross-plant math
    records_by_id = {r["consumable_id"]: r for r in data["records"]}
    c1_rec = records_by_id[str(c1.id)]
    c2_rec = records_by_id[str(c2.id)]

    assert c1_rec["total_gross_qty"] == 300.0  # 100 + 200
    assert c1_rec["net_purchase_qty"] == 300.0
    assert c2_rec["total_gross_qty"] == 125.0  # 50 + 75
    assert c2_rec["net_purchase_qty"] == 125.0

    # 5. Re-running aggregation performs idempotent upsert
    re_agg = client.post("/api/v1/aggregate/8/2026", headers=test_data["admin_headers"])
    assert re_agg.status_code == 200
    assert re_agg.json()["total_aggregated_consumables"] == 2


def test_aggregation_clears_gracefully_when_no_approved_plans(client, test_data):
    # Call aggregation for a period with no approved plans -> returns 200 with 0 records
    res = client.post("/api/v1/aggregate/9/2028", headers=test_data["admin_headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["total_approved_plans"] == 0
    assert data["total_aggregated_consumables"] == 0
    assert data["records"] == []


def test_auto_provisioning_all_5_plants_on_fetch(client, test_data):
    # GET /plans?month=10&year=2026 for admin auto-provisions all 5 plants
    res = client.get("/api/v1/plans?month=10&year=2026", headers=test_data["admin_headers"])
    assert res.status_code == 200
    plans = res.json()
    plants = [p["plant_id"] for p in plans if p["month"] == 10 and p["year"] == 2026]
    for expected in ["PLANT_I", "PLANT_II", "PLANT_III", "PLANT_IV", "PLANT_V"]:
        assert expected in plants
    # All auto-provisioned plans are in DRAFT status
    for p in plans:
        if p["month"] == 10 and p["year"] == 2026:
            assert p["status"] in ("DRAFT", "APPROVED", "SUBMITTED")


def test_direct_draft_to_approved_by_admin(client, test_data):
    # Create plan in DRAFT
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_III", "month": 5, "year": 2027}, headers=test_data["admin_headers"])
    assert res_plan.status_code == 201
    plan_id = res_plan.json()["id"]
    assert res_plan.json()["status"] == "DRAFT"

    # Admin approves directly from DRAFT without SUBMITTED first
    res_app = client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["admin_headers"])
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "APPROVED"


def test_automatic_background_aggregation_on_approval_and_item_update(client, test_data):
    c1 = test_data["c1"]

    # 1. Create plan for 7/2027
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 7, "year": 2027}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    # 2. Add item
    item_res = client.post(
        f"/api/v1/plans/{plan_id}/items/single",
        json={"consumable_id": str(c1.id), "requested_qty": 350.0},
        headers=test_data["admin_headers"],
    )
    item_id = item_res.json()["id"]

    # 3. Direct approve plan -> triggers background aggregation
    client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["admin_headers"])

    # 4. Verify GET /aggregate/7/2027 immediately reflects the 350.0 quantity without manual aggregation call
    agg_res = client.get("/api/v1/aggregate/7/2027", headers=test_data["admin_headers"])
    assert agg_res.status_code == 200
    records = agg_res.json()
    assert len(records) == 1
    assert records[0]["consumable_id"] == str(c1.id)
    assert records[0]["total_gross_qty"] == 350.0

    # 5. Update item quantity -> automatic background recalculation
    client.put(
        f"/api/v1/plans/{plan_id}/items/{item_id}",
        json={"requested_qty": 500.0},
        headers=test_data["admin_headers"],
    )
    agg_res2 = client.get("/api/v1/aggregate/7/2027", headers=test_data["admin_headers"])
    assert agg_res2.status_code == 200
    records2 = agg_res2.json()
    assert len(records2) == 1
    assert records2[0]["total_gross_qty"] == 500.0


def test_get_aggregated_requirements_endpoint(client, test_data):
    c1 = test_data["c1"]

    # Create & approve plan for 11/2026
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 11, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]
    client.post(f"/api/v1/plans/{plan_id}/items/single", json={"consumable_id": str(c1.id), "requested_qty": 450.0}, headers=test_data["admin_headers"])
    client.patch(f"/api/v1/plans/{plan_id}/submit", headers=test_data["plant_1_headers"])
    client.patch(f"/api/v1/plans/{plan_id}/approve", headers=test_data["admin_headers"])

    # Run aggregation
    client.post("/api/v1/aggregate/11/2026", headers=test_data["admin_headers"])

    # 1. Unauthenticated / Standard user access fails with 403
    get_unauth = client.get("/api/v1/aggregate/11/2026", headers=test_data["plant_1_headers"])
    assert get_unauth.status_code == 403

    # 2. Admin retrieves aggregated requirements
    get_res = client.get("/api/v1/aggregate/11/2026", headers=test_data["admin_headers"])
    assert get_res.status_code == 200, get_res.text
    records = get_res.json()
    assert isinstance(records, list)
    assert len(records) >= 1

    rec = next(r for r in records if r["consumable_id"] == str(c1.id))
    assert rec["total_gross_qty"] == 450.0
    assert rec["net_purchase_qty"] == 450.0
    assert rec["item_code"] == c1.item_id
    assert rec["item_description"] is not None
    assert rec["part_no"] is not None
    assert rec["unit"] is not None


def test_phase4_single_intake_crud_and_auto_consumable(client, test_data):
    # 1. Create plan
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_II", "month": 8, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    # 2. Add item with non-existing consumable code -> auto creates consumable & serial_no
    single_res = client.post(
        f"/api/v1/plans/{plan_id}/items/single",
        json={
            "item_code": "AUTO-CONSUMABLE-01",
            "item_description": "Auto Created High-Grade Grease",
            "part_no": "PART-GREASE-X",
            "unit": "KGS",
            "serial_no": 1,
            "requested_qty": 75.5,
        },
        headers=test_data["admin_headers"],
    )
    assert single_res.status_code == 200, single_res.text
    item_data = single_res.json()
    item_id = item_data["id"]
    assert item_data["item_code"] == "AUTO-CONSUMABLE-01"
    assert item_data["description"] == "Auto Created High-Grade Grease"
    assert item_data["part_no"] == "PART-GREASE-X"
    assert item_data["unit"] == "KGS"
    assert item_data["serial_no"] == 1
    assert item_data["requested_qty"] == 75.5

    # 3. Update line item (PUT)
    put_res = client.put(
        f"/api/v1/plans/{plan_id}/items/{item_id}",
        json={"requested_qty": 120.0, "part_no": "PART-GREASE-MODIFIED"},
        headers=test_data["admin_headers"],
    )
    assert put_res.status_code == 200, put_res.text
    updated = put_res.json()
    assert updated["requested_qty"] == 120.0
    assert updated["part_no"] == "PART-GREASE-MODIFIED"

    # 4. Delete line item (DELETE)
    del_res = client.delete(
        f"/api/v1/plans/{plan_id}/items/{item_id}",
        headers=test_data["admin_headers"],
    )
    assert del_res.status_code == 200

    # Verify deleted
    get_plans = client.get("/api/v1/plans", headers=test_data["admin_headers"])
    plan_obj = next(p for p in get_plans.json() if p["id"] == plan_id)
    assert len(plan_obj["line_items"]) == 0


def test_phase4_multi_sheet_all_plants_bulk_upload(client, test_data):
    # Create an initial plan for plant 1
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 10, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    # Build Excel workbook with Plant 1 and Plant 2 sheets
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df1 = pd.DataFrame([
            {"S.no.": 1, "Item Id.": "SHEET-ITEM-P1", "Item Description": "P1 Oil", "Part No.": "P1-OIL", "Unit": "L", "Oct'26": 55.0}
        ])
        df1.to_excel(writer, sheet_name="Plant I", index=False)

        df2 = pd.DataFrame([
            {"S.no.": 1, "Item Id.": "SHEET-ITEM-P2", "Item Description": "P2 Grease", "Part No.": "P2-GRS", "Unit": "KG", "Oct'26": 88.0}
        ])
        df2.to_excel(writer, sheet_name="Plant II", index=False)

    excel_buffer.seek(0)

    files = {"file": ("all_plants.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = client.post(
        f"/api/v1/plans/{plan_id}/items/bulk?upload_all_plants=true",
        files=files,
        headers=test_data["admin_headers"],
    )
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["upserted"] >= 2
    assert "PLANT_I" in data["plants_affected"]
    assert "PLANT_II" in data["plants_affected"]

    # Verify both plans exist and contain line items
    plans_res = client.get("/api/v1/plans", headers=test_data["admin_headers"])
    plans_by_plant = {p["plant_id"]: p for p in plans_res.json() if p["month"] == 10 and p["year"] == 2026}
    assert "PLANT_I" in plans_by_plant
    assert "PLANT_II" in plans_by_plant
    assert len(plans_by_plant["PLANT_I"]["line_items"]) >= 1
    assert len(plans_by_plant["PLANT_II"]["line_items"]) >= 1


def test_complex_factory_double_header_excel_upload(client, test_data):
    # Tests parsing of double-header row (Row with 'Month', Row with 'Item Id.'),
    # non-standard sheet name 'Plant 1', and multiple QTY / month columns
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 10, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    # Build simulated factory excel with double header
    # Row 0: Title banner / empty
    # Row 1: Month row: ['', '', '', '', '', "Oct'26", "Nov'26"]
    # Row 2: Header row: ['S.no.', 'Item Id.', 'Item Description', 'Part No.', 'Unit', 'QTY', 'QTY']
    # Row 3: Data row: [1, 'COMPLEX-ITEM-01', 'High Temp Grease', 'HTG-100', 'KGS', 125.0, 200.0]
    # Row 4: Data row: [2, 'COMPLEX-ITEM-02', 'Gear Lubricant', 'GL-320', 'LTR', 75.0, 50.0]
    raw_data = [
        ["Factory Consumable Plan", None, None, None, None, None, None],
        ["Month", None, None, None, None, "Oct' 26", "Nov' 26"],
        ["S.no.", "Item Id.", "Item Description", "Part No.", "Unit", "QTY", "QTY"],
        [1, "CON-001", "High Temp Grease", "HTG-100", "KGS", 125.0, 200.0],
        [2, "CON-002", "Gear Lubricant", "GL-320", "LTR", 75.0, 50.0],
    ]
    df_complex = pd.DataFrame(raw_data)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_complex.to_excel(writer, sheet_name="Plant 1", header=False, index=False)
    excel_buffer.seek(0)

    files = {"file": ("1.Consumable plan- Oct '26.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = client.post(
        f"/api/v1/plans/{plan_id}/items/bulk",
        files=files,
        headers=test_data["admin_headers"],
    )
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["upserted"] == 2

    # Check imported quantities match Oct'26 column (125.0, 75.0) rather than Nov'26 (200.0, 50.0)
    items_by_code = {it["item_code"]: it for it in data["items"]}
    assert items_by_code["CON-001"]["requested_qty"] == 125.0
    assert items_by_code["CON-002"]["requested_qty"] == 75.0
    assert items_by_code["CON-001"]["serial_no"] == 1
    assert items_by_code["CON-002"]["serial_no"] == 2


def test_five_column_catalog_without_qty_defaults_to_zero(client, test_data):
    # Simulates plant1.xlsx / Sheet1 with 5 columns: S.no., Item Id., Item Description, Part No., Unit
    # No QTY column present -> requested_qty defaults to 0.0
    res_plan = client.post("/api/v1/plans", json={"plant_id": "PLANT_I", "month": 10, "year": 2026}, headers=test_data["admin_headers"])
    plan_id = res_plan.json()["id"]

    catalog_data = [
        ["S.no.", "Item Id.", "Item Description", "Part No.", "Unit"],
        [1, "CAT-ITEM-001", "Welding Rod E6013", "WR-6013", "NOS"],
        [2, "CAT-ITEM-002", "Cutting Disc 4 inch", "CD-4IN", "NOS"],
        [3, "CAT-ITEM-003", "Cotton Waste White", None, "KGS"],
    ]
    df_catalog = pd.DataFrame(catalog_data)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_catalog.to_excel(writer, sheet_name="Sheet1", header=False, index=False)
    excel_buffer.seek(0)

    files = {"file": ("plant1.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = client.post(
        f"/api/v1/plans/{plan_id}/items/bulk",
        files=files,
        headers=test_data["admin_headers"],
    )
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["upserted"] == 3

    items_by_code = {it["item_code"]: it for it in data["items"]}
    assert items_by_code["CAT-ITEM-001"]["requested_qty"] == 0.0
    assert items_by_code["CAT-ITEM-002"]["requested_qty"] == 0.0
    assert items_by_code["CAT-ITEM-003"]["requested_qty"] == 0.0
    assert items_by_code["CAT-ITEM-001"]["serial_no"] == 1
    assert items_by_code["CAT-ITEM-002"]["serial_no"] == 2
    assert items_by_code["CAT-ITEM-003"]["serial_no"] == 3
    assert items_by_code["CAT-ITEM-001"]["description"] == "Welding Rod E6013"
    assert items_by_code["CAT-ITEM-003"]["unit"] == "KGS"





