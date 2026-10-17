from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.grn import GRN, GRNItem
from app.models.inventory_masters import Consumable, Supplier, Unit
from app.models.prd import PlanningVersion
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseDemandEvidence, PurchaseOrder, PurchaseOrderItem


def material_options(session: Session, q: str | None, limit: int):
    query = select(Consumable.id, Consumable.code, Consumable.name, Unit.code).join(Unit, Unit.id == Consumable.unit_id)
    if q:
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(Consumable.code.ilike(pattern, escape='\\') | Consumable.name.ilike(pattern, escape='\\'))
    return session.execute(query.order_by(Consumable.code, Consumable.id).limit(limit)).all()


def supplier_options(session: Session, q: str | None, limit: int):
    query = select(Supplier.id, Supplier.code, Supplier.name)
    if q:
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(Supplier.code.ilike(pattern, escape='\\') | Supplier.name.ilike(pattern, escape='\\'))
    return session.execute(query.order_by(Supplier.code, Supplier.id).limit(limit)).all()


def version_options(session: Session, q: str | None, limit: int):
    query = select(PlanningVersion.id, PlanningVersion.planning_period, PlanningVersion.revision_label, PlanningVersion.status)
    if q:
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(PlanningVersion.planning_period.ilike(pattern, escape='\\') |
                            PlanningVersion.revision_label.ilike(pattern, escape='\\') |
                            PlanningVersion.status.ilike(pattern, escape='\\'))
    return session.execute(query.order_by(PlanningVersion.created_at.desc(), PlanningVersion.id).limit(limit)).all()


def purchase_flow(session: Session, *, supplier_id=None, consumable_id=None, planning_version_id=None,
                  approval_status=None, po_status=None, po_date_from=None, po_date_until=None,
                  submitted_from=None, submitted_until=None, pending_only=False,
                  limit=25, offset=0):
    orders_query = select(
        PurchaseOrderItem.approval_id.label('approval_id'),
        func.sum(case((PurchaseOrder.status == 'DRAFT', PurchaseOrderItem.ordered_quantity), else_=0)).label('draft_qty'),
        func.sum(case((PurchaseOrder.status == 'ISSUED', PurchaseOrderItem.ordered_quantity), else_=0)).label('issued_qty'),
        func.sum(case((PurchaseOrder.status == 'CANCELLED', PurchaseOrderItem.ordered_quantity), else_=0)).label('cancelled_qty'),
    ).join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
    if po_status:
        orders_query = orders_query.where(PurchaseOrder.status == po_status)
    if po_date_from:
        orders_query = orders_query.where(PurchaseOrder.po_date >= po_date_from)
    if po_date_until:
        orders_query = orders_query.where(PurchaseOrder.po_date < po_date_until)
    orders = orders_query.group_by(PurchaseOrderItem.approval_id).subquery()
    receipts = select(
        PurchaseOrderItem.approval_id.label('approval_id'),
        func.sum(GRNItem.received_quantity).label('received_qty'),
        func.sum(GRNItem.accepted_quantity).label('accepted_qty'),
        func.sum(GRNItem.rejected_quantity).label('rejected_qty'),
    ).join(GRNItem, GRNItem.purchase_order_item_id == PurchaseOrderItem.id).join(
        PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
    if po_status:
        receipts = receipts.where(PurchaseOrder.status == po_status)
    if po_date_from:
        receipts = receipts.where(PurchaseOrder.po_date >= po_date_from)
    if po_date_until:
        receipts = receipts.where(PurchaseOrder.po_date < po_date_until)
    receipts = receipts.group_by(PurchaseOrderItem.approval_id).subquery()

    query = select(PurchaseApproval, PurchaseDemandEvidence, Consumable, Unit, Supplier,
                   orders.c.draft_qty, orders.c.issued_qty, orders.c.cancelled_qty, receipts.c.received_qty,
                   receipts.c.accepted_qty, receipts.c.rejected_qty)
    query = query.join(Consumable, Consumable.id == PurchaseApproval.consumable_id)
    query = query.join(Unit, Unit.id == Consumable.unit_id)
    query = query.join(Supplier, Supplier.id == PurchaseApproval.supplier_id)
    query = query.outerjoin(PurchaseDemandEvidence, PurchaseDemandEvidence.approval_id == PurchaseApproval.id)
    query = query.outerjoin(orders, orders.c.approval_id == PurchaseApproval.id)
    query = query.outerjoin(receipts, receipts.c.approval_id == PurchaseApproval.id)
    if supplier_id:
        query = query.where(PurchaseApproval.supplier_id == supplier_id)
    if consumable_id:
        query = query.where(PurchaseApproval.consumable_id == consumable_id)
    if planning_version_id:
        query = query.where(PurchaseApproval.planning_version_id == planning_version_id)
    if approval_status:
        query = query.where(PurchaseApproval.status == approval_status)
    if submitted_from:
        query = query.where(PurchaseApproval.created_at >= submitted_from)
    if submitted_until:
        query = query.where(PurchaseApproval.created_at < submitted_until)
    if po_status or po_date_from or po_date_until:
        query = query.where(orders.c.approval_id.is_not(None))
    if pending_only:
        query = query.where(func.coalesce(orders.c.issued_qty, 0) > func.coalesce(receipts.c.accepted_qty, 0))
    count = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = session.execute(query.order_by(Supplier.code, Consumable.code, PurchaseApproval.created_at.desc(), PurchaseApproval.id)
                           .limit(limit).offset(offset)).all()
    return rows, count


def grn_report(session: Session, *, supplier_id=None, consumable_id=None, purchase_order_id=None,
               event_from=None, event_until=None, limit=25, offset=0):
    query = select(GRN, GRNItem, PurchaseOrder, Supplier, PurchaseOrderItem)
    query = query.join(GRNItem, GRNItem.grn_id == GRN.id)
    query = query.join(PurchaseOrder, PurchaseOrder.id == GRN.purchase_order_id)
    query = query.join(Supplier, Supplier.id == GRN.supplier_id)
    query = query.join(PurchaseOrderItem, PurchaseOrderItem.id == GRNItem.purchase_order_item_id)
    if supplier_id:
        query = query.where(GRN.supplier_id == supplier_id)
    if consumable_id:
        query = query.where(GRNItem.consumable_id == consumable_id)
    if purchase_order_id:
        query = query.where(GRN.purchase_order_id == purchase_order_id)
    if event_from:
        query = query.where(GRN.event_at >= event_from)
    if event_until:
        query = query.where(GRN.event_at < event_until)
    count = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = session.execute(query.order_by(GRN.event_at.desc(), GRN.id, GRNItem.source_line_id).limit(limit).offset(offset)).all()
    return rows, count
