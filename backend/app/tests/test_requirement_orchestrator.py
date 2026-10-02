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
from app.models.requirements import CalculatedRequirement, RequirementCalculationError
from app.models.rules import ConsumptionNorm
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


@pytest.fixture
def orchestrator_fixture():
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

    # 1. User & Role
    admin_role = Role(id=uuid4(), code="ADMIN", name="Admin Role")
    user = User(
        id=uuid4(),
        username="orchestrator_tester",
        password_hash="dummy_hash",
        is_active=True,
        roles=[admin_role],
    )
    db.add(user)

    # 2. Units
    u_box = Unit(id=uuid4(), code="BOX", name="Carton Box", is_active=True)
    u_pcs = Unit(id=uuid4(), code="PCS", name="Pieces", is_active=True)
    db.add_all([u_box, u_pcs])

    # 3. Consumable
    cons_box = Consumable(
        id=uuid4(),
        code="CONS-BOX-M25",
        name="Corrugated Master Shipping Carton 500x300x250",
        unit_id=u_box.id,
        is_active=True,
    )
    db.add(cons_box)

    # 4. Products
    p1 = Product(id=uuid4(), code="PRD-HARNESS-01", name="Harness Valid", uom="PCS", is_active=True)
    p2 = Product(id=uuid4(), code="PRD-HARNESS-02", name="Harness No Plant", uom="PCS", is_active=True)
    p3 = Product(id=uuid4(), code="PRD-HARNESS-03", name="Harness No Process", uom="PCS", is_active=True)
    p4 = Product(id=uuid4(), code="PRD-HARNESS-04", name="Harness No Rule", uom="PCS", is_active=True)
    db.add_all([p1, p2, p3, p4])

    # 5. Plant, Route & Process
    plant = Plant(id=uuid4(), name="Plant Pune 01", location="Pune, Maharashtra", is_active=True)
    process = Process(id=uuid4(), name="Final Packing", description="Packing process", is_active=True)
    route = Route(id=uuid4(), name="Standard Route", is_active=True)
    db.add_all([plant, process, route])
    db.flush()

    route_step = RouteStep(id=uuid4(), route_id=route.id, process_id=process.id, sequence_order=1)
    db.add(route_step)

    # 6. Product-Plant Mappings (P1, P3, P4 mapped to Plant; P2 is NOT mapped)
    pp1 = ProductPlant(id=uuid4(), product_id=p1.id, plant_id=plant.id, route_id=route.id, is_primary=True, is_active=True)
    pp3 = ProductPlant(id=uuid4(), product_id=p3.id, plant_id=plant.id, route_id=route.id, is_primary=True, is_active=True)
    pp4 = ProductPlant(id=uuid4(), product_id=p4.id, plant_id=plant.id, route_id=route.id, is_primary=True, is_active=True)
    db.add_all([pp1, pp3, pp4])

    # 7. Product-Process-Consumable Mappings (P1 and P4 mapped to cons_box; P3 is NOT mapped)
    ppc1 = ProductProcessConsumable(id=uuid4(), product_id=p1.id, process_id=process.id, consumable_id=cons_box.id, is_active=True)
    ppc4 = ProductProcessConsumable(id=uuid4(), product_id=p4.id, process_id=process.id, consumable_id=cons_box.id, is_active=True)
    db.add_all([ppc1, ppc4])

    # 8. Consumption Norms (P1 has PACKING_RATIO norm; P4 has NO norm)
    norm1 = ConsumptionNorm(
        id=uuid4(),
        rule_type="PACKING_RATIO",
        consumable_id=cons_box.id,
        product_id=p1.id,
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
    db.add(norm1)

    # 9. Planning Version 1 (Revision R0)
    v1 = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=0,
        revision_label="R0",
        source_filename="PRD_2026_10_R0.xlsx",
        status="LOCKED",
        created_by=user.id,
    )
    db.add(v1)
    db.flush()

    batch1 = ImportBatch(
        id=uuid4(),
        planning_version_id=v1.id,
        filename="PRD_2026_10_R0.xlsx",
        file_size_bytes=1024,
        status="PROMOTED",
        uploaded_by=user.id,
    )
    db.add(batch1)
    db.flush()

    h1 = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=v1.id,
        import_batch_id=batch1.id,
        planning_period="2026-10",
        total_planned_qty=Decimal("3010.0000"),
        total_line_items=4,
    )
    db.add(h1)
    db.flush()

    # 4 items in V1: Item 1 valid, Item 2 no plant, Item 3 no process, Item 4 no rule
    i1 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=v1.id,
        header_id=h1.id,
        source_row_number=1,
        product_code=p1.code,
        product_id=p1.id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("1010.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    i2 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=v1.id,
        header_id=h1.id,
        source_row_number=2,
        product_code=p2.code,
        product_id=p2.id,
        plant_code="PLANT-UNKNOWN",
        planned_quantity=Decimal("500.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    i3 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=v1.id,
        header_id=h1.id,
        source_row_number=3,
        product_code=p3.code,
        product_id=p3.id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("700.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    i4 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=v1.id,
        header_id=h1.id,
        source_row_number=4,
        product_code=p4.code,
        product_id=p4.id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("800.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    db.add_all([i1, i2, i3, i4])

    # 10. Planning Version 2 (Revision R1) for isolation test
    v2 = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        revision_label="R1",
        source_filename="PRD_2026_10_R1.xlsx",
        status="LOCKED",
        created_by=user.id,
    )
    db.add(v2)
    db.flush()

    batch2 = ImportBatch(
        id=uuid4(),
        planning_version_id=v2.id,
        filename="PRD_2026_10_R1.xlsx",
        file_size_bytes=1024,
        status="PROMOTED",
        uploaded_by=user.id,
    )
    db.add(batch2)
    db.flush()

    h2 = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=v2.id,
        import_batch_id=batch2.id,
        planning_period="2026-10",
        total_planned_qty=Decimal("2020.0000"),
        total_line_items=1,
    )
    db.add(h2)
    db.flush()

    i5 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=v2.id,
        header_id=h2.id,
        source_row_number=1,
        product_code=p1.code,
        product_id=p1.id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("2020.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    db.add(i5)

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
            "v1": v1,
            "v2": v2,
            "p1": p1,
            "p2": p2,
            "p3": p3,
            "p4": p4,
            "cons_box": cons_box,
            "plant": plant,
            "route": route,
            "i1": i1,
            "i2": i2,
            "i3": i3,
            "i4": i4,
            "i5": i5,
        }
        yield client, db, headers, ctx

    db.close()
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# TESTS FOR M3.3 REQUIREMENT CALCULATION ORCHESTRATOR
# ==============================================================================

def test_mixed_valid_and_error_batch(orchestrator_fixture):
    """Mixed Batch: 1 valid item calculates cleanly, 3 items fail with explicit typed errors.
    Zero errors are silently skipped.
    """
    client, db, headers, ctx = orchestrator_fixture

    resp = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v1"].id)},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["planning_version_id"] == str(ctx["v1"].id)
    assert data["planning_period"] == "2026-10"
    assert data["revision_label"] == "R0"
    assert data["status"] == "CALCULATED_WITH_ERRORS"
    assert data["total_items_processed"] == 4
    assert data["successful_requirements_count"] == 1
    assert data["error_count"] == 3

    # 1. Verify successful requirement (1010 PCS / 25 = 40.4 -> ROUND_UP -> 41 BOX)
    reqs_resp = client.get(
        f"/api/v1/requirements/planning-versions/{ctx['v1'].id}",
        headers=headers,
    )
    assert reqs_resp.status_code == 200
    reqs = reqs_resp.json()
    assert len(reqs) == 1
    req = reqs[0]
    assert req["product_code"] == "PRD-HARNESS-01"
    assert Decimal(str(req["source_production_qty"])) == Decimal("1010.0000")
    assert Decimal(str(req["raw_requirement"])) == Decimal("40.4000")
    assert req["rounding_policy"] == "ROUND_UP"
    assert Decimal(str(req["calculated_qty"])) == Decimal("41")
    assert req["uom"] == "BOX"
    assert "explanation_payload" in req
    assert req["explanation_payload"]["rule"]["rule_type"] == "PACKING_RATIO"

    # 2. Verify explicit error categorization
    errors_resp = client.get(
        f"/api/v1/requirements/planning-versions/{ctx['v1'].id}/errors",
        headers=headers,
    )
    assert errors_resp.status_code == 200
    errors = errors_resp.json()
    assert len(errors) == 3

    error_codes = {e["error_code"] for e in errors}
    assert "MISSING_PLANT_MAPPING" in error_codes
    assert "MISSING_PROCESS_MAPPING" in error_codes
    assert "MISSING_RULE" in error_codes

    # Verify error context
    plant_err = next(e for e in errors if e["error_code"] == "MISSING_PLANT_MAPPING")
    assert plant_err["product_code"] == "PRD-HARNESS-02"

    proc_err = next(e for e in errors if e["error_code"] == "MISSING_PROCESS_MAPPING")
    assert proc_err["product_code"] == "PRD-HARNESS-03"

    rule_err = next(e for e in errors if e["error_code"] == "MISSING_RULE")
    assert rule_err["product_code"] == "PRD-HARNESS-04"
    assert rule_err["consumable_code"] == "CONS-BOX-M25"


def test_recalculation_and_idempotency(orchestrator_fixture):
    """Recalculating the same version cleans prior runs and reproduces deterministic outputs."""
    client, db, headers, ctx = orchestrator_fixture

    # First run
    resp1 = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v1"].id)},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Second run (recalculation)
    resp2 = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v1"].id)},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Confirm idempotency
    assert data1["successful_requirements_count"] == data2["successful_requirements_count"]
    assert data1["error_count"] == data2["error_count"]

    reqs_resp = client.get(f"/api/v1/requirements/planning-versions/{ctx['v1'].id}", headers=headers)
    assert len(reqs_resp.json()) == 1

    errs_resp = client.get(f"/api/v1/requirements/planning-versions/{ctx['v1'].id}/errors", headers=headers)
    assert len(errs_resp.json()) == 3


def test_planning_revision_isolation(orchestrator_fixture):
    """Revision R0 and Revision R1 maintain complete isolation of calculations and records."""
    client, db, headers, ctx = orchestrator_fixture

    # 1. Calculate Version 1 (Revision R0: 1010 PCS -> 41 BOX)
    resp_v1 = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v1"].id)},
    )
    assert resp_v1.status_code == 200

    # 2. Calculate Version 2 (Revision R1: 2020 PCS / 25 = 80.8 -> 81 BOX)
    resp_v2 = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v2"].id)},
    )
    assert resp_v2.status_code == 200
    assert resp_v2.json()["status"] == "CALCULATED"
    assert resp_v2.json()["successful_requirements_count"] == 1
    assert resp_v2.json()["error_count"] == 0

    # 3. Check V1 records are preserved and unchanged
    v1_reqs = client.get(f"/api/v1/requirements/planning-versions/{ctx['v1'].id}", headers=headers).json()
    assert len(v1_reqs) == 1
    assert Decimal(str(v1_reqs[0]["calculated_qty"])) == Decimal("41")
    assert Decimal(str(v1_reqs[0]["source_production_qty"])) == Decimal("1010.0000")

    # 4. Check V2 records
    v2_reqs = client.get(f"/api/v1/requirements/planning-versions/{ctx['v2'].id}", headers=headers).json()
    assert len(v2_reqs) == 1
    assert Decimal(str(v2_reqs[0]["calculated_qty"])) == Decimal("81")
    assert Decimal(str(v2_reqs[0]["source_production_qty"])) == Decimal("2020.0000")

    # 5. Recalculate V2 and confirm V1 remains untouched
    client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v2"].id)},
    )
    v1_reqs_after = client.get(f"/api/v1/requirements/planning-versions/{ctx['v1'].id}", headers=headers).json()
    assert len(v1_reqs_after) == 1
    assert Decimal(str(v1_reqs_after[0]["calculated_qty"])) == Decimal("41")


