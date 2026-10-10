from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable


def find(session: Session, model, entity_id: UUID, *, lock=False):
    query = select(model).where(model.id == entity_id)
    if lock:
        query = query.with_for_update()
    return session.scalar(query.execution_options(populate_existing=True))


def list_records(session: Session, model, *, limit: int, offset: int, q: str | None,
                 is_active: bool | None, supplier_id: UUID | None = None,
                 consumable_id: UUID | None = None):
    predicates = []
    if is_active is not None:
        predicates.append(model.is_active == is_active)
    if model is SupplierConsumable:
        if supplier_id:
            predicates.append(model.supplier_id == supplier_id)
        if consumable_id:
            predicates.append(model.consumable_id == consumable_id)
        if q:
            query_text = literal_search(q)
            supplier_matches = select(Supplier.id).where(or_(Supplier.code.ilike(query_text, escape="\\"), Supplier.name.ilike(query_text, escape="\\")))
            consumable_matches = select(Consumable.id).where(or_(Consumable.code.ilike(query_text, escape="\\"), Consumable.name.ilike(query_text, escape="\\")))
            predicates.append(or_(model.supplier_id.in_(supplier_matches), model.consumable_id.in_(consumable_matches)))
        ordering = (model.created_at, model.id)
    else:
        if q:
            query_text = literal_search(q)
            predicates.append(or_(model.code.ilike(query_text, escape="\\"), model.name.ilike(query_text, escape="\\")))
        ordering = (model.code, model.id)
    total = session.scalar(select(func.count()).select_from(model).where(*predicates))
    items = session.scalars(select(model).where(*predicates).order_by(*ordering).limit(limit).offset(offset)).all()
    return items, total


def literal_search(q: str) -> str:
    return "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def has_active_consumables(session: Session, unit_id: UUID) -> bool:
    return session.scalar(select(Consumable.id).where(Consumable.unit_id == unit_id, Consumable.is_active.is_(True)).limit(1)) is not None


def has_supplier_mapping(session: Session, consumable_id: UUID) -> bool:
    return session.scalar(select(SupplierConsumable.id).where(SupplierConsumable.consumable_id == consumable_id).limit(1)) is not None
