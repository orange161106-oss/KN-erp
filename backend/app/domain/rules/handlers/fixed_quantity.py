from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, FixedQuantityParams, RuleCalculationInput


class FixedQuantityHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = FixedQuantityParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        raw_qty = params.quantity
        steps.append(
            CalculationStep(
                step_number=1,
                description="Apply fixed baseline requirement independent of production volume",
                formula=f"{params.quantity}",
                result=raw_qty,
            )
        )

        return raw_qty, steps