def test_decimal_aggregation(orchestrator_fixture):
    """Cross-item summation uses exact Decimal precision without binary floating point drift."""
    client, db, headers, ctx = orchestrator_fixture

    # Add 2 more valid items for P1 to V2
    h2 = db.query(PRDOrderHeader).filter(PRDOrderHeader.planning_version_id == ctx["v2"].id).first()

    # Item A: 1000 PCS / 25 = 40.0000 -> 40 BOX
    i_extra1 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=ctx["v2"].id,
        header_id=h2.id,
        source_row_number=2,
        product_code=ctx["p1"].code,
        product_id=ctx["p1"].id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("1000.0000"),
        uom="PCS",
        target_period="2026-11",
    )
    # Item B: 505 PCS / 25 = 20.2000 -> 21 BOX
    i_extra2 = PRDOrderItem(
        id=uuid4(),
        planning_version_id=ctx["v2"].id,
        header_id=h2.id,
        source_row_number=3,
        product_code=ctx["p1"].code,
        product_id=ctx["p1"].id,
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("505.0000"),
        uom="PCS",
        target_period="2026-12",
    )
    db.add_all([i_extra1, i_extra2])
    db.commit()

    resp = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v2"].id)},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Total lines: 3 (Item 5: 2020 PCS -> 80.8 raw, 81 final; Item extra1: 1000 PCS -> 40.0 raw, 40 final; Item extra2: 505 PCS -> 20.2 raw, 21 final)
    assert data["successful_requirements_count"] == 3
    summary = data["summary_by_consumable"][0]
    assert summary["consumable_code"] == "CONS-BOX-M25"
    assert summary["line_items_count"] == 3

    # Exact Decimals:
    # raw sum: 80.8000 + 40.0000 + 20.2000 = 141.0000
    assert Decimal(str(summary["total_raw_requirement"])) == Decimal("141.0000")
    # final sum: 81 + 40 + 21 = 142
    assert Decimal(str(summary["total_calculated_qty"])) == Decimal("142")


def test_invalid_planning_version_status_rejected(orchestrator_fixture):
    """Planning version in DRAFT status cannot be calculated and yields a 400 error."""
    client, db, headers, ctx = orchestrator_fixture

    ctx["v1"].status = "DRAFT"
    db.commit()

    resp = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"planning_version_id": str(ctx["v1"].id)},
    )
    assert resp.status_code == 400
    assert "must be validated, locked, or calculated" in resp.json()["message"].lower()
