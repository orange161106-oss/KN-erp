"""Compose a read-only assessment from the authoritative M4.2 report."""
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.inventory_engine.reorder import Calendar, assess
from app.repositories import projection as repository
from app.schemas.reorder import ReorderReport, ReorderRequest
from app.services import projection


def report(session, data: ReorderRequest):
    source = projection.report(session, data.consumable_id, data.planning_version_id,
                               data.cutoff, data.source_set_id)
    def unavailable(code, message):
        return ReorderReport(status='INCOMPLETE', explanation=message,
                             limitations=[{'code': code, 'message': message}], request=data, projection=source)
    if source.stock_as_of and data.evaluated_at < source.stock_as_of:
        raise ApplicationError('INVALID_REORDER_EVALUATION', 'Evaluation cannot precede the stock snapshot.', 422)
    if source.status != 'COMPLETE':
        return unavailable('PROJECTION_INCOMPLETE', 'The projection is incomplete or stale; inspect its source limitations before assessing reorder timing.')
    policy, lead = data.policy, data.lead_time
    if policy and not (policy.effective_from <= source.stock_as_of and policy.effective_until >= data.cutoff):
        return unavailable('POLICY_COVERAGE_UNAVAILABLE', 'The supplied policy must cover the whole projection interval; policy revisions are not inferred.')
    if lead:
        try:
            mapped = repository.supplier_mapping_exists(session, data.consumable_id, lead.supplier_id)
        except SQLAlchemyError:
            raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None
        if not mapped:
            raise ApplicationError('SUPPLIER_MAPPING_MISSING', 'The lead-time supplier must be mapped to this consumable.', 409)
        if source.inputs.lead_time and source.inputs.lead_time.supplier_id != lead.supplier_id:
            return unavailable('LEAD_TIME_SUPPLIER_MISMATCH', 'The duration supplier differs from the supplier identified by the selected projection evidence.')
    calendar = None
    if lead and lead.calendar:
        calendar = Calendar(lead.calendar.first_date, lead.calendar.last_date, frozenset(lead.calendar.working_dates))
    result = assess(baseline=source.stock_as_of, evaluated_at=data.evaluated_at, cutoff=data.cutoff,
                    initial_condition=source.current_msl_condition,
                    timeline=tuple((row.at, row.msl_condition) for row in source.timeline),
                    violation=policy.violation if policy else None,
                    boundary=policy.availability_boundary if policy else None,
                    days=lead.days if lead else None, calendar=calendar,
                    working_days=bool(lead and lead.basis == 'WORKING_DAYS'))
    if lead and not result['already_breached']:
        relevant = [data.evaluated_at, result['latest_safe_order_at'], result['earliest_usable_at_if_ordered_now'],
                    result['expected_msl_crossing_at']]
        if any(at and not lead.effective_from <= at < lead.effective_until for at in relevant):
            return unavailable('LEAD_TIME_VALIDITY_UNAVAILABLE', 'Lead-time evidence does not cover evaluation, initiation and usable-availability dates required by this assessment.')
    return ReorderReport(**result, request=data, projection=source)
