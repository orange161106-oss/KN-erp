"""Owner-approved Plan!AD4 / AE4 from KNL-Formula.xlsx (2026-10-17).

This monthly rule is separate from the timed M5.1 receipt assessment. Inputs are
already in the requirement's stock unit. Pending POs and pack multiples are not
operands in the supplied company formula.
"""
from decimal import Decimal, localcontext


RULE_VERSION = 'KNL_MONTHLY_V1'
FORMULA_REFERENCE = 'KNL-Formula.xlsx: Sheet1 rows 9, 12, 14, 20, 23-24; Plan!AD4 / AE4'


def calculate_monthly_purchase(*, required: Decimal, closing_stock: Decimal,
                               msl: Decimal, moq: Decimal, rate: Decimal | None = None) -> dict:
    quantities = (required, closing_stock, msl, moq)
    if any(not isinstance(value, Decimal) or not value.is_finite()
           or abs(value) >= Decimal('1e14') or value != value.quantize(Decimal('.0001'))
           for value in quantities):
        raise ValueError('Finite stock-unit quantities with at most four decimal places are required.')
    if required < 0 or msl < 0 or moq < 0:
        raise ValueError('Requirement, MSL and MOQ cannot be negative.')
    if rate is not None and (not isinstance(rate, Decimal) or not rate.is_finite() or rate < 0):
        raise ValueError('Rate must be a nonnegative exact decimal when supplied.')
    with localcontext() as ctx:
        ctx.prec = 80
        gap = msl + required - closing_stock
        quantity = max(gap, moq) if gap > 0 else Decimal('0')
        if abs(gap) >= Decimal('1e14') or quantity >= Decimal('1e14'):
            raise ValueError('Monthly purchase quantity exceeds supported precision.')
        return {'raw_quantity': gap.quantize(Decimal('.0001')),
                'recommended_quantity': quantity.quantize(Decimal('.0001')),
                # AE4 is the exact product; no unapproved currency rounding.
                'purchase_value': quantity * rate if rate is not None else None}
