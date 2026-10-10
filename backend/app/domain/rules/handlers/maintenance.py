from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, MaintenanceParams, RuleCalculationInput


class MaintenanceHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = MaintenanceParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        fixed_part = params.fixed_amount
        steps.append(
            CalculationStep(
                step_number=1,
                description="Determine baseline periodic maintenance consumable allocation",
                formula=f"{params.fixed_amount}",
                result=fixed_part,
            )
        )

        variable_part = input_data.production_quantity * params.variable_rate
        if params.variable_rate > 0:
            steps.append(
                CalculationStep(
                    step_number=2,
                    description="Calculate variable maintenance wear allocation from production volume",
                    formula=f"{input_data.production_quantity} * {params.variable_rate}",
                    result=variable_part,
                )
            )

        raw_qty = fixed_part + variable_part
        steps.append(
            CalculationStep(
                step_number=len(steps) + 1,
                description="Sum baseline and volume-based maintenance requirements",
                formula=f"{fixed_part} + {variable_part}",
                result=raw_qty,
            )
        )

        return raw_qty, steps
