"""Exact normalization for source ERP history; no warehouse posting authority."""
from decimal import Decimal, localcontext
from enum import StrEnum

from app.core.errors import ApplicationError


class Movement(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    RETURN = "RETURN"


STOCK_STEP = Decimal("0.0001")
STOCK_LIMIT = Decimal("100000000000000")


def stock_quantity(quantity: Decimal, factor: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        result = quantity * factor
        if result <= 0 or result >= STOCK_LIMIT or result != result.quantize(STOCK_STEP):
            raise ApplicationError("INVALID_CONVERSION", "Conversion must produce an exact positive stock quantity with at most four decimal places.", 422)
        return result.quantize(STOCK_STEP)


def signed_change(movement: Movement, quantity: Decimal) -> Decimal:
    return -quantity if movement == Movement.ISSUE else quantity
