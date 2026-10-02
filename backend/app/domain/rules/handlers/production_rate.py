from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, ProductionRateParams, RuleCalculationInput


class ProductionRateHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = ProductionRateParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        base_qty = input_data.production_quantity * params.rate
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate nominal requirement based on consumption rate per product unit",
                formula=f"{input_data.production_quantity} * {params.rate}",
                result=base_qty,
            )
        )

        if params.scrap_factor > 0:
            factor = Decimal("1") + params.scrap_factor
            raw_qty = base_qty * factor
            steps.append(
                CalculationStep(
                    step_number=2,
                    description=f"Apply scrap allowance factor of {params.scrap_factor * 100}%",
                    formula=f"{base_qty} * (1 + {params.scrap_factor})",
                    result=raw_qty,
                )
            )
        else:
            raw_qty = base_qty

        return raw_qty, steps
