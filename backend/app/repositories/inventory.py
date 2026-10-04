from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models.inventory import StockImportBatch, StockSnapshot, StockTransaction
from app.models.inventory_masters import Consumable, Unit


def find_batch(session: Session, export_id: str):
    return session.scalar(select(StockImportBatch).where(StockImportBatch.export_id == export_id))


def lock_consumables(session: Session, ids: set[UUID]):
    return {row.id: row for row in session.scalars(
        select(Consumable).where(Consumable.id.in_(ids)).order_by(Consumable.id)
        .with_for_update().execution_options(populate_existing=True)
    )}


def has_stock_records(session: Session, consumable_id: UUID) -> bool:
    return (session.scalar(select(StockTransaction.id).where(StockTransaction.consumable_id == consumable_id).limit(1)) is not None
            or session.scalar(select(StockSnapshot.id).where(StockSnapshot.consumable_id == consumable_id).limit(1)) is not None)


def find_source_record(session: Session, model, key: str):
    field = model.source_event_id if model is StockTransaction else model.source_snapshot_id
    return session.scalar(select(model).where(field == key))


def balances(session: Session, *, limit: int, offset: int, q=None, is_active=None, consumable_id=None):
    latest = select(StockSnapshot.consumable_id, func.max(StockSnapshot.as_of).label("as_of")).group_by(StockSnapshot.consumable_id).subquery()
    query = select(Consumable, Unit.code, StockSnapshot, StockImportBatch).join(Unit, Unit.id == Consumable.unit_id)
    query = query.outerjoin(latest, latest.c.consumable_id == Consumable.id)
    query = query.outerjoin(StockSnapshot, (StockSnapshot.consumable_id == Consumable.id) & (StockSnapshot.as_of == latest.c.as_of))
    query = query.outerjoin(StockImportBatch, StockImportBatch.id == StockSnapshot.batch_id)
    if consumable_id is not None:
        query = query.where(Consumable.id == consumable_id)
    if is_active is not None:
        query = query.where(Consumable.is_active == is_active)
    if q:
        literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Consumable.code.ilike("%" + literal + "%", escape="\\") | Consumable.name.ilike("%" + literal + "%", escape="\\"))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return session.execute(query.order_by(Consumable.code, Consumable.id).offset(offset).limit(limit)).all(), total


def transactions(session: Session, *, limit: int, offset: int, consumable_id=None, movement=None, since=None, until=None):
    source_unit = aliased(Unit)
    query = select(StockTransaction, Consumable.code, Consumable.name, Unit.code, source_unit.code, StockImportBatch)
    query = query.join(Consumable, Consumable.id == StockTransaction.consumable_id).join(Unit, Unit.id == StockTransaction.unit_id)
    query = query.join(source_unit, source_unit.id == StockTransaction.source_unit_id).join(StockImportBatch, StockImportBatch.id == StockTransaction.batch_id)
    if consumable_id is not None:
        query = query.where(StockTransaction.consumable_id == consumable_id)
    if movement is not None:
        query = query.where(StockTransaction.movement == movement)
    if since is not None:
        query = query.where(StockTransaction.event_at >= since)
    if until is not None:
        query = query.where(StockTransaction.event_at <= until)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return session.execute(query.order_by(StockTransaction.event_at.desc(), StockTransaction.id).offset(offset).limit(limit)).all(), total
