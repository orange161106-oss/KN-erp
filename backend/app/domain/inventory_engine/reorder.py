"""Deterministic timing only. No purchase quantities, database or current clock."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class Calendar:
    first: date
    last: date
    working: frozenset[date]


class TimingUnavailable(ValueError):
    pass


def shift(at: datetime, days: int, direction: int, calendar: Calendar | None) -> datetime:
    """Explicit UTC convention: preserve time, exclude start, include end.

    Working-day initiation/availability occur on working dates. Initiation on a
    nonworking date rolls forward before counting. A nonworking breach needs
    intraday cutoff rules to determine an exact latest initiation timestamp.
    """
    at = at.astimezone(timezone.utc)
    try:
        if calendar is None:
            return at + timedelta(days=direction * days)
        point = at
        def covered(value):
            if not calendar.first <= value.date() <= calendar.last:
                raise TimingUnavailable('The approved working calendar does not cover the required date.')
        covered(point)
        if direction == -1 and point.date() not in calendar.working:
            raise TimingUnavailable('A nonworking crossing date requires approved intraday order/availability cutoffs; no exact deadline is inferred.')
        while point.date() not in calendar.working:
            point += timedelta(days=direction)
            covered(point)
        for _ in range(days):
            point += timedelta(days=direction)
            covered(point)
            while point.date() not in calendar.working:
                point += timedelta(days=direction)
                covered(point)
        return point
    except OverflowError:
        raise TimingUnavailable('The required date exceeds the supported timestamp range.') from None


def assess(*, baseline: datetime, evaluated_at: datetime, cutoff: datetime,
           initial_condition: str, timeline: tuple[tuple[datetime, str], ...],
           violation: str | None, boundary: str | None, days: int | None,
           calendar: Calendar | None = None, working_days: bool = False) -> dict:
    dates = [baseline, evaluated_at, cutoff, *(row[0] for row in timeline)]
    if any(at.utcoffset() is None for at in dates) or not baseline <= evaluated_at < cutoff:
        raise ValueError('Aware evaluation must lie within the projection interval')
    if any(not baseline < at < cutoff for at, _ in timeline) or len({at for at, _ in timeline}) != len(timeline):
        raise ValueError('Timeline events must be unique and inside the projection interval')
    if violation not in (None, 'BELOW_MSL', 'AT_OR_BELOW_MSL') or boundary not in (None, 'BEFORE_CROSSING', 'AT_CROSSING_ALLOWED'):
        raise ValueError('Unsupported policy')
    if days is not None and (type(days) is not int or not 0 <= days <= 3660):
        raise ValueError('Lead time must be an exact nonnegative bounded day count')
    if calendar and (not working_days or not 0 <= (calendar.last - calendar.first).days <= 3660
                     or any(not calendar.first <= day <= calendar.last for day in calendar.working)):
        raise ValueError('Calendar must match the working-day basis and have bounded consistent coverage')
    result = dict(status='INCOMPLETE', reorder_required=None, already_breached=None,
                  expected_msl_crossing_at=None, crossing_time_kind=None, latest_safe_order_at=None,
                  latest_safe_order_inclusive=None, earliest_usable_at_if_ordered_now=None,
                  explanation='', limitations=[])
    def incomplete(code, message):
        result['limitations'].append(dict(code=code, message=message))
        result['explanation'] = message
        return result
    if violation is None or boundary is None:
        return incomplete('MSL_POLICY_UNCONFIRMED', 'Supply an approved violation and availability-boundary policy.')
    ordered = sorted(timeline)
    if initial_condition == 'UNKNOWN' or any(state == 'UNKNOWN' for _, state in ordered):
        return incomplete('MSL_UNCONFIGURED', 'Effective MSL is unknown within the assessment interval.')
    allowed = {'BELOW_MSL', 'AT_MSL', 'ABOVE_MSL'}
    if initial_condition not in allowed or any(state not in allowed for _, state in ordered):
        raise ValueError('Unknown MSL condition')
    violates = lambda state: state == 'BELOW_MSL' or (state == 'AT_MSL' and violation == 'AT_OR_BELOW_MSL')
    current = next((state for at, state in reversed(ordered) if at <= evaluated_at), initial_condition)
    already = violates(current)
    result['already_breached'] = already
    crossing = evaluated_at if already else next((at for at, state in ordered if at > evaluated_at and violates(state)), None)
    result['expected_msl_crossing_at'] = crossing
    result['crossing_time_kind'] = ('AT_OR_BEFORE_EVALUATION' if already else 'EXACT_EVENT') if crossing else None
    if already:
        result.update(status='DETERMINED', reorder_required=True,
                      explanation='Stock violates the supplied MSL policy at evaluation. Initiate action now; an order cannot prevent an existing breach. No retrospective safe order time is claimed.')
        return result
    if days is None:
        return incomplete('LEAD_TIME_UNCONFIRMED', 'An approved initiation-to-usable duration is required; an observed interval is not a reusable duration.')
    if working_days and calendar is None:
        return incomplete('CALENDAR_UNCONFIRMED', 'Working-day lead time requires an approved calendar and counting convention.')
    try:
        arrival = shift(evaluated_at, days, 1, calendar)
        result['earliest_usable_at_if_ordered_now'] = arrival
        if crossing is None:
            if cutoff <= arrival:
                return incomplete('INSUFFICIENT_HORIZON', 'No breach is observed, but the exclusive projection horizon does not cover usable availability for an order initiated now.')
            result.update(status='DETERMINED', reorder_required=False,
                          explanation='No policy violation occurs within the verified projection horizon, which covers the supplied lead time. This is not a guarantee beyond that horizon.')
            return result
        latest = shift(crossing, days, -1, calendar)
        # Rolling a nonworking crossing back gives availability strictly before it.
        arrival_at_latest = shift(latest, days, 1, calendar)
        inclusive = boundary == 'AT_CROSSING_ALLOWED' or arrival_at_latest < crossing
        result.update(status='DETERMINED', reorder_required=evaluated_at >= latest,
                      latest_safe_order_at=latest, latest_safe_order_inclusive=inclusive,
                      explanation='The first future policy violation determines the order deadline. Initiate by the returned point when inclusive, otherwise strictly before it. A reached or passed deadline requires action; no purchase quantity is calculated.')
        return result
    except TimingUnavailable as error:
        return incomplete('CALENDAR_COVERAGE_UNAVAILABLE', str(error))
