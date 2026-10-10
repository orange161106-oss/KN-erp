from datetime import date
from decimal import Decimal
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
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.models.production import Plant, Process, Route, RouteStep
from app.models.rules import ConsumptionNorm
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


@pytest.fixture
def golden_rule_fixture():
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

    # 1. User & Auth
    admin_role = Role(id=uuid4(), code="ADMIN", name="Admin Role")
    user = User(
        id=uuid4(),
        username="planner_golden",
        password_hash="dummy_hash",
        is_active=True,
        roles=[admin_role],
    )
    db.add(user)

    # 2. Units
    u_box = Unit(id=uuid4(), code="BOX", name="Carton Box", is_active=True)
    u_pcs = Unit(id=uuid4(), code="PCS", name="Pieces", is_active=True)
    db.add_all([u_box, u_pcs])

    # 3. Product & Consumable
    product = Product(
        id=uuid4(),
        code="PRD-HARNESS-01",
        name="Wire Harness Gen-A",
        uom="PCS",
        is_active=True,
    )
    consumable = Consumable(
        id=uuid4(),
        code="CONS-BOX-M25",
        name="Corrugated Master Shipping Carton 500x300x250",
        unit_id=u_box.id,
        is_active=True,
    )
    db.add_all([product, consumable])

    # 4. Plant, Route & Process
    plant = Plant(
        id=uuid4(),
        name="Plant Pune 01",
        location="Pune, Maharashtra",
        is_active=True,
    )
    process = Process(
        id=uuid4(),
        name="Final Packing & Palletization",
        description="Carton packing",
        is_active=True,
    )
    route = Route(
        id=uuid4(),
        name="Harness Assembly & Pack Route",
        is_active=True,
    )
    db.add_all([plant, process, route])
    db.flush()

    route_step = RouteStep(
        id=uuid4(),
        route_id=route.id,
        process_id=process.id,
        sequence_order=1,
    )
    db.add(route_step)

    # 5. Mappings (Product -> Plant -> Route -> Process -> Consumable)
    prod_plant = ProductPlant(
        id=uuid4(),
        product_id=product.id,
        plant_id=plant.id,
        route_id=route.id,
        is_primary=True,
        is_active=True,
    )
    prod_proc_cons = ProductProcessConsumable(
        id=uuid4(),
        product_id=product.id,
        process_id=process.id,
        consumable_id=consumable.id,
        is_active=True,
    )
    db.add_all([prod_plant, prod_proc_cons])

    # 6. Planning Version, PRD Header, & PRD Order Item (Production Source)
    plan_version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        revision_label="R0",
        source_filename="KN_PRD_2026_10.xlsx",
        status="LOCKED",
        created_by=user.id,
    )
    db.add(plan_version)
    db.flush()

    batch = ImportBatch(
        id=uuid4(),
        planning_version_id=plan_version.id,
        filename="KN_PRD_2026_10.xlsx",
        file_size_bytes=1024,
        status="PROMOTED",
        uploaded_by=user.id,
    )
    db.add(batch)
    db.flush()

    header = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=plan_version.id,
        import_batch_id=batch.id,
        planning_period="2026-10",
        total_planned_qty=Decimal("1010.0000"),
        total_line_items=1,
    )
    db.add(header)
    db.flush()

    prd_item = PRDOrderItem(
        id=uuid4(),
        planning_version_id=plan_version.id,
        header_id=header.id,
        source_row_number=12,
        product_code="PRD-HARNESS-01",
        product_id=product.id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("1010.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    db.add(prd_item)

    # 7. Approved Consumption Norm: PACKING_RATIO with units_per_pack=25, ROUND_UP
    norm = ConsumptionNorm(
        id=uuid4(),
        rule_type="PACKING_RATIO",
        consumable_id=consumable.id,
        product_id=product.id,
        process_id=process.id,
        plant_id=plant.id,
        version=1,
        parameters={"units_per_pack": 25},
        unit_id=u_box.id,
        rounding_policy="ROUND_UP",
        rounding_precision=0,
        effective_from=date(2026, 10, 1),
        is_active=True,
    )
    db.add(norm)
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
        headers = {"Authorization": f"Bearer {token}"}
        ctx = {
            "prd_item": prd_item,
            "product": product,
            "consumable": consumable,
            "plant": plant,
            "process": process,
            "plan_version": plan_version,
            "norm": norm,
            "prod_proc_cons": prod_proc_cons,
            "prod_plant": prod_plant,
        }
        yield client, db, headers, ctx

    db.close()
    Base.metadata.drop_all(bind=engine)


# ==========================================================
# Tests for M3.2 First Approved Deterministic Calculation
# ==========================================================

def test_golden_case_packing_box_fractional_ceiling(golden_rule_fixture):
    """Golden Case: 1010 PCS / 25 = 40.4000 BOX -> ROUND_UP precision 0 -> 41 BOX.
    Verifies full end-to-end explanation across all required entities.
    """
    client, db, headers, ctx = golden_rule_fixture

    payload = {
        "prd_item_id": str(ctx["prd_item"].id),
        "consumable_id": str(ctx["consumable"].id),
    }
    resp = client.post("/api/v1/consumption-norms/calculate-item", headers=headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # 1. Planning Version check
    assert data["planning_version"]["planning_period"] == "2026-10"
    assert data["planning_version"]["revision_label"] == "R0"
    assert data["planning_version"]["status"] == "LOCKED"

    # 2. Production Source check
    assert data["production_source"]["row_number"] == 12
    assert Decimal(str(data["production_source"]["planned_quantity"])) == Decimal("1010.0000")
    assert data["production_source"]["uom"] == "PCS"

    # 3. Product check
    assert data["product"]["code"] == "PRD-HARNESS-01"
    assert data["product"]["name"] == "Wire Harness Gen-A"

    # 4. Plant check
    assert data["plant"]["name"] == "Plant Pune 01"

    # 5. Process check
    assert data["process"]["name"] == "Final Packing & Palletization"

    # 6. Consumable check
    assert data["consumable"]["code"] == "CONS-BOX-M25"
    assert data["consumable"]["unit"] == "BOX"

    # 7. Rule Metadata
    assert data["rule"]["rule_type"] == "PACKING_RATIO"
    assert data["rule"]["version"] == 1
    assert data["rule"]["parameters"]["units_per_pack"] == 25

    # 8. Calculation & Explainability Steps
    calc = data["calculation"]
    assert Decimal(str(calc["source_production_qty"])) == Decimal("1010.0000")
    assert Decimal(str(calc["raw_requirement"])) == Decimal("40.4000")
    assert calc["rounding_policy"] == "ROUND_UP"
    assert calc["rounding_precision"] == 0
    assert Decimal(str(calc["final_calculated_requirement"])) == Decimal("41")
    assert calc["unit"] == "BOX"

    # Verify calculation steps are explicitly enumerated
    assert len(calc["calculation_steps"]) == 2
    step1 = calc["calculation_steps"][0]
    assert step1["step_number"] == 1
    assert "1010" in step1["formula"]
    assert "25" in step1["formula"]

    step2 = calc["calculation_steps"][1]
    assert step2["step_number"] == 2
    assert "ROUND_UP" in step2["description"]
    assert "41" in step2["formula"]


def test_golden_case_exact_multiple_no_rounding_spillover(golden_rule_fixture):
    """Exact Multiple: 1000 PCS / 25 = 40.0000 BOX -> ROUND_UP precision 0 -> 40 BOX."""
    client, db, headers, ctx = golden_rule_fixture

    # Update item planned quantity to 1000
    ctx["prd_item"].planned_quantity = Decimal("1000.0000")
    db.commit()

    payload = {
        "prd_item_id": str(ctx["prd_item"].id),
        "consumable_id": str(ctx["consumable"].id),
    }
    resp = client.post("/api/v1/consumption-norms/calculate-item", headers=headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert Decimal(str(data["calculation"]["raw_requirement"])) == Decimal("40.0000")
    assert Decimal(str(data["calculation"]["final_calculated_requirement"])) == Decimal("40")


def test_zero_quantity_case(golden_rule_fixture):
    """Zero production quantity yields 0 required boxes, and DB enforces positive planned_quantity."""
    client, db, headers, ctx = golden_rule_fixture

    # 1. Domain evaluation with 0 qty yields 0
    from app.domain.rules import RoundingPolicy, RuleCalculationInput, RuleType, evaluate_rule
    from sqlalchemy.exc import IntegrityError

    zero_calc = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PACKING_RATIO,
            parameters={"units_per_pack": Decimal("25")},
            production_quantity=Decimal("0"),
            rounding_policy=RoundingPolicy.ROUND_UP,
            rounding_precision=0,
        )
    )
    assert zero_calc.final_calculated_requirement == Decimal("0")
    assert zero_calc.raw_requirement == Decimal("0")

    # 2. Database integrity check constraint protects PRD order lines from non-positive quantities
    with pytest.raises(IntegrityError):
        ctx["prd_item"].planned_quantity = Decimal("0.0000")
        db.commit()
    db.rollback()


def test_invalid_denominator_norm_creation_rejected(golden_rule_fixture):
    """Denominator = 0 in PACKING_RATIO must be rejected by parameter validation."""
    client, db, headers, ctx = golden_rule_fixture

    payload = {
        "rule_type": "PACKING_RATIO",
        "consumable_id": str(ctx["consumable"].id),
        "product_id": str(ctx["product"].id),
        "parameters": {"units_per_pack": 0},
        "unit_id": str(ctx["consumable"].unit_id),
        "effective_from": str(date.today()),
    }
    resp = client.post("/api/v1/consumption-norms", headers=headers, json=payload)
    assert resp.status_code == 400
    assert "denominator" in resp.json()["message"].lower()


def test_missing_mapping_returns_404(golden_rule_fixture):
    """When a consumable is not mapped to any process step for the product, 404 is returned."""
    client, db, headers, ctx = golden_rule_fixture

    # Deactivate the process consumable mapping
    ctx["prod_proc_cons"].is_active = False
    db.commit()

    payload = {
        "prd_item_id": str(ctx["prd_item"].id),
        "consumable_id": str(ctx["consumable"].id),
    }
    resp = client.post("/api/v1/consumption-norms/calculate-item", headers=headers, json=payload)
    assert resp.status_code == 404
    assert "not mapped" in resp.json()["message"].lower()


def test_missing_rule_returns_404(golden_rule_fixture):
    """When no active consumption norm exists for the consumable, 404 is returned."""
    client, db, headers, ctx = golden_rule_fixture

    # Deactivate the norm
    ctx["norm"].is_active = False
    db.commit()

    payload = {
        "prd_item_id": str(ctx["prd_item"].id),
        "consumable_id": str(ctx["consumable"].id),
    }
    resp = client.post("/api/v1/consumption-norms/calculate-item", headers=headers, json=payload)
    assert resp.status_code == 404
    assert "no active" in resp.json()["message"].lower()


def test_explicit_rounding_never_hidden(golden_rule_fixture):
    """Validates that raw calculation and rounding policy are explicitly exposed and distinct."""
    client, db, headers, ctx = golden_rule_fixture

    payload = {
        "prd_item_id": str(ctx["prd_item"].id),
        "consumable_id": str(ctx["consumable"].id),
    }
    resp = client.post("/api/v1/consumption-norms/calculate-item", headers=headers, json=payload)
    assert resp.status_code == 200
    calc = resp.json()["calculation"]

    # Raw value is 40.4000, final rounded is 41
    assert Decimal(str(calc["raw_requirement"])) == Decimal("40.4000")
    assert Decimal(str(calc["final_calculated_requirement"])) == Decimal("41")
    assert calc["rounding_policy"] == "ROUND_UP"
    assert calc["raw_requirement"] != calc["final_calculated_requirement"]

