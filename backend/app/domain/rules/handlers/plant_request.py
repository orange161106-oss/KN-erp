from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, PlantRequestParams, RuleCalculationInput


class PlantRequestHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = PlantRequestParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        if input_data.requested_quantity is not None:
            raw_qty = input_data.requested_quantity
            steps.append(
                CalculationStep(
                    step_number=1,
                    description="Use explicitly requested quantity submitted by plant",
                    formula=f"{input_data.requested_quantity}",
                    result=raw_qty,
                )
            )
        else:
            raw_qty = params.default_quantity
            steps.append(
                CalculationStep(
                    step_number=1,
                    description="Use configured default quantity in absence of explicit plant request",
                    formula=f"{params.default_quantity}",
                    result=raw_qty,
                )
            )

        return raw_qty, steps
