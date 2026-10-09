from decimal import Decimal
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, PackingRatioParams, RuleCalculationInput


class PackingRatioHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = PackingRatioParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        pack_count = input_data.production_quantity / params.units_per_pack
        steps.append(
            CalculationStep(
                step_number=1,
                description="Calculate packaging pack requirement from production quantity and units per pack",
                formula=f"{input_data.production_quantity} / {params.units_per_pack}",
                result=pack_count,
            )
        )

        if params.material_per_pack != Decimal("1"):
            raw_qty = pack_count * params.material_per_pack
            steps.append(
                CalculationStep(
                    step_number=2,
                    description=f"Calculate material requirement using factor of {params.material_per_pack} per pack",
                    formula=f"{pack_count} * {params.material_per_pack}",
                    result=raw_qty,
                )
            )
        else:
            raw_qty = pack_count

        return raw_qty, steps
