"""Read-only composition. All demand and incoming arithmetic belongs to M4.2."""
from decimal import Decimal, localcontext

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.inventory_engine.reorder import Calendar, TimingUnavailable, shift
from app.domain.purchase_engine.recommendation import Constraint, NAMES, calculate
from app.repositories import purchase_recommendation as repository
from app.schemas.purchase_recommendation import PurchaseReport, PurchaseRequest
from app.services import projection


def report(session, data: PurchaseRequest):
    try:
        return _report(session, data)
    except SQLAlchemyError:
        raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None


def _report(session, data):
    source = projection.report(session, data.consumable_id, data.planning_version_id,
                               data.receipt_at, data.source_set_id)
    material, unit, supplier, mapping = repository.context(session, data.consumable_id, data.supplier_id)
    if supplier is None or mapping is None:
        raise ApplicationError('SUPPLIER_MAPPING_MISSING', 'Select a supplier mapped to this consumable.', 409)
    if not all(row.is_active for row in (material, unit, supplier, mapping)):
        raise ApplicationError('PURCHASE_MASTER_INACTIVE', 'Consumable, stock unit, supplier and mapping must be active.', 409)
    if data.unit_id != source.unit_id:
        raise ApplicationError('UNIT_MISMATCH', 'Target and supplier constraints must use the consumable stock unit.', 409)
    if source.stock_as_of and data.initiated_at < source.stock_as_of:
        raise ApplicationError('INVALID_PURCHASE_INITIATION', 'Order initiation cannot precede the source stock snapshot.', 422)
    with localcontext() as ctx:
        ctx.prec = 80
        totals = sum((row.final_quantity for row in source.requirement_totals), Decimal('0')) if source.requirement_totals else None
        incoming = sum((row.receipts for row in source.timeline), Decimal('0')) if source.status == 'COMPLETE' else None
    common = dict(supplier_id=supplier.id, supplier_code=supplier.code, supplier_name=supplier.name,
                  final_requirement=totals, current_stock=source.opening_stock,
                  projected_stock_at_receipt=source.projected_stock,
                  confirmed_incoming_before_receipt=incoming, msl_at_receipt=source.projected_msl,
                  target_stock=data.target.quantity if data.target else None,
                  lead_time=data.lead_time, constraints=data.constraints, request=data, projection=source)
    def unavailable(code, message):
        return PurchaseReport(status='INCOMPLETE', explanation=message,
                              limitations=[{'code': code, 'message': message}], **common)
    if source.status != 'COMPLETE':
        return unavailable('PROJECTION_INCOMPLETE', 'Dated, reconciled and current projection evidence is required; inspect projection limitations.')
    if not data.evidence_from <= data.initiated_at <= data.receipt_at < data.evidence_until:
        return unavailable('PURCHASE_EVIDENCE_EXPIRED', 'Target and constraint evidence must cover initiation through usable receipt.')
    if source.projected_msl is None:
        return unavailable('MSL_UNCONFIRMED', 'The effective MSL is unknown; supply it rather than interpreting the target as MSL.')
    inputs = source.inputs
    # M4.2 cutoff excludes exact-time events. Do not turn that exclusion into an
    # undocumented ordering assumption at the proposed receipt itself.
    simultaneous = any(event.at == data.receipt_at and event.quantity for plan in inputs.demand or [] for event in plan.events or [])
    simultaneous |= any(row.available_at == data.receipt_at and row.status == 'CONFIRMED'
                        and row.scheduled_quantity > row.received_quantity + row.cancelled_quantity for row in inputs.incoming or [])
    simultaneous |= any(row.effective_at == data.receipt_at for row in inputs.msl_history)
    if simultaneous:
        return unavailable('RECEIPT_EVENT_ORDER_UNCONFIRMED', 'Demand, confirmed supply or an MSL change shares the receipt timestamp. Exact event order must be resolved at source.')
    lead = data.lead_time
    if lead is None:
        return unavailable('LEAD_TIME_UNCONFIRMED', 'Supply an initiation-to-usable lead time; no duration is inferred from an old receipt interval.')
    if lead.supplier_id != data.supplier_id or (inputs.lead_time and inputs.lead_time.supplier_id != data.supplier_id):
        return unavailable('LEAD_TIME_SUPPLIER_MISMATCH', 'Lead-time evidence must identify the selected supplier.')
    if not lead.effective_from <= data.initiated_at <= data.receipt_at < lead.effective_until:
        return unavailable('LEAD_TIME_EXPIRED', 'Lead-time validity must cover initiation through usable receipt.')
    if lead.basis == 'WORKING_DAYS' and lead.calendar is None:
        return unavailable('CALENDAR_UNCONFIRMED', 'Working-day lead time requires an explicit approved calendar.')
    calendar = Calendar(lead.calendar.first_date, lead.calendar.last_date, frozenset(lead.calendar.working_dates)) if lead.calendar else None
    try:
        expected = shift(data.initiated_at, lead.days, 1, calendar)
    except TimingUnavailable as error:
        return unavailable('CALENDAR_COVERAGE_UNAVAILABLE', str(error))
    if expected != data.receipt_at:
        return unavailable('RECEIPT_LEAD_TIME_MISMATCH', 'The supplied receipt timestamp does not equal usable availability from the stated initiation and lead time.')
    if data.constraints.other_constraints != 'CONFIRMED_NONE':
        return unavailable('ADDITIONAL_CONSTRAINTS_UNCONFIRMED', 'Confirm that no additional supplier restrictions apply; unsupported restrictions cannot be silently ignored.')
    constraints = {name: Constraint(getattr(data.constraints, name).state, getattr(data.constraints, name).value) for name in NAMES}
    result = calculate(target=data.target.quantity if data.target else None,
                       projected=source.projected_stock, constraints=constraints)
    if data.target and data.target.quantity < source.projected_msl:
        result['limitations'].append({'code': 'TARGET_BELOW_MSL', 'message': 'The supplied target is below the effective MSL. Review the target; this quantity calculation does not override it or establish MSL-policy compliance.'})
    return PurchaseReport(**result, **common)
