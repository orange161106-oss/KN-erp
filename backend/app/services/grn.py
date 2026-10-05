"""One transaction imports ERP evidence, PO fulfilment and stock source records."""
from functools import wraps
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.purchase_engine.orders import pending_quantity
from app.models.grn import GRN, GRNItem
from app.models.inventory import StockSnapshot, StockTransaction
from app.repositories import grn as repository, purchase_order as orders
from app.schemas.grn import GRNResponse, ReceiptLineResponse
from app.services import inventory
from app.services.projection import digest
from app.services.purchase_order import audit


def transaction(function):
    @wraps(function)
    def wrapped(session, *args, **kwargs):
        try:
            return function(session, *args, **kwargs)
        except IntegrityError:
            session.rollback()
            raise ApplicationError('GRN_SOURCE_CONFLICT', 'Source receipt, stock event or snapshot conflicts. Retry unchanged only for a concurrent import.', 409) from None
        except SQLAlchemyError as error:
            session.rollback()
            if getattr(getattr(error, 'orig', None), 'sqlstate', None) in ('40001', '40P01'):
                raise ApplicationError('GRN_RETRY_REQUIRED', 'A concurrent receipt changed this order. Retry the unchanged export.', 409) from None
            raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None
        except Exception:
            session.rollback()
            raise
    return wrapped


def response(session, row, replayed=False):
    order = orders.order(session, row.purchase_order_id)
    po_items = {item.id: item for item in orders.items(session, order.id)}
    lines = []
    for line in repository.items(session, row.id):
        material = po_items[line.purchase_order_item_id].material_snapshot
        values = {field: getattr(line, field) for field in (
            'id', 'source_line_id', 'purchase_order_item_id', 'consumable_id', 'unit_id',
            'received_quantity', 'accepted_quantity', 'rejected_quantity', 'stock_transaction_id', 'stock_snapshot_id')}
        lines.append(ReceiptLineResponse(**values, consumable_code=material['code'],
                     consumable_name=material['name'], unit_code=material['unit_code']))
    return GRNResponse(**{field: getattr(row, field) for field in (
        'id', 'source_grn_id', 'purchase_order_id', 'supplier_id', 'stock_batch_id', 'event_at',
        'source_actor', 'imported_by', 'imported_at', 'reason')},
        po_number=order.po_number, supplier_name=order.supplier_snapshot['name'], items=lines, replayed=replayed)


@transaction
def import_grn(session, data, actor, *, enabled):
    if not enabled:
        raise ApplicationError('INVENTORY_IMPORT_DISABLED', 'Source import is disabled until the ERP mapping is verified.', 409)
    normalized = data.model_dump(mode='json')
    normalized['items'].sort(key=lambda row: row['source_line_id'])
    normalized['stock']['movements'].sort(key=lambda row: row['source_event_id'])
    normalized['stock']['snapshots'].sort(key=lambda row: row['source_snapshot_id'])
    payload_hash = digest(normalized)
    # Lock the parent before reading totals. Every receipt for this PO uses this
    # lock; stock stage then locks materials in UUID order. SERIALIZABLE also
    # protects against stale snapshots after waiting for the lock.
    order = orders.order(session, data.purchase_order_id, lock=True)
    if order is None:
        raise ApplicationError('PO_NOT_FOUND', 'Purchase order does not exist.', 404)
    previous = repository.by_source(session, data.source_grn_id)
    if previous:
        if previous.payload_hash != payload_hash:
            raise ApplicationError('GRN_KEY_CONFLICT', 'This source GRN already has different content. Imported history cannot be replaced.', 409)
        return response(session, previous, True)
    if order.status != 'ISSUED':
        raise ApplicationError('GRN_PO_STATE', 'Only issued purchase orders can receive imported GRNs.', 409)
    if order.supplier_id != data.supplier_id:
        raise ApplicationError('GRN_SUPPLIER_MISMATCH', 'Source supplier must match the purchase order.', 409)
    if data.event_at.date() < order.po_date:
        raise ApplicationError('GRN_EVENT_TIME', 'Receipt cannot precede the purchase order date.', 422)
    lines = {row.id: row for row in orders.items(session, order.id)}
    for line in data.items:
        item = lines.get(line.purchase_order_item_id)
        if item is None or item.consumable_id != line.consumable_id or item.unit_id != line.unit_id:
            raise ApplicationError('GRN_ITEM_MISMATCH', 'Receipt item, material and stock unit must match this PO.', 409)
        _, accepted, _ = repository.totals(session, item.id)
        # Conservative hold: an import exceeding outstanding physical quantity
        # requires an approved over-receipt policy, even if some is rejected.
        if line.received_quantity > pending_quantity(item.ordered_quantity, Decimal('0'), accepted):
            raise ApplicationError('GRN_OVER_RECEIPT_TBD', 'Receipt exceeds pending quantity. Over-receipt policy requires KNL confirmation; nothing was imported.', 409)
    stock = inventory.stage_source(session, data.stock, actor, enabled=enabled)
    row = GRN(source_grn_id=data.source_grn_id, payload_hash=payload_hash, purchase_order_id=order.id,
              supplier_id=data.supplier_id, stock_batch_id=stock.id, event_at=data.event_at,
              source_actor=data.source_actor, imported_by=actor, reason=data.reason)
    session.add(row)
    session.flush()
    snapshots = {source.consumable_id: session.scalar(select(StockSnapshot).where(
        StockSnapshot.source_snapshot_id == source.source_snapshot_id)) for source in data.stock.snapshots}
    for line in data.items:
        movement = session.scalar(select(StockTransaction).where(StockTransaction.source_event_id == line.source_event_id)) if line.source_event_id else None
        session.add(GRNItem(grn_id=row.id, **line.model_dump(exclude={'source_event_id'}),
                            stock_transaction_id=movement.id if movement else None,
                            stock_snapshot_id=snapshots[line.consumable_id].id))
    session.flush()
    audit(session, actor, row.id, 'IMPORT_GRN', data.reason,
          {'source_grn_id': row.source_grn_id, 'purchase_order_id': str(order.id), 'stock_batch_id': str(stock.id),
           'payload_hash': payload_hash, 'source': 'EXISTING_ERP'}, entity='grns')
    audit(session, actor, order.id, 'IMPORT_PO_RECEIPT', data.reason,
          {'grn_id': str(row.id), 'source_grn_id': row.source_grn_id, 'fulfilment_basis': 'ACCEPTED_USABLE_ONLY'})
    session.flush()
    result = response(session, row)
    session.commit()
    return result


@transaction
def get(session, identity):
    row = session.get(GRN, identity)
    if row is None:
        raise ApplicationError('GRN_NOT_FOUND', 'Imported GRN does not exist.', 404)
    return response(session, row)


@transaction
def listing(session, limit, offset, purchase_order_id=None):
    query = select(GRN)
    if purchase_order_id:
        query = query.where(GRN.purchase_order_id == purchase_order_id)
    rows = session.scalars(query.order_by(GRN.event_at.desc(), GRN.id).limit(limit).offset(offset)).all()
    return [response(session, row) for row in rows]
