"""Immutable receipts imported from the authoritative existing ERP."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GRN(Base):
    __tablename__ = 'grns'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_grn_id: Mapped[str] = mapped_column(String(192), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    purchase_order_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_orders.id', ondelete='RESTRICT'), index=True)
    supplier_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('suppliers.id', ondelete='RESTRICT'))
    stock_batch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('stock_import_batches.id', ondelete='RESTRICT'))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_actor: Mapped[str] = mapped_column(String(128))
    imported_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)


class GRNItem(Base):
    __tablename__ = 'grn_items'
    __table_args__ = (
        UniqueConstraint('grn_id', 'source_line_id'), UniqueConstraint('grn_id', 'purchase_order_item_id', name='uq_grn_items_grn_id_po_item'),
        CheckConstraint('received_quantity > 0 AND accepted_quantity >= 0 AND rejected_quantity >= 0', name='valid_quantities'),
        CheckConstraint('received_quantity = accepted_quantity + rejected_quantity', name='quantity_split'),
        CheckConstraint('(accepted_quantity = 0 AND stock_transaction_id IS NULL) OR (accepted_quantity > 0 AND stock_transaction_id IS NOT NULL)', name='accepted_stock_link'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    grn_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('grns.id', ondelete='RESTRICT'), index=True)
    source_line_id: Mapped[str] = mapped_column(String(192))
    purchase_order_item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_order_items.id', ondelete='RESTRICT'), index=True)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('consumables.id', ondelete='RESTRICT'))
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('units.id', ondelete='RESTRICT'))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    stock_transaction_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('stock_transactions.id', ondelete='RESTRICT'), unique=True)
    stock_snapshot_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('stock_snapshots.id', ondelete='RESTRICT'))
