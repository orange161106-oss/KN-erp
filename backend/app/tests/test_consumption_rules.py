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
from app.domain.rules import (
    InvalidDenominatorError,
    ParameterValidationError,
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
    validate_rule_parameters,
)
from app.domain.rules.models import (
    AreaCoverageParams,
    FixedQuantityParams,
    MaintenanceParams,
    MinMaxParams,
    PackingRatioParams,
    PlantRequestParams,
    ProductionRateParams,
    ToolLifeParams,
)
from app.main import create_app
from app.models.auth import Role, User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Plant, Process
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


# ==========================================================
# 1. Pure Domain Parameter Validation Tests
# ==========================================================

def test_production_rate_validation():
    # Valid
    p = validate_rule_parameters(
        RuleType.PRODUCTION_RATE, {"rate": Decimal("0.05"), "scrap_factor": Decimal("0.02")}
    )
    assert isinstance(p, ProductionRateParams)
    assert p.rate == Decimal("0.05")

    # Invalid rate <= 0
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.PRODUCTION_RATE, {"rate": Decimal("0")})

    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.PRODUCTION_RATE, {"rate": Decimal("-0.1")})

    # Invalid negative scrap factor
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.PRODUCTION_RATE, {"rate": Decimal("0.05"), "scrap_factor": Decimal("-0.01")}
        )


def test_area_coverage_validation_and_invalid_denominator():
    # Valid
    p = validate_rule_parameters(
        RuleType.AREA_COVERAGE,
        {"area_per_unit": Decimal("2.5"), "coverage": Decimal("10.0"), "loss_factor": Decimal("0.05")},
    )
    assert isinstance(p, AreaCoverageParams)

    # Invalid area <= 0
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.AREA_COVERAGE, {"area_per_unit": Decimal("0"), "coverage": Decimal("10.0")}
        )

    # Invalid denominator: coverage == 0 or negative
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.AREA_COVERAGE, {"area_per_unit": Decimal("2.5"), "coverage": Decimal("0")}
        )

    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.AREA_COVERAGE, {"area_per_unit": Decimal("2.5"), "coverage": Decimal("-5.0")}
        )


def test_packing_ratio_validation_and_invalid_denominator():
    # Valid
    p = validate_rule_parameters(RuleType.PACKING_RATIO, {"units_per_pack": Decimal("10")})
    assert isinstance(p, PackingRatioParams)

    # Invalid denominator: units_per_pack == 0 or negative
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(RuleType.PACKING_RATIO, {"units_per_pack": Decimal("0")})

    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(RuleType.PACKING_RATIO, {"units_per_pack": Decimal("-2")})


def test_tool_life_validation_and_invalid_denominator():
    # Valid
    p = validate_rule_parameters(
        RuleType.TOOL_LIFE, {"operations_per_unit": Decimal("2"), "tool_life": Decimal("5000")}
    )
    assert isinstance(p, ToolLifeParams)

    # Invalid operations <= 0
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.TOOL_LIFE, {"operations_per_unit": Decimal("0"), "tool_life": Decimal("5000")}
        )

    # Invalid denominator: tool_life == 0 or negative
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.TOOL_LIFE, {"operations_per_unit": Decimal("1"), "tool_life": Decimal("0")}
        )

    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.TOOL_LIFE, {"operations_per_unit": Decimal("1"), "tool_life": Decimal("-100")}
        )


def test_fixed_quantity_validation():
    p = validate_rule_parameters(RuleType.FIXED_QUANTITY, {"quantity": Decimal("15.5")})
    assert isinstance(p, FixedQuantityParams)

    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.FIXED_QUANTITY, {"quantity": Decimal("0")})


def test_min_max_validation():
    # Valid
    p = validate_rule_parameters(
        RuleType.MIN_MAX,
        {"min_quantity": Decimal("10"), "max_quantity": Decimal("50"), "base_rate": Decimal("0.2")},
    )
    assert isinstance(p, MinMaxParams)

    # Invalid: max < min
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.MIN_MAX,
            {"min_quantity": Decimal("60"), "max_quantity": Decimal("50"), "base_rate": Decimal("0.2")},
        )

    # Invalid: base_rate <= 0
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.MIN_MAX,
            {"min_quantity": Decimal("10"), "max_quantity": Decimal("50"), "base_rate": Decimal("0")},
        )


def test_maintenance_validation():
    p = validate_rule_parameters(
        RuleType.MAINTENANCE, {"fixed_amount": Decimal("10"), "variable_rate": Decimal("0.01")}
    )
    assert isinstance(p, MaintenanceParams)

    # Invalid: both 0
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(
            RuleType.MAINTENANCE, {"fixed_amount": Decimal("0"), "variable_rate": Decimal("0")}
        )


# ==========================================================
# 2. Pure Domain Decimal Arithmetic & Rounding Tests
# ==========================================================

def test_pure_decimal_arithmetic_precision():
    # Verifies standard Decimal accuracy (no IEEE 754 float drift)
    res = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PRODUCTION_RATE,
            parameters={"rate": Decimal("0.1"), "scrap_factor": Decimal("0")},
            production_quantity=Decimal("3"),
        )
    )
    assert res.final_calculated_requirement == Decimal("0.3")


