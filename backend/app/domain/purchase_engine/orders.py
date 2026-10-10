from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext

from app.domain.purchase_engine.recommendation import Constraint, NAMES, calculate

ROUNDING = {'HALF_UP': ROUND_HALF_UP, 'HALF_EVEN': ROUND_HALF_EVEN, 'DOWN': ROUND_DOWN}


def line_value(quantity: Decimal, rate: Decimal, places: int, rounding: str) -> Decimal:
    if (not isinstance(quantity, Decimal) or not isinstance(rate, Decimal)
            or not quantity.is_finite() or not rate.is_finite() or quantity <= 0 or rate < 0
            or type(places) is not int or not 0 <= places <= 4 or rounding not in ROUNDING):
        raise ValueError('Exact quantity, rate and explicit currency rounding are required')
    with localcontext() as ctx:
        ctx.prec = 80
        value = (quantity * rate).quantize(Decimal(1).scaleb(-places), rounding=ROUNDING[rounding])
        if value >= Decimal('1e30'):
            raise ValueError('Line value exceeds supported precision')
        return value


def pending_quantity(ordered: Decimal, cancelled: Decimal, fulfilled: Decimal | None) -> Decimal | None:
    """Future fulfilment adapter must provide a source-approved cumulative quantity."""
    for value in (ordered, cancelled, fulfilled):
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
            raise ValueError('Exact nonnegative quantities are required')
    with localcontext() as ctx:
        ctx.prec = 80
        if cancelled > ordered or (fulfilled is not None and cancelled + fulfilled > ordered):
            raise ValueError('Cancellation and fulfilment exceed the order')
        return None if fulfilled is None else ordered - cancelled - fulfilled


def satisfies_order_terms(quantity: Decimal, source_constraints: dict) -> bool:
    """Reuse M5.1 supplier/order constraints when splitting approved demand.

    Stock-at-receipt maximum is assessed in the original recommendation; it is
    not an order increment and cannot be recomputed using a made-up stock balance.
    """
    constraints = {name: Constraint(source_constraints[name]['state'],
                   Decimal(source_constraints[name]['value']) if source_constraints[name]['value'] is not None else None)
                   for name in NAMES}
    constraints['max_stock_quantity'] = Constraint('NOT_APPLICABLE')
    result = calculate(target=quantity, projected=Decimal('0'), constraints=constraints)
    return result['recommended_quantity'] == quantity
