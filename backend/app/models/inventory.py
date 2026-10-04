from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockImportBatch(Base):
    __tablename__ = "stock_import_batches"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    export_id: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    import_reason: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    movement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False)


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    __table_args__ = (
        CheckConstraint("movement IN ('RECEIPT', 'ISSUE', 'RETURN')", name="movement"),
        CheckConstraint("source_quantity > 0 AND quantity > 0 AND conversion_factor > 0", name="positive_quantity"),
        CheckConstraint("quantity = source_quantity * conversion_factor", name="exact_conversion"),
        CheckConstraint("signed_quantity = CASE WHEN movement = 'ISSUE' THEN -quantity ELSE quantity END", name="signed_quantity"),
        CheckConstraint("(source_unit_id = unit_id AND conversion_factor = 1) OR (source_unit_id <> unit_id AND conversion_reference IS NOT NULL AND length(conversion_reference) > 0)", name="conversion_reference"),
        Index("ix_stock_transactions_material_time", "consumable_id", "event_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_event_id: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("stock_import_batches.id", ondelete="RESTRICT"), nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    source_unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    source_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    conversion_reference: Mapped[str | None] = mapped_column(String(192))
    movement: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    signed_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_actor: Mapped[str] = mapped_column(String(128), nullable=False)


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"
    __table_args__ = (
        UniqueConstraint("consumable_id", "as_of"),
        CheckConstraint("usable_quantity >= 0", name="nonnegative_quantity"),
        CheckConstraint("nonusable_excluded AND reservations_excluded", name="usable_exclusions"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("stock_import_batches.id", ondelete="RESTRICT"), nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    usable_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nonusable_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reservations_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False)