def test_rounding_policies_discrete_packing():
    # Packaging 50 parts into boxes of 6 -> 50 / 6 = 8.3333333333...
    # ROUND_UP must yield exactly 9 boxes (you cannot buy 8.33 boxes)
    res = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PACKING_RATIO,
            parameters={"units_per_pack": Decimal("6")},
            production_quantity=Decimal("50"),
            rounding_policy=RoundingPolicy.ROUND_UP,
            rounding_precision=0,
            unit="BOX",
        )
    )
    assert res.final_calculated_requirement == Decimal("9")
    assert any("ROUND_UP" in step.description for step in res.calculation_steps)

    # ROUND_DOWN yields 8
    res_down = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PACKING_RATIO,
            parameters={"units_per_pack": Decimal("6")},
            production_quantity=Decimal("50"),
            rounding_policy=RoundingPolicy.ROUND_DOWN,
            rounding_precision=0,
        )
    )
    assert res_down.final_calculated_requirement == Decimal("8")

    # ROUND_HALF_UP with 2 decimal places
    res_half = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PACKING_RATIO,
            parameters={"units_per_pack": Decimal("6")},
            production_quantity=Decimal("50"),
            rounding_policy=RoundingPolicy.ROUND_HALF_UP,
            rounding_precision=2,
        )
    )
    assert res_half.final_calculated_requirement == Decimal("8.33")


def test_all_rule_types_evaluation_vectors():
    # 1. PRODUCTION_RATE: 1000 * 0.05 * 1.02 = 51.000
    r1 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PRODUCTION_RATE,
            parameters={"rate": Decimal("0.05"), "scrap_factor": Decimal("0.02")},
            production_quantity=Decimal("1000"),
        )
    )
    assert r1.final_calculated_requirement == Decimal("51.000")

    # 2. AREA_COVERAGE: (500 * 2.0 / 10.0) * 1.10 = 110.000
    r2 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.AREA_COVERAGE,
            parameters={"area_per_unit": Decimal("2.0"), "coverage": Decimal("10.0"), "loss_factor": Decimal("0.10")},
            production_quantity=Decimal("500"),
        )
    )
    assert r2.final_calculated_requirement == Decimal("110.000")

    # 3. TOOL_LIFE: (10000 * 2) / 5000 = 4.0
    r3 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.TOOL_LIFE,
            parameters={"operations_per_unit": Decimal("2"), "tool_life": Decimal("5000")},
            production_quantity=Decimal("10000"),
        )
    )
    assert r3.final_calculated_requirement == Decimal("4")

    # 4. FIXED_QUANTITY: 25.0
    r4 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.FIXED_QUANTITY,
            parameters={"quantity": Decimal("25.0")},
            production_quantity=Decimal("99999"),
        )
    )
    assert r4.final_calculated_requirement == Decimal("25.0")

    # 5. PLANT_REQUEST: requested 150 overrides default
    r5 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.PLANT_REQUEST,
            parameters={"default_quantity": Decimal("50.0")},
            requested_quantity=Decimal("150.0"),
        )
    )
    assert r5.final_calculated_requirement == Decimal("150.0")

    # 6. MAINTENANCE: 20 + (1000 * 0.05) = 70.00
    r6 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.MAINTENANCE,
            parameters={"fixed_amount": Decimal("20.0"), "variable_rate": Decimal("0.05")},
            production_quantity=Decimal("1000"),
        )
    )
    assert r6.final_calculated_requirement == Decimal("70.00")

    # 7. MIN_MAX: 100 * 0.1 = 10, clamped to min 20
    r7 = evaluate_rule(
        RuleCalculationInput(
            rule_type=RuleType.MIN_MAX,
            parameters={"min_quantity": Decimal("20.0"), "max_quantity": Decimal("100.0"), "base_rate": Decimal("0.1")},
            production_quantity=Decimal("100"),
        )
    )
    assert r7.final_calculated_requirement == Decimal("20.0")


# ==========================================================
# 3. Database & REST API Integration Tests
# ==========================================================

