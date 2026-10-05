from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, MinMaxParams, RuleCalculationInput


class MinMaxHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = MinMaxParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        nominal = input_data.production_quantity * params.base_rate
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate nominal requirement using base consumption rate",
                formula=f"{input_data.production_quantity} * {params.base_rate}",
                result=nominal,
            )
        )

        capped = min(params.max_quantity, nominal)
        steps.append(
            CalculationStep(
                step_number=2,
                description=f"Apply ceiling cap (max {params.max_quantity})",
                formula=f"min({params.max_quantity}, {nominal})",
                result=capped,
            )
        )

        raw_qty = max(params.min_quantity, capped)
        steps.append(
            CalculationStep(
                step_number=3,
                description=f"Apply protected floor (min {params.min_quantity})",
                formula=f"max({params.min_quantity}, {capped})",
                result=raw_qty,
            )
        )

        return raw_qty, steps
