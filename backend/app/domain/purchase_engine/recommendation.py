"""M5.1_V1: simultaneous constraints, exact stock-unit arithmetic, no PO side effects."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from math import lcm

ZERO = Decimal('0.0000')
LIMIT = Decimal('100000000000000')
NAMES = ('moq', 'pack_size', 'order_multiple', 'max_order_quantity', 'max_stock_quantity')


@dataclass(frozen=True)
class Constraint:
    state: str
    value: Decimal | None = None


def exact(value, *, signed=False, aggregate=False):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError('An exact finite Decimal is required')
    if (not signed and value < 0) or value.copy_abs() >= (Decimal('1e20') if aggregate else LIMIT):
        raise ValueError('Quantity is outside the supported range')
    with localcontext() as ctx:
        ctx.prec = 80
        if value != value.quantize(Decimal('.0001')):
            raise ValueError('At most four decimal places are supported')


def calculate(*, target: Decimal | None, projected: Decimal,
              constraints: dict[str, Constraint]) -> dict:
    exact(projected, signed=True, aggregate=True)
    if target is not None:
        exact(target)
    if set(constraints) != set(NAMES):
        raise ValueError('Every constraint must explicitly state its applicability')
    for name, row in constraints.items():
        if row.state not in ('APPLICABLE', 'NOT_APPLICABLE', 'UNKNOWN'):
            raise ValueError('Invalid constraint state')
        if row.state == 'APPLICABLE':
            exact(row.value)
            if name in ('pack_size', 'order_multiple') and row.value == 0:
                raise ValueError('Ordering increments must be positive')
        elif row.value is not None:
            raise ValueError('Only applicable constraints may carry quantities')
    result = dict(status='INCOMPLETE', raw_quantity=None, quantity_after_moq=None,
                  combined_increment=None, candidate_quantity=None, recommended_quantity=None,
                  stock_after_receipt=None, explanation='', limitations=[], steps=[])
    def stop(code, message, status='INCOMPLETE'):
        result.update(status=status, explanation=message)
        result['limitations'].append(dict(code=code, message=message))
        return result
    if target is None:
        return stop('TARGET_UNCONFIRMED', 'An explicit target stock quantity is required; MSL is not substituted.')
    with localcontext() as ctx:
        ctx.prec = 80
        raw = target - projected
        result['raw_quantity'] = raw
        result['steps'].append(dict(code='RAW', quantity=raw, explanation='Target stock minus projected usable stock immediately before receipt.'))
        unknown = [name for name, row in constraints.items() if row.state == 'UNKNOWN']
        if unknown:
            return stop('CONSTRAINT_UNCONFIRMED', 'Unknown constraints: ' + ', '.join(unknown))
        values = {name: row.value for name, row in constraints.items()}
        if raw <= 0:
            result.update(status='RECOMMENDED', quantity_after_moq=ZERO, candidate_quantity=ZERO,
                          recommended_quantity=ZERO, stock_after_receipt=projected,
                          explanation='Stock already meets the supplied target; no purchase is needed. MOQ does not create an order.')
            if values['max_stock_quantity'] is not None and projected > values['max_stock_quantity']:
                result['limitations'].append(dict(code='EXISTING_STOCK_ABOVE_MAXIMUM', message='Existing projected stock exceeds the supplied maximum; a purchase cannot resolve this.'))
            return result
        lower = max(raw, values['moq'] or ZERO)
        result['quantity_after_moq'] = lower
        result['steps'].append(dict(code='MOQ', quantity=lower, explanation='For positive demand, meet both raw need and the applicable MOQ.'))
        increments = [values[name] for name in ('pack_size', 'order_multiple') if values[name] is not None]
        # Integer ten-thousandths make common-multiple rounding exact, including
        # decimal increments such as 0.25 and 0.30 (combined increment 1.50).
        if increments:
            ticks = lcm(*(int(value * 10000) for value in increments))
            increment = Decimal(ticks) / Decimal(10000)
            lower_ticks = int(lower * 10000)
            candidate = Decimal(((lower_ticks + ticks - 1) // ticks) * ticks) / Decimal(10000)
            result['combined_increment'] = increment
        else:
            candidate = lower
        result['candidate_quantity'] = candidate
        result['steps'].append(dict(code='SIMULTANEOUS_INCREMENTS', quantity=candidate,
                                    explanation='Smallest quantity meeting MOQ and every applicable whole-pack/order increment together.'))
        if candidate >= LIMIT:
            return stop('QUANTITY_OUT_OF_RANGE', 'The valid rounded candidate exceeds supported purchase quantity precision.', 'CONFLICT')
        if values['max_order_quantity'] is not None and candidate > values['max_order_quantity']:
            return stop('MAX_ORDER_CONFLICT', 'The smallest compliant order exceeds the maximum order quantity; no silent capping is applied.', 'CONFLICT')
        if values['max_stock_quantity'] is not None and projected + candidate > values['max_stock_quantity']:
            return stop('MAX_STOCK_CONFLICT', 'The smallest compliant order exceeds maximum stock at receipt; review the constraints.', 'CONFLICT')
        result.update(status='RECOMMENDED', recommended_quantity=candidate, stock_after_receipt=projected + candidate,
                      explanation='The recommended quantity is the smallest quantity satisfying raw need, MOQ and all applicable increments without violating supplied maximums.')
        return result
