from datetime import date, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.domain.purchase_engine.orders import pending_quantity
from app.repositories import inventory_purchase_reports as repository
from app.schemas.inventory_purchase_reports import (
    GRNReportItem, GRNReportPage, PurchaseFlowItem, PurchaseFlowPage, ReportOption,
)
from app.schemas.purchase_recommendation import PurchaseReport
from app.services import inventory, projection, purchase_recommendation, reorder


def _database(function):
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError:
            raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None
    return wrapped


@_database
def stock(session: Session, **filters):
    return inventory.list_balances(session, **filters)


@_database
def materials(session: Session, q: str | None, limit: int):
    return [ReportOption(id=identity, label=code, detail=f'{name} · {unit}')
            for identity, code, name, unit in repository.material_options(session, q, limit)]


@_database
def suppliers(session: Session, q: str | None, limit: int):
    return [ReportOption(id=identity, label=code, detail=name)
            for identity, code, name in repository.supplier_options(session, q, limit)]


@_database
def planning_versions(session: Session, q: str | None, limit: int):
    return [ReportOption(id=identity, label=f'{period} · {revision}', detail=status)
            for identity, period, revision, status in repository.version_options(session, q, limit)]


@_database
def projection_report(session: Session, consumable_id, planning_version_id, cutoff, source_set_id=None):
    return projection.report(session, consumable_id, planning_version_id, cutoff, source_set_id)


@_database
def reorder_report(session: Session, data):
    return reorder.report(session, data)


@_database
def purchase_assessment(session: Session, data):
    return purchase_recommendation.report(session, data)


def _purchase_flow_item(row):
    approval, evidence, material, unit, supplier, draft, issued, cancelled, received, accepted, rejected = row
    report_status = 'NO_SAVED_EVIDENCE'
    recommended = None
    if evidence is not None:
        try:
            saved = PurchaseReport.model_validate(evidence.report)
            report_status = saved.status
            recommended = saved.recommended_quantity
        except ValidationError:
            report_status = 'INVALID_SAVED_EVIDENCE'
    draft_qty = draft if draft is not None else Decimal('0')
    issued_qty = issued if issued is not None else Decimal('0')
    cancelled_qty = cancelled if cancelled is not None else Decimal('0')
    received_qty = received if received is not None else Decimal('0')
    accepted_qty = accepted if accepted is not None else Decimal('0')
    rejected_qty = rejected if rejected is not None else Decimal('0')
    pending = pending_quantity(issued_qty, Decimal('0'), accepted_qty)
    return PurchaseFlowItem(
        approval_id=approval.id, evidence_id=evidence.id if evidence else None,
        submitted_at=evidence.created_at if evidence else None,
        supplier_id=supplier.id, supplier_code=supplier.code, supplier_name=supplier.name,
        consumable_id=material.id, consumable_code=material.code, consumable_name=material.name,
        unit_code=unit.code, planning_version_id=approval.planning_version_id,
        recommendation_status=report_status, recommended_quantity=recommended,
        approval_status=approval.status, reviewed_at=approval.reviewed_at,
        approved_quantity=approval.approved_qty, draft_allocated_quantity=draft_qty,
        issued_ordered_quantity=issued_qty, cancelled_order_quantity=cancelled_qty,
        received_quantity=received_qty,
        accepted_quantity=accepted_qty, rejected_quantity=rejected_qty, pending_quantity=pending,
        pending_basis='IMPORTED_ACCEPTED_GRNS' if issued_qty else 'NOT_ISSUED')


@_database
def purchase_flow(session: Session, *, supplier_id=None, consumable_id=None, planning_version_id=None,
                  approval_status=None, po_status=None, po_date_from: date | None = None,
                  po_date_until: date | None = None, submitted_from: datetime | None = None,
                  submitted_until: datetime | None = None,
                  pending_only=False, limit=25, offset=0):
    if submitted_from and submitted_until and submitted_from >= submitted_until:
        raise ApplicationError('INVALID_DATE_RANGE', 'Submitted-from must precede submitted-until; the upper bound is exclusive.', 422)
    if po_date_from and po_date_until and po_date_from >= po_date_until:
        raise ApplicationError('INVALID_DATE_RANGE', 'PO-date-from must precede PO-date-until; the upper bound is exclusive.', 422)
    rows, total = repository.purchase_flow(session, supplier_id=supplier_id, consumable_id=consumable_id,
        planning_version_id=planning_version_id, approval_status=approval_status, po_status=po_status,
        po_date_from=po_date_from, po_date_until=po_date_until,
        submitted_from=submitted_from, submitted_until=submitted_until, pending_only=pending_only,
        limit=limit, offset=offset)
    return PurchaseFlowPage(items=[_purchase_flow_item(row) for row in rows], total=total, limit=limit,
        offset=offset, pending_only=pending_only, submitted_from=submitted_from, submitted_until=submitted_until,
        po_status=po_status, po_date_from=po_date_from, po_date_until=po_date_until)


@_database
def grn_history(session: Session, *, supplier_id=None, consumable_id=None, purchase_order_id=None,
                event_from: datetime | None = None, event_until: datetime | None = None, limit=25, offset=0):
    if event_from and event_until and event_from >= event_until:
        raise ApplicationError('INVALID_DATE_RANGE', 'Event-from must precede event-until; the upper bound is exclusive.', 422)
    rows, total = repository.grn_report(session, supplier_id=supplier_id, consumable_id=consumable_id,
        purchase_order_id=purchase_order_id, event_from=event_from, event_until=event_until,
        limit=limit, offset=offset)
    items = []
    for grn, line, order, supplier, order_line in rows:
        items.append(GRNReportItem(grn_id=grn.id, source_grn_id=grn.source_grn_id,
            purchase_order_id=order.id, po_number=order.po_number, supplier_id=supplier.id,
            supplier_code=supplier.code, supplier_name=supplier.name, consumable_id=line.consumable_id,
            consumable_code=order_line.material_snapshot['code'], consumable_name=order_line.material_snapshot['name'],
            unit_id=line.unit_id, unit_code=order_line.material_snapshot['unit_code'], source_line_id=line.source_line_id,
            event_at=grn.event_at, imported_at=grn.imported_at, received_quantity=line.received_quantity,
            accepted_quantity=line.accepted_quantity, rejected_quantity=line.rejected_quantity,
            stock_transaction_id=line.stock_transaction_id, stock_snapshot_id=line.stock_snapshot_id))
    return GRNReportPage(items=items, total=total, limit=limit, offset=offset,
                         event_from=event_from, event_until=event_until)
