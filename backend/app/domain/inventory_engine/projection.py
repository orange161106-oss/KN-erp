"""Pure event projection. No persistence, permissions, clocks or implicit demand spread."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

ZERO = Decimal('0.0000')


@dataclass(frozen=True)
class Event:
    source_id: str
    at: datetime
    quantity: Decimal


@dataclass(frozen=True)
class Floor:
    source_id: str
    at: datetime
    quantity: Decimal


def condition(balance: Decimal, floor: Decimal | None) -> str:
    if floor is None:
        return 'UNKNOWN'
    if balance < floor:
        return 'BELOW_MSL'
    return 'AT_MSL' if balance == floor else 'ABOVE_MSL'


def calculate(*, opening: Decimal, baseline: datetime, cutoff: datetime,
              receipts: tuple[Event, ...], demands: tuple[Event, ...],
              floors: tuple[Floor, ...], lead_time_at: datetime | None = None) -> dict:
    """Return the state strictly before cutoff; event rows show before/after state.

    An identical timestamp gives no authority to process supply before demand.
    Reject ambiguous mixed events, including stock/MSL changes at the same instant.
    """
    dates = [baseline, cutoff, *[row.at for row in (*receipts, *demands, *floors)]]
    if lead_time_at is not None:
        dates.append(lead_time_at)
    if any(value.tzinfo is None or value.utcoffset() is None for value in dates) or cutoff <= baseline:
        raise ValueError('An aware cutoff after baseline is required')
    quantities = [opening, *[row.quantity for row in (*receipts, *demands, *floors)]]
    if any(not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value >= Decimal('100000000000000') or value != value.quantize(Decimal('.0001')) for value in quantities):
        raise ValueError('Exact nonnegative four-place Decimal inputs are required')
    for rows in (receipts, demands, floors):
        if len({row.source_id for row in rows}) != len(rows):
            raise ValueError('Duplicate source input')
    if len({row.at for row in floors}) != len(floors):
        raise ValueError('Conflicting MSL effective times')
    if any(row.at <= baseline for row in (*receipts, *demands)):
        raise ValueError('Remaining stock events must follow the baseline')

    initial_floor = max((row for row in floors if row.at <= baseline), key=lambda row: row.at, default=None)
    floor = initial_floor.quantity if initial_floor else None
    initial_condition = condition(opening, floor)
    groups: dict[datetime, dict] = {}
    excluded = []
    for kind, rows in (('receipt', receipts), ('demand', demands), ('msl', floors)):
        for row in rows:
            if row.at <= baseline:
                continue
            if row.at >= cutoff:
                excluded.append({'source_id': f'{kind}:{row.source_id}', 'reason': 'AT_OR_AFTER_CUTOFF', 'quantity': row.quantity})
                continue
            group = groups.setdefault(row.at, {'receipt': [], 'demand': [], 'msl': []})
            group[kind].append(row)
    if any(sum(bool(rows) for rows in group.values()) > 1 for group in groups.values()):
        return {'status': 'INCOMPLETE', 'cutoff': cutoff, 'opening_stock': opening,
                'current_msl': floor, 'current_msl_condition': initial_condition, 'excluded': excluded,
                'limitations': [{'code': 'TIMING_ORDER_UNCONFIRMED', 'message': 'Mixed events share a timestamp. Supply, demand and MSL ordering needs source confirmation.', 'blocks_projection': True}]}

    timeline = []
    balance = opening
    first_breach = None
    previous_condition = initial_condition
    # Keep sums exact even when many individually valid quantities are combined.
    with localcontext() as ctx:
        ctx.prec = 50
        for at, group in sorted(groups.items()):
            before = balance
            incoming = sum((row.quantity for row in group['receipt']), ZERO)
            demand = sum((row.quantity for row in group['demand']), ZERO)
            balance += incoming - demand
            if group['msl']:
                floor = group['msl'][0].quantity
            comparison = condition(balance, floor)
            if comparison == 'BELOW_MSL' and first_breach is None and previous_condition != 'BELOW_MSL' and initial_floor is not None:
                first_breach = at
            previous_condition = comparison
            timeline.append({'at': at, 'balance_before': before, 'receipts': incoming,
                             'requirements': demand, 'balance_after': balance, 'msl': floor,
                             'msl_condition': comparison,
                             'sources': sorted(f'{kind}:{row.source_id}' for kind, rows in group.items() for row in rows)})
    limitations = []
    if initial_floor is None:
        limitations.append({'code': 'MSL_UNCONFIGURED', 'message': 'No source-approved MSL is effective at the stock snapshot; the first MSL breach cannot be established.', 'blocks_projection': False})
    lead_balance = None
    if lead_time_at is None:
        limitations.append({'code': 'LEAD_TIME_UNCONFIGURED', 'message': 'No approved lead-time interval is supplied.', 'blocks_projection': False})
    elif not baseline < lead_time_at <= cutoff:
        limitations.append({'code': 'LEAD_TIME_OUTSIDE_COVERAGE', 'message': 'Lead-time availability lies outside the projected interval.', 'blocks_projection': False})
    else:
        lead_balance = next((row['balance_after'] for row in reversed(timeline) if row['at'] < lead_time_at), opening)
    return {'status': 'COMPLETE', 'cutoff': cutoff, 'opening_stock': opening, 'projected_stock': balance,
            'current_msl': initial_floor.quantity if initial_floor else None,
            'projected_msl': floor, 'projected_msl_condition': condition(balance, floor),
            'current_msl_condition': initial_condition, 'first_future_breach_at': first_breach,
            'future_breach': None if initial_floor is None else first_breach is not None,
            'lead_time_balance': lead_balance, 'timeline': timeline, 'excluded': excluded, 'limitations': limitations}
