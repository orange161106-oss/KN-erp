from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import AreaCoverageParams, CalculationStep, RuleCalculationInput


class AreaCoverageHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = AreaCoverageParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        total_area = input_data.production_quantity * params.area_per_unit
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate total surface area from production quantity and area per unit",
                formula=f"{input_data.production_quantity} * {params.area_per_unit}",
                result=total_area,
            )
        )

        base_qty = total_area / params.coverage
        steps.append(
            CalculationStep(
                step_number=2,
                description="Calculate baseline consumable requirement using rated coverage",
                formula=f"{total_area} / {params.coverage}",
                result=base_qty,
            )
        )

        if params.loss_factor > 0:
            factor = Decimal("1") + params.loss_factor
            raw_qty = base_qty * factor
            steps.append(
                CalculationStep(
                    step_number=3,
                    description=f"Apply overspray/process loss allowance of {params.loss_factor * 100}%",
                    formula=f"{base_qty} * (1 + {params.loss_factor})",
                    result=raw_qty,
                )
            )
        else:
            raw_qty = base_qty

        return raw_qty, steps
