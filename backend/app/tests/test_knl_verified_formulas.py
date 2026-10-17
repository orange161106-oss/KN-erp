from decimal import Decimal
import pytest

from app.domain.rules import (
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
    validate_rule_parameters,
)
from app.domain.rules.errors import InvalidDenominatorError, ParameterValidationError


# ==============================================================================
# 1. PRODUCTION_RATE Tests
# ==============================================================================

def test_production_rate_normal():
    # 10,000 pcs * 0.005 kg/pc = 50 kg
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PRODUCTION_RATE,
        parameters={"rate": Decimal("0.005")},
        production_quantity=Decimal("10000"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("50.000")
    assert len(result.calculation_steps) == 1
    assert "10000 * 0.005" in result.calculation_steps[0].formula


def test_production_rate_with_alias_and_scrap():
    # Using 'consumption_rate' alias and scrap_factor 5%
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PRODUCTION_RATE,
        parameters={"consumption_rate": Decimal("0.02"), "scrap_factor": Decimal("0.05")},
        production_quantity=Decimal("1000"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    # 1,000 * 0.02 = 20. 20 * 1.05 = 21.0
    assert result.final_calculated_requirement == Decimal("21.000")
    assert len(result.calculation_steps) == 2


def test_production_rate_zero_quantity():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PRODUCTION_RATE,
        parameters={"rate": Decimal("0.005")},
        production_quantity=Decimal("0"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("0")


def test_production_rate_invalid_negative_rate():
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.PRODUCTION_RATE, {"rate": Decimal("-0.05")})


def test_production_rate_zero_rate():
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.PRODUCTION_RATE, {"rate": Decimal("0")})


# ==============================================================================
# 2. AREA_COVERAGE Tests
# ==============================================================================

def test_area_coverage_normal():
    # 1,000 parts * 2.5 sq ft / 100 sq ft/kg = 25 kg
    rule_input = RuleCalculationInput(
        rule_type=RuleType.AREA_COVERAGE,
        parameters={"area_per_unit": Decimal("2.5"), "coverage": Decimal("100")},
        production_quantity=Decimal("1000"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("25")
    assert len(result.calculation_steps) == 2


def test_area_coverage_with_overspray_loss():
    # 1,000 parts * 2.5 sq ft / 100 sq ft/kg * (1 + 0.10 loss) = 27.5 kg
    rule_input = RuleCalculationInput(
        rule_type=RuleType.AREA_COVERAGE,
        parameters={
            "area_per_unit": Decimal("2.5"),
            "coverage": Decimal("100"),
            "loss_factor": Decimal("0.10"),
        },
        production_quantity=Decimal("1000"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("27.5")
    assert len(result.calculation_steps) == 3


def test_area_coverage_zero_coverage_denominator():
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.AREA_COVERAGE,
            {"area_per_unit": Decimal("2.5"), "coverage": Decimal("0")},
        )


# ==============================================================================
# 3. PACKING_RATIO Tests
# ==============================================================================

def test_packing_ratio_roundup_cartons():
    # 500 pcs / 24 pcs per carton = 20.8333... -> ROUNDUP = 21 cartons
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PACKING_RATIO,
        parameters={"pieces_per_pack": Decimal("24")},
        production_quantity=Decimal("500"),
        rounding_policy=RoundingPolicy.ROUNDUP,
        rounding_precision=0,
        unit="BOX",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("21")


def test_packing_ratio_with_material_factor():
    # 1,000 pcs / 50 pcs per pack = 20 packs; 20 packs * 1.5 m bubble sheet = 30 m
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PACKING_RATIO,
        parameters={
            "units_per_pack": Decimal("50"),
            "material_per_pack": Decimal("1.5"),
        },
        production_quantity=Decimal("1000"),
        unit="MTR",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("30.0")


def test_packing_ratio_zero_denominator():
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(RuleType.PACKING_RATIO, {"units_per_pack": Decimal("0")})


# ==============================================================================
# 4. TOOL_LIFE Tests
# ==============================================================================

def test_tool_life_roundup():
    # 5,000 parts * 1 op / 2,000 ops per tap = 2.5 -> ROUNDUP = 3 taps
    rule_input = RuleCalculationInput(
        rule_type=RuleType.TOOL_LIFE,
        parameters={"operations_per_unit": Decimal("1"), "tool_life": Decimal("2000")},
        production_quantity=Decimal("5000"),
        rounding_policy=RoundingPolicy.ROUNDUP,
        rounding_precision=0,
        unit="NOS",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("3")


def test_tool_life_multi_operations():
    # 1,200 parts * 2 ops = 2,400 ops; 2,400 / 500 ops per bit = 4.8 -> ROUNDUP = 5 bits
    rule_input = RuleCalculationInput(
        rule_type=RuleType.TOOL_LIFE,
        parameters={"operations_per_part": Decimal("2"), "tool_life": Decimal("500")},
        production_quantity=Decimal("1200"),
        rounding_policy=RoundingPolicy.ROUNDUP,
        rounding_precision=0,
        unit="NOS",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("5")


def test_tool_life_zero_denominator():
    with pytest.raises(InvalidDenominatorError):
        validate_rule_parameters(
            RuleType.TOOL_LIFE,
            {"operations_per_unit": Decimal("1"), "tool_life": Decimal("0")},
        )


# ==============================================================================
# 5. FIXED_QUANTITY Tests
# ==============================================================================

def test_fixed_quantity_normal():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.FIXED_QUANTITY,
        parameters={"quantity": Decimal("50")},
        production_quantity=Decimal("10000"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("50")


def test_fixed_quantity_alias():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.FIXED_QUANTITY,
        parameters={"fixed_quantity": Decimal("75.5")},
        production_quantity=Decimal("0"),
        unit="LTR",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("75.5")


def test_fixed_quantity_invalid():
    with pytest.raises(ParameterValidationError):
        validate_rule_parameters(RuleType.FIXED_QUANTITY, {"quantity": Decimal("-10")})


# ==============================================================================
# 6. PLANT_REQUEST Tests
# ==============================================================================

def test_plant_request_department_summation():
    # Workbook Row 46: BG = SUM(P1..P5, Tool Room, Quality, PMD, Maintenance, etc.)
    dept_requests = {
        "Plant 1": Decimal("600"),
        "Plant 2": Decimal("700"),
        "Tool Room": Decimal("150"),
        "Quality": Decimal("100"),
        "Maintenance": Decimal("1000"),
    }
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PLANT_REQUEST,
        parameters={"department_requests": dept_requests},
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("2550")
    assert "Sum plant and department requests" in result.calculation_steps[0].description


def test_plant_request_explicit_scalar():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PLANT_REQUEST,
        parameters={"default_quantity": Decimal("100")},
        requested_quantity=Decimal("350"),
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("350")


def test_plant_request_default_fallback():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.PLANT_REQUEST,
        parameters={"default_quantity": Decimal("100")},
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("100")


# ==============================================================================
# 7. MAINTENANCE Tests
# ==============================================================================

def test_maintenance_combined():
    # Fixed base: 20 L + (5,000 parts * 0.002 L/part) = 20 + 10 = 30 L
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MAINTENANCE,
        parameters={"fixed_amount": Decimal("20"), "variable_rate": Decimal("0.002")},
        production_quantity=Decimal("5000"),
        unit="LTR",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("30.000")


def test_maintenance_zero_variable():
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MAINTENANCE,
        parameters={"fixed_amount": Decimal("50"), "variable_rate": Decimal("0")},
        production_quantity=Decimal("5000"),
        unit="LTR",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("50")


# ==============================================================================
# 8. MIN_MAX & STOCK POLICY Tests (Authoritative KNL Formulas)
# ==============================================================================

def test_knl_min_max_co2_golden_case():
    """Authoritative KNL Formula Map Golden Case: Row 11 & 22 (CO2).

    Requirement = 2,550 kg
    Working days = 26
    MSL days = 10
    Daily requirement = 2550 / 26 = 98.07692...
    MSL = ROUNDUP(98.07692 * 10, 0) = 981 kg
    Current stock = 235 kg
    Incoming PO = 0 kg
    MOQ = 675 kg
    Available supply = 235 + 0 = 235 kg
    Gross need = MSL + requirement - available supply = 981 + 2550 - 235 = 3,296 kg
    Order Qty = max(3296, 675) = 3,296 kg
    """
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MIN_MAX,
        parameters={
            "monthly_requirement": Decimal("2550"),
            "working_days": Decimal("26"),
            "msl_days": Decimal("10"),
            "current_stock": Decimal("235"),
            "incoming_po": Decimal("0"),
            "moq": Decimal("675"),
        },
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("3296")

    # Step-by-step audit verification
    step_formulas = [s.formula for s in result.calculation_steps]
    assert any("2550 / 26" in f for f in step_formulas)
    assert any("ROUNDUP" in f and "10" in f for f in step_formulas)
    assert any("235 + 0" in f for f in step_formulas)
    assert any("981 + 2550 - 235" in f for f in step_formulas)


def test_knl_min_max_incoming_po_isolation():
    """Section 13: Confirmed incoming PO quantity MUST be netted to prevent double ordering.

    Available Supply = Current Stock (235) + Confirmed Incoming PO (1000) = 1,235 kg
    Gross need = 981 + 2550 - 1235 = 2,296 kg
    Order Qty = 2,296 kg
    """
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MIN_MAX,
        parameters={
            "monthly_requirement": Decimal("2550"),
            "working_days": Decimal("26"),
            "msl_days": Decimal("10"),
            "current_stock": Decimal("235"),
            "incoming_po": Decimal("1000"),
            "moq": Decimal("675"),
        },
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    assert result.final_calculated_requirement == Decimal("2296")


def test_knl_min_max_moq_elevation():
    """When gross need is positive but less than MOQ, order quantity is raised to MOQ."""
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MIN_MAX,
        parameters={
            "monthly_requirement": Decimal("500"),
            "working_days": Decimal("26"),
            "msl_days": Decimal("10"),
            "current_stock": Decimal("400"),
            "incoming_po": Decimal("0"),
            "moq": Decimal("675"),
        },
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    # Daily = 500 / 26 = 19.2307... -> MSL = ROUNDUP(192.307) = 193.
    # Gross need = 193 + 500 - 400 = 293.
    # 293 < MOQ (675) -> Order = 675.
    assert result.final_calculated_requirement == Decimal("675")


def test_knl_min_max_order_multiple():
    """When order multiple is specified, order quantity is rounded up to the next multiple."""
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MIN_MAX,
        parameters={
            "monthly_requirement": Decimal("2550"),
            "working_days": Decimal("26"),
            "msl_days": Decimal("10"),
            "current_stock": Decimal("235"),
            "incoming_po": Decimal("0"),
            "moq": Decimal("675"),
            "order_multiple": Decimal("50"),
        },
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    # Gross need = 3,296 -> ceil(3296 / 50) * 50 = 66 * 50 = 3,300 kg.
    assert result.final_calculated_requirement == Decimal("3300")


def test_knl_min_max_zero_order_when_surplus():
    """When available supply satisfies both MSL and monthly requirement, order qty is 0."""
    rule_input = RuleCalculationInput(
        rule_type=RuleType.MIN_MAX,
        parameters={
            "monthly_requirement": Decimal("1000"),
            "working_days": Decimal("26"),
            "msl_days": Decimal("10"),
            "current_stock": Decimal("2000"),
            "incoming_po": Decimal("500"),
            "moq": Decimal("675"),
        },
        unit="KG",
    )
    result = evaluate_rule(rule_input)
    # Daily = 1000 / 26 = 38.46 -> MSL = 385.
    # Available = 2500.
    # Gross need = 385 + 1000 - 2500 = -1115 <= 0 -> Order = 0.
    assert result.final_calculated_requirement == Decimal("0")


# ==============================================================================
# 9. ROUNDING POLICIES Tests
# ==============================================================================

@pytest.mark.parametrize(
    "policy_name, expected",
    [
        ("NONE", Decimal("12.3456")),
        ("ROUND", Decimal("12.35")),
        ("ROUND_HALF_UP", Decimal("12.35")),
        ("ROUNDUP", Decimal("12.35")),
        ("ROUND_UP", Decimal("12.35")),
        ("CEILING", Decimal("12.35")),
        ("ROUNDDOWN", Decimal("12.34")),
        ("ROUND_DOWN", Decimal("12.34")),
        ("FLOOR", Decimal("12.34")),
    ],
)
def test_all_rounding_policy_aliases(policy_name, expected):
    from app.domain.rules.handlers.base import BaseRuleHandler
    policy = RoundingPolicy.parse(policy_name)
    rounded = BaseRuleHandler.apply_rounding(Decimal("12.3456"), policy, precision=2)
    assert rounded == expected
