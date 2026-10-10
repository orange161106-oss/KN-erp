from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, RuleCalculationInput, ToolLifeParams


class ToolLifeHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = ToolLifeParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        total_ops = input_data.production_quantity * params.operations_per_unit
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate total tool operations from production quantity and operations per unit",
                formula=f"{input_data.production_quantity} * {params.operations_per_unit}",
                result=total_ops,
            )
        )

        raw_qty = total_ops / params.tool_life
        steps.append(
            CalculationStep(
                step_number=2,
                description="Calculate required tooling replacements against rated tool life",
                formula=f"{total_ops} / {params.tool_life}",
                result=raw_qty,
            )
        )

        return raw_qty, steps
