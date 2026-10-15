"""Direct norm selection requires no ProductPlant or route records."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.domain.rules import RuleCalculationInput, RuleType, evaluate_rule
from app.services.basic_norms import applicable_norms, match_product


def product(**values):
    return SimpleNamespace(**{"id": uuid4(), "code": "PART-A_ITEM-A", "part_number": "PART-A",
                             "item_id": "ITEM-A", "is_active": True, **values})


def norm(product_id, **values):
    unit_id, process_id, material_id = uuid4(), uuid4(), uuid4()
    return SimpleNamespace(**{
        "id": uuid4(), "product_id": product_id, "process_id": process_id, "consumable_id": material_id,
        "plant_id": None, "is_active": True, "version": 1, "effective_from": date(2026, 10, 1),
        "effective_to": None, "process": SimpleNamespace(is_active=True),
        "consumable": SimpleNamespace(is_active=True, unit_id=unit_id),
        "unit": SimpleNamespace(is_active=True), "unit_id": unit_id, "rule_type": "PRODUCTION_RATE", "parameters": {}, **values,
    })


def test_exact_product_pair_does_not_fall_back_to_another_item():
    p = product()
    assert match_product([p], part_number="PART-A", item_id="OTHER")[1] == "PRODUCT_NOT_FOUND"
    assert match_product([p], part_number=" part-a ", item_id="item-a") == (p, None)
    assert match_product([p], code="PART-A_ITEM") == (None, "PRODUCT_NOT_FOUND")


def test_part_number_ambiguity_requires_canonical_product_review():
    a, b = product(), product(item_id="ITEM-B", code="PART-A_ITEM-B")
    assert match_product([a, b], part_number="PART-A")[1] == "PRODUCT_AMBIGUOUS"
    assert match_product([a], product_id=a.id, part_number="OTHER")[1] == "PRODUCT_IDENTITY_CONFLICT"
    assert match_product([a], item_id="ITEM-A") == (a, None)


def test_product_norms_resolve_without_plant_or_separate_mapping():
    p = product()
    n = norm(p.id)
    selected, errors = applicable_norms([n], p.id, date(2026, 10, 15))
    assert selected == [n] and errors == []


def test_date_product_and_explicit_plant_scopes_are_respected():
    p = product()
    n = norm(p.id)
    plant = uuid4()
    specific = norm(p.id, plant_id=plant, process_id=n.process_id, consumable_id=n.consumable_id)
    assert applicable_norms([n, specific], p.id, date(2026, 10, 15))[0] == [n]
    assert applicable_norms([n, specific], p.id, date(2026, 10, 15), plant)[0] == [specific]
    assert applicable_norms([n], uuid4(), date(2026, 10, 15))[1][0]["code"] == "MISSING_CONSUMPTION_NORM"
    assert applicable_norms([n], p.id, date(2026, 9, 30))[1][0]["code"] == "MISSING_CONSUMPTION_NORM"


def test_two_effective_norms_for_different_materials_are_not_lost():
    identity = uuid4()
    a, b = norm(identity), norm(identity)
    assert applicable_norms([a, b], identity, date(2026, 10, 15)) == ([a, b], [])


def test_conflicting_active_versions_are_not_chosen_by_query_order():
    identity = uuid4()
    a = norm(identity)
    b = norm(identity, process_id=a.process_id, consumable_id=a.consumable_id)
    selected, errors = applicable_norms([a, b], identity, date(2026, 10, 15))
    assert not selected and errors[0]["code"] == "AMBIGUOUS_NORM"


def test_stock_netting_and_unverified_unit_conversion_cannot_become_basic_demand():
    identity = uuid4()
    assert applicable_norms([norm(identity, rule_type="MIN_MAX")], identity, date(2026, 10, 15))[1][0]["code"] == "WRONG_CALCULATION_STAGE"
    assert applicable_norms([norm(identity, unit_id=uuid4())], identity, date(2026, 10, 15))[1][0]["code"] == "NORM_UNIT_MISMATCH"


def test_bounded_min_max_preserves_existing_production_formula():
    identity = uuid4()
    bounded = norm(identity, rule_type="MIN_MAX", parameters={"base_rate": "2", "min_quantity": "10", "max_quantity": "150"})
    assert applicable_norms([bounded], identity, date(2026, 10, 15)) == ([bounded], [])
    result = evaluate_rule(RuleCalculationInput(rule_type=RuleType.MIN_MAX, rule_version=1,
        parameters=bounded.parameters, production_quantity=Decimal("100"), unit="PCS"))
    assert result.final_calculated_requirement == Decimal("150")
    stock_policy = norm(identity, rule_type="MIN_MAX", parameters={**bounded.parameters, "current_stock": "0"})
    assert applicable_norms([stock_policy], identity, date(2026, 10, 15))[1][0]["code"] == "WRONG_CALCULATION_STAGE"


def test_owner_confirmed_drill_requirement_100_parts_times_two_equals_200_units():
    result = evaluate_rule(RuleCalculationInput(rule_type=RuleType.PRODUCTION_RATE, rule_version=1,
        parameters={"rate": "2", "scrap_factor": "0"}, production_quantity=Decimal("100"), unit="PCS"))
    assert result.final_calculated_requirement == Decimal("200")
