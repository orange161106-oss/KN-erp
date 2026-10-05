from decimal import Decimal

from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.prd import PlanningVersion
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseDemandEvidence, PurchaseOrder, PurchaseOrderItem


def approval(session, identity, lock=False):
    query = select(PurchaseApproval).where(PurchaseApproval.id == identity)
    return session.scalar(query.with_for_update() if lock else query)


def evidence(session, identity):
    return session.scalar(select(PurchaseDemandEvidence).where(PurchaseDemandEvidence.approval_id == identity))


def allocated(session, identity, exclude=None):
    query = select(func.coalesce(func.sum(PurchaseOrderItem.ordered_quantity), 0)).join(
        PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id).where(
        PurchaseOrderItem.approval_id == identity, PurchaseOrder.status != 'CANCELLED')
    if exclude:
        query = query.where(PurchaseOrder.id != exclude)
    return Decimal(session.scalar(query))


def masters(session, row):
    material = session.get(Consumable, row.consumable_id)
    return (material, session.get(Unit, material.unit_id) if material else None,
            session.get(Supplier, row.supplier_id),
            session.scalar(select(SupplierConsumable).where(SupplierConsumable.supplier_id == row.supplier_id,
                                                          SupplierConsumable.consumable_id == row.consumable_id)),
            session.get(PlanningVersion, row.planning_version_id) if row.planning_version_id else None)


def order(session, identity, lock=False):
    query = select(PurchaseOrder).where(PurchaseOrder.id == identity)
    return session.scalar(query.with_for_update() if lock else query)


def items(session, identity):
    return session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == identity).order_by(PurchaseOrderItem.id)).all()


def history(session, identity):
    return session.scalars(select(AuditLog).where(AuditLog.entity_type == 'purchase_orders', AuditLog.entity_id == identity)
                           .order_by(AuditLog.created_at, AuditLog.id)).all()
