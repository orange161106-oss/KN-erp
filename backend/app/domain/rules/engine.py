from typing import Any
from pydantic import BaseModel

from app.domain.rules.errors import ParameterValidationError, RuleDomainError
from app.domain.rules.handlers import (
    AreaCoverageHandler,
    BaseRuleHandler,
    FixedQuantityHandler,
    MaintenanceHandler,
    MinMaxHandler,
    PackingRatioHandler,
    PlantRequestHandler,
    ProductionRateHandler,
    ToolLifeHandler,
)
from app.domain.rules.models import (
    AreaCoverageParams,
    CalculationResult,
    CalculationStep,
    FixedQuantityParams,
    MaintenanceParams,
    MinMaxParams,
    PackingRatioParams,
    PlantRequestParams,
    ProductionRateParams,
    RuleCalculationInput,
    ToolLifeParams,
)
from app.domain.rules.types import RoundingPolicy, RuleType

HANDLERS: dict[RuleType, BaseRuleHandler] = {
    RuleType.PRODUCTION_RATE: ProductionRateHandler(),
    RuleType.AREA_COVERAGE: AreaCoverageHandler(),
    RuleType.PACKING_RATIO: PackingRatioHandler(),
    RuleType.TOOL_LIFE: ToolLifeHandler(),
    RuleType.FIXED_QUANTITY: FixedQuantityHandler(),
    RuleType.PLANT_REQUEST: PlantRequestHandler(),
    RuleType.MAINTENANCE: MaintenanceHandler(),
    RuleType.MIN_MAX: MinMaxHandler(),
}

PARAM_MODELS: dict[RuleType, type[BaseModel]] = {
    RuleType.PRODUCTION_RATE: ProductionRateParams,
    RuleType.AREA_COVERAGE: AreaCoverageParams,
    RuleType.PACKING_RATIO: PackingRatioParams,
    RuleType.TOOL_LIFE: ToolLifeParams,
    RuleType.FIXED_QUANTITY: FixedQuantityParams,
    RuleType.PLANT_REQUEST: PlantRequestParams,
    RuleType.MAINTENANCE: MaintenanceParams,
    RuleType.MIN_MAX: MinMaxParams,
}


def validate_rule_parameters(rule_type: RuleType, parameters: dict[str, Any]) -> BaseModel:
    """Validates parameters dictionary against the strongly-typed schema for the given rule type."""
    model_cls = PARAM_MODELS.get(rule_type)
    if not model_cls:
        raise ParameterValidationError(f"Unsupported rule type '{rule_type}'.")
    return model_cls.model_validate(parameters)


def evaluate_rule(input_data: RuleCalculationInput) -> CalculationResult:
    """Pure domain evaluation of requirement calculation rules.
    Executes the appropriate handler strategy, applies rounding,
    and returns a structured, explainable CalculationResult.
    """
    handler = HANDLERS.get(input_data.rule_type)
    if not handler:
        raise RuleDomainError(f"No handler registered for rule type '{input_data.rule_type}'.")

    rounding_policy = RoundingPolicy.parse(input_data.rounding_policy)
    raw_requirement, steps = handler.calculate(input_data)
    final_requirement = handler.apply_rounding(
        raw_requirement, rounding_policy, input_data.rounding_precision
    )

    if rounding_policy != RoundingPolicy.NONE:
        steps.append(
            CalculationStep(
                step_number=len(steps) + 1,
                description=(
                    f"Apply rounding policy {rounding_policy.value} "
                    f"with precision {input_data.rounding_precision}"
                ),
                formula=f"{raw_requirement} -> {final_requirement}",
                result=final_requirement,
            )
        )

    return CalculationResult(
        rule_type=input_data.rule_type,
        rule_version=input_data.rule_version,
        parameters=input_data.parameters,
        source_production_qty=input_data.production_quantity,
        calculation_steps=steps,
        raw_requirement=raw_requirement,
        rounding_policy=rounding_policy,
        rounding_precision=input_data.rounding_precision,
        final_calculated_requirement=final_requirement,
        unit=input_data.unit,
    )
