from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from app.domain.rules.models import CalculationStep, RuleCalculationInput
from app.domain.rules.types import RoundingPolicy


class BaseRuleHandler(ABC):
    @abstractmethod
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        """Calculates raw requirement and records human-readable audit steps.

        Returns:
            tuple[Decimal, list[CalculationStep]]: (raw_requirement, steps)
        """
        pass

    @staticmethod
    def apply_rounding(value: Decimal, policy: RoundingPolicy | str, precision: int) -> Decimal:
        """Applies configured rounding policy with high-precision Decimal quantization."""
        if isinstance(policy, str):
            policy = RoundingPolicy.parse(policy)

        if policy == RoundingPolicy.NONE:
            return value

        # Exponent format for Decimal.quantize, e.g. 0 -> Decimal('1'), 2 -> Decimal('0.01')
        if precision <= 0:
            exp = Decimal("1")
        else:
            exp = Decimal("1e-" + str(precision))

        if policy in (RoundingPolicy.ROUND_UP, RoundingPolicy.ROUNDUP, RoundingPolicy.CEILING):
            return value.quantize(exp, rounding=ROUND_CEILING)
        elif policy in (RoundingPolicy.ROUND_HALF_UP, RoundingPolicy.ROUND):
            return value.quantize(exp, rounding=ROUND_HALF_UP)
        elif policy in (RoundingPolicy.ROUND_DOWN, RoundingPolicy.ROUNDDOWN, RoundingPolicy.FLOOR):
            return value.quantize(exp, rounding=ROUND_FLOOR)

        return value