@pytest.fixture
def rules_api_setup():
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

    # Create admin user
    role = Role(id=uuid4(), code="ADMIN", name="Admin Role")
    user = User(
        id=uuid4(),
        username="rules_admin",
        password_hash="dummy_hash",
        is_active=True,
        roles=[role],
    )
    db.add(user)

    # Master seeds
    u_kg = Unit(id=uuid4(), code="KG", name="Kilogram", is_active=True)
    db.add(u_kg)

    cons = Consumable(id=uuid4(), code="CONS-PAINT-01", name="Industrial Epoxy Paint", unit_id=u_kg.id, is_active=True)
    cons_inactive = Consumable(id=uuid4(), code="CONS-OLD-PAINT", name="Discontinued Paint", unit_id=u_kg.id, is_active=False)
    db.add_all([cons, cons_inactive])

    prod = Product(id=uuid4(), code="PRD-ENCLOSURE-01", name="Steel Control Enclosure", uom="PCS", is_active=True)
    db.add(prod)

    plant = Plant(id=uuid4(), name="Plant Pune 01", location="Pune", is_active=True)
    db.add(plant)

    proc = Process(id=uuid4(), name="Powder Coating", description="Electrostatic coating", is_active=True)
    db.add(proc)

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
        seeds = {
            "u_kg": u_kg,
            "cons": cons,
            "cons_inactive": cons_inactive,
            "prod": prod,
            "plant": plant,
            "proc": proc,
        }
        yield client, db, headers, seeds

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_consumption_norm_crud_and_versioning(rules_api_setup):
    client, db, headers, seeds = rules_api_setup

    # 1. Create initial norm (version 1)
    payload_v1 = {
        "rule_type": "AREA_COVERAGE",
        "consumable_id": str(seeds["cons"].id),
        "product_id": str(seeds["prod"].id),
        "process_id": str(seeds["proc"].id),
        "plant_id": str(seeds["plant"].id),
        "parameters": {
            "area_per_unit": "2.5",
            "coverage": "10.0",
            "loss_factor": "0.05",
        },
        "unit_id": str(seeds["u_kg"].id),
        "rounding_policy": "ROUND_HALF_UP",
        "rounding_precision": 2,
        "effective_from": str(date.today()),
    }
    resp1 = client.post("/api/v1/consumption-norms", headers=headers, json=payload_v1)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["version"] == 1
    assert data1["rule_type"] == "AREA_COVERAGE"
    assert data1["consumable_code"] == "CONS-PAINT-01"
    assert data1["is_active"] is True

    # 2. Creating another norm for same product/process/consumable creates version 2 and deactivates v1
    payload_v2 = {**payload_v1, "parameters": {"area_per_unit": "2.8", "coverage": "10.0", "loss_factor": "0.05"}}
    resp2 = client.post("/api/v1/consumption-norms", headers=headers, json=payload_v2)
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["version"] == 2
    assert data2["is_active"] is True

    # Check v1 is superseded (is_active is False)
    check_v1 = client.get(f"/api/v1/consumption-norms/{data1['id']}", headers=headers)
    assert check_v1.status_code == 200
    assert check_v1.json()["is_active"] is False


def test_consumption_norm_rejects_inactive_entity(rules_api_setup):
    client, db, headers, seeds = rules_api_setup

    # Attempt to create norm with inactive consumable
    payload = {
        "rule_type": "FIXED_QUANTITY",
        "consumable_id": str(seeds["cons_inactive"].id),
        "parameters": {"quantity": "10.0"},
        "unit_id": str(seeds["u_kg"].id),
        "effective_from": str(date.today()),
    }
    resp = client.post("/api/v1/consumption-norms", headers=headers, json=payload)
    assert resp.status_code == 400
    assert "inactive" in resp.json()["message"].lower()


def test_evaluate_endpoint_end_to_end(rules_api_setup):
    client, db, headers, seeds = rules_api_setup

    # 1. Create approved norm for Area Coverage
    client.post(
        "/api/v1/consumption-norms",
        headers=headers,
        json={
            "rule_type": "AREA_COVERAGE",
            "consumable_id": str(seeds["cons"].id),
            "product_id": str(seeds["prod"].id),
            "process_id": str(seeds["proc"].id),
            "parameters": {
                "area_per_unit": "2.0",
                "coverage": "8.0",
                "loss_factor": "0.10",
            },
            "unit_id": str(seeds["u_kg"].id),
            "rounding_policy": "ROUND_HALF_UP",
            "rounding_precision": 2,
            "effective_from": str(date.today()),
        },
    )

    # 2. Evaluate requirement for 1000 units of product:
    # Total area = 1000 * 2.0 = 2000
    # Base req = 2000 / 8.0 = 250
    # With 10% loss factor = 250 * 1.10 = 275.00
    eval_payload = {
        "consumable_id": str(seeds["cons"].id),
        "product_id": str(seeds["prod"].id),
        "process_id": str(seeds["proc"].id),
        "production_quantity": "1000",
    }
    eval_resp = client.post("/api/v1/consumption-norms/evaluate", headers=headers, json=eval_payload)
    assert eval_resp.status_code == 200
    res = eval_resp.json()
    calc = res["calculation"]
    assert calc["rule_type"] == "AREA_COVERAGE"
    assert Decimal(str(calc["final_calculated_requirement"])) == Decimal("275.00")
    assert len(calc["calculation_steps"]) >= 3
    assert calc["unit"] == "KG"


def test_evaluate_missing_rule_returns_404(rules_api_setup):
    client, db, headers, seeds = rules_api_setup

    eval_payload = {
        "consumable_id": str(seeds["cons"].id),
        "product_id": str(uuid4()),  # Unconfigured product
        "production_quantity": "500",
    }
    resp = client.post("/api/v1/consumption-norms/evaluate", headers=headers, json=eval_payload)
    assert resp.status_code == 404
    assert "no active" in resp.json()["message"].lower()
