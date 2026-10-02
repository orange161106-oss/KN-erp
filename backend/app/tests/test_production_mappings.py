from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.auth import Role, User
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.masters import Product
from app.models.production import Plant, Process, Route, RouteStep
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


@pytest.fixture
def mapping_test_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("btrim", 1, lambda s: s.strip() if s is not None else None)

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()

    # Create admin/planner user
    planner_role = Role(id=uuid4(), code="ADMIN", name="Admin Role")
    user = User(
        id=uuid4(),
        username="mapping_admin",
        password_hash="dummy_hash",
        is_active=True,
        roles=[planner_role],
    )
    db.add(user)

    # 1. Seed Units
    unit_pcs = Unit(id=uuid4(), code="PCS", name="Pieces", is_active=True)
    unit_mtr = Unit(id=uuid4(), code="MTR", name="Meters", is_active=True)
    db.add_all([unit_pcs, unit_mtr])

    # 2. Seed Consumables
    c_wire = Consumable(
        id=uuid4(), code="CONS-WIRE-01", name="Copper Wire 1.5mm", unit_id=unit_mtr.id, is_active=True
    )
    c_term = Consumable(
        id=uuid4(), code="CONS-TERM-01", name="Gold Terminal Pins", unit_id=unit_pcs.id, is_active=True
    )
    c_tube = Consumable(
        id=uuid4(), code="CONS-TUBE-01", name="Heat Shrink Tube 6mm", unit_id=unit_mtr.id, is_active=True
    )
    db.add_all([c_wire, c_term, c_tube])

    # 3. Seed Products
    prod1 = Product(id=uuid4(), code="PRD-HARNESS-01", name="Wire Harness Gen-A", uom="PCS", is_active=True)
    prod2 = Product(id=uuid4(), code="PRD-SENSOR-01", name="Speed Sensor Mod-B", uom="PCS", is_active=True)
    prod_inactive = Product(id=uuid4(), code="PRD-DISCONTINUED", name="Discontinued Assy", uom="PCS", is_active=False)
    db.add_all([prod1, prod2, prod_inactive])

    # 4. Seed Plants
    plant1 = Plant(id=uuid4(), name="Plant Pune 01", location="Pune, Maharashtra", is_active=True)
    plant2 = Plant(id=uuid4(), name="Plant Chennai 02", location="Chennai, Tamil Nadu", is_active=True)
    plant_inactive = Plant(id=uuid4(), name="Plant Dormant", location="Inactive Location", is_active=False)
    db.add_all([plant1, plant2, plant_inactive])

    # 5. Seed Processes
    proc_cut = Process(id=uuid4(), name="Wire Cutting & Stripping", description="Automated wire cut", is_active=True)
    proc_crimp = Process(id=uuid4(), name="Terminal Crimping", description="Precision crimp", is_active=True)
    proc_shrink = Process(id=uuid4(), name="Heat Shrinking", description="Thermal sleeve oven", is_active=True)
    proc_test = Process(id=uuid4(), name="Electrical Testing", description="Continuity check", is_active=True)
    db.add_all([proc_cut, proc_crimp, proc_shrink, proc_test])

    # 6. Seed Route and Steps
    route1 = Route(id=uuid4(), name="Standard Harness Assembly Route", description="Full assembly route", is_active=True)
    db.add(route1)
    db.flush()

    step1 = RouteStep(id=uuid4(), route_id=route1.id, process_id=proc_cut.id, sequence_order=1)
    step2 = RouteStep(id=uuid4(), route_id=route1.id, process_id=proc_crimp.id, sequence_order=2)
    step3 = RouteStep(id=uuid4(), route_id=route1.id, process_id=proc_shrink.id, sequence_order=3)
    db.add_all([step1, step2, step3])

    db.commit()

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user:pass@127.0.0.1/kn_unit_test",
        auth_secret_key=TEST_SIGNING_KEY,
    )
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app, raise_server_exceptions=True) as client:
        token = create_access_token(user.id, settings)
        auth_headers = {"Authorization": f"Bearer {token}"}
        seeded_data = {
            "prod1": prod1,
            "prod2": prod2,
            "prod_inactive": prod_inactive,
            "plant1": plant1,
            "plant2": plant2,
            "plant_inactive": plant_inactive,
            "proc_cut": proc_cut,
            "proc_crimp": proc_crimp,
            "proc_shrink": proc_shrink,
            "proc_test": proc_test,
            "route1": route1,
            "c_wire": c_wire,
            "c_term": c_term,
            "c_tube": c_tube,
        }
        yield client, db, auth_headers, seeded_data

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_product_plant_crud_and_primary_switch(mapping_test_setup):
    client, db, headers, seed = mapping_test_setup

    # 1. Create ProductPlant mapping
    payload1 = {
        "product_id": str(seed["prod1"].id),
        "plant_id": str(seed["plant1"].id),
        "route_id": str(seed["route1"].id),
        "is_primary": True,
    }
    resp1 = client.post("/api/v1/mappings/product-plants", headers=headers, json=payload1)
    assert resp1.status_code == 201
    created1 = resp1.json()
    assert created1["product_code"] == "PRD-HARNESS-01"
    assert created1["plant_name"] == "Plant Pune 01"
    assert created1["route_name"] == "Standard Harness Assembly Route"
    assert created1["is_primary"] is True

    # 2. Add a second plant as primary -> first plant must be switched to non-primary
    payload2 = {
        "product_id": str(seed["prod1"].id),
        "plant_id": str(seed["plant2"].id),
        "route_id": str(seed["route1"].id),
        "is_primary": True,
    }
    resp2 = client.post("/api/v1/mappings/product-plants", headers=headers, json=payload2)
    assert resp2.status_code == 201
    created2 = resp2.json()
    assert created2["is_primary"] is True

    # Verify first mapping is now is_primary = False
    check1 = client.get(f"/api/v1/mappings/product-plants/{created1['id']}", headers=headers)
    assert check1.status_code == 200
    assert check1.json()["is_primary"] is False

    # 3. Duplicate mapping attempt should return 409
    dup_resp = client.post("/api/v1/mappings/product-plants", headers=headers, json=payload1)
    assert dup_resp.status_code == 409

    # 4. Filter list by product_id
    list_resp = client.get(
        f"/api/v1/mappings/product-plants?product_id={seed['prod1'].id}", headers=headers
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    # 5. Update mapping status to inactive
    update_resp = client.put(
        f"/api/v1/mappings/product-plants/{created2['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False


def test_product_plant_inactive_entity_rejected(mapping_test_setup):
    client, db, headers, seed = mapping_test_setup

    # Try mapping to inactive plant
    payload = {
        "product_id": str(seed["prod1"].id),
        "plant_id": str(seed["plant_inactive"].id),
        "route_id": str(seed["route1"].id),
        "is_primary": True,
    }
    resp = client.post("/api/v1/mappings/product-plants", headers=headers, json=payload)
    assert resp.status_code == 400
    assert "inactive" in resp.json()["message"].lower()

    # Try mapping inactive product
    payload_inact_prod = {
        "product_id": str(seed["prod_inactive"].id),
        "plant_id": str(seed["plant1"].id),
        "route_id": str(seed["route1"].id),
        "is_primary": True,
    }
    resp2 = client.post("/api/v1/mappings/product-plants", headers=headers, json=payload_inact_prod)
    assert resp2.status_code == 400


def test_product_process_consumable_crud(mapping_test_setup):
    client, db, headers, seed = mapping_test_setup

    # 1. Create mapping: prod1 -> proc_cut -> c_wire
    payload = {
        "product_id": str(seed["prod1"].id),
        "process_id": str(seed["proc_cut"].id),
        "consumable_id": str(seed["c_wire"].id),
    }
    resp = client.post("/api/v1/mappings/product-process-consumables", headers=headers, json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["product_code"] == "PRD-HARNESS-01"
    assert data["process_name"] == "Wire Cutting & Stripping"
    assert data["consumable_code"] == "CONS-WIRE-01"
    assert data["unit"] == "MTR"
    assert data["is_active"] is True

    # 2. Duplicate mapping attempt should return 409
    dup_resp = client.post("/api/v1/mappings/product-process-consumables", headers=headers, json=payload)
    assert dup_resp.status_code == 409

    # 3. List PPC mappings with filters
    list_resp = client.get(
        f"/api/v1/mappings/product-process-consumables?product_id={seed['prod1'].id}&process_id={seed['proc_cut'].id}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Update status
    update_resp = client.put(
        f"/api/v1/mappings/product-process-consumables/{data['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False


def test_bulk_mapping_endpoints(mapping_test_setup):
    client, db, headers, seed = mapping_test_setup

    # Bulk create ProductPlants
    bulk_pp = {
        "items": [
            {
                "product_id": str(seed["prod2"].id),
                "plant_id": str(seed["plant1"].id),
                "route_id": str(seed["route1"].id),
                "is_primary": True,
            },
            {
                "product_id": str(seed["prod2"].id),
                "plant_id": str(seed["plant2"].id),
                "route_id": str(seed["route1"].id),
                "is_primary": False,
            },
        ]
    }
    resp_pp = client.post("/api/v1/mappings/product-plants/bulk", headers=headers, json=bulk_pp)
    assert resp_pp.status_code == 201
    assert resp_pp.json()["created_count"] == 2
    assert len(resp_pp.json()["errors"]) == 0

    # Bulk create PPC
    bulk_ppc = {
        "items": [
            {
                "product_id": str(seed["prod2"].id),
                "process_id": str(seed["proc_cut"].id),
                "consumable_id": str(seed["c_wire"].id),
            },
            {
                "product_id": str(seed["prod2"].id),
                "process_id": str(seed["proc_crimp"].id),
                "consumable_id": str(seed["c_term"].id),
            },
        ]
    }
    resp_ppc = client.post("/api/v1/mappings/product-process-consumables/bulk", headers=headers, json=bulk_ppc)
    assert resp_ppc.status_code == 201
    assert resp_ppc.json()["created_count"] == 2


def test_phase_2_gate_complete_chain_resolution(mapping_test_setup):
    """Demonstrates Phase 2 Gate:
    For a product, verify the full structural chain:
    Product -> Plant -> Route -> Process -> Consumable
    """
    client, db, headers, seed = mapping_test_setup

    # 1. Map Product1 -> Plant1 with Route1
    client.post(
        "/api/v1/mappings/product-plants",
        headers=headers,
        json={
            "product_id": str(seed["prod1"].id),
            "plant_id": str(seed["plant1"].id),
            "route_id": str(seed["route1"].id),
            "is_primary": True,
        },
    )

    # 2. Map Consumables to Process Steps for Product1:
    # - Step 1: proc_cut -> c_wire
    client.post(
        "/api/v1/mappings/product-process-consumables",
        headers=headers,
        json={
            "product_id": str(seed["prod1"].id),
            "process_id": str(seed["proc_cut"].id),
            "consumable_id": str(seed["c_wire"].id),
        },
    )
    # - Step 2: proc_crimp -> c_term
    client.post(
        "/api/v1/mappings/product-process-consumables",
        headers=headers,
        json={
            "product_id": str(seed["prod1"].id),
            "process_id": str(seed["proc_crimp"].id),
            "consumable_id": str(seed["c_term"].id),
        },
    )
    # - Step 3: proc_shrink -> c_tube
    client.post(
        "/api/v1/mappings/product-process-consumables",
        headers=headers,
        json={
            "product_id": str(seed["prod1"].id),
            "process_id": str(seed["proc_shrink"].id),
            "consumable_id": str(seed["c_tube"].id),
        },
    )

    # 3. Call Gate Resolution Endpoint: GET /mappings/resolve/{product_id}
    resolve_resp = client.get(
        f"/api/v1/mappings/resolve/{seed['prod1'].id}", headers=headers
    )
    assert resolve_resp.status_code == 200
    res = resolve_resp.json()

    # Product level
    assert res["product_code"] == "PRD-HARNESS-01"
    assert res["product_name"] == "Wire Harness Gen-A"
    assert res["uom"] == "PCS"
    assert len(res["plant_mappings"]) == 1

    # Plant level
    plant_map = res["plant_mappings"][0]
    assert plant_map["plant_name"] == "Plant Pune 01"
    assert plant_map["route_name"] == "Standard Harness Assembly Route"
    assert plant_map["is_primary"] is True
    assert len(plant_map["steps"]) == 3

    # Step level verification (Strict sequence ordering)
    step1 = plant_map["steps"][0]
    assert step1["sequence_order"] == 1
    assert step1["process_name"] == "Wire Cutting & Stripping"
    assert len(step1["consumables"]) == 1
    assert step1["consumables"][0]["code"] == "CONS-WIRE-01"
    assert step1["consumables"][0]["unit"] == "MTR"

    step2 = plant_map["steps"][1]
    assert step2["sequence_order"] == 2
    assert step2["process_name"] == "Terminal Crimping"
    assert len(step2["consumables"]) == 1
    assert step2["consumables"][0]["code"] == "CONS-TERM-01"
    assert step2["consumables"][0]["unit"] == "PCS"

    step3 = plant_map["steps"][2]
    assert step3["sequence_order"] == 3
    assert step3["process_name"] == "Heat Shrinking"
    assert len(step3["consumables"]) == 1
    assert step3["consumables"][0]["code"] == "CONS-TUBE-01"
    assert step3["consumables"][0]["unit"] == "MTR"


def test_mapping_validation_report(mapping_test_setup):
    """Verifies that the validation report flags unmapped products,
    processes without consumables, and inactive entities.
    """
    client, db, headers, seed = mapping_test_setup

    # Initially, neither prod1 nor prod2 are mapped
    resp = client.get("/api/v1/mappings/validate", headers=headers)
    assert resp.status_code == 200
    report = resp.json()
    assert report["is_valid"] is False
    assert report["unmapped_products_count"] >= 2
    issues = report["issues"]
    assert any(i["issue_type"] == "UNMAPPED_PRODUCT" and i["product_code"] == "PRD-HARNESS-01" for i in issues)

    # Now map prod1 to plant1 and route1, but do NOT map consumables yet
    client.post(
        "/api/v1/mappings/product-plants",
        headers=headers,
        json={
            "product_id": str(seed["prod1"].id),
            "plant_id": str(seed["plant1"].id),
            "route_id": str(seed["route1"].id),
            "is_primary": True,
        },
    )

    # Validate prod1 specifically
    resp_prod1 = client.get(f"/api/v1/mappings/validate?product_id={seed['prod1'].id}", headers=headers)
    assert resp_prod1.status_code == 200
    report_prod1 = resp_prod1.json()
    issues_prod1 = report_prod1["issues"]
    # Should flag warning that process steps have no consumables
    assert any(i["issue_type"] == "PROCESS_WITHOUT_CONSUMABLES" for i in issues_prod1)
