from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, PackingRatioParams, RuleCalculationInput


class PackingRatioHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = PackingRatioParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        raw_qty = input_data.production_quantity / params.units_per_pack
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate packaging requirement from production quantity and units per pack",
                formula=f"{input_data.production_quantity} / {params.units_per_pack}",
                result=raw_qty,
            )
        )

        return raw_qty, steps
