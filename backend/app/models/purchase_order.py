"""Purchase commitments and immutable recommendation evidence; no stock postings."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PurchaseDemandEvidence(Base):
    __tablename__ = 'purchase_demand_evidence'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    approval_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_approvals.id', ondelete='RESTRICT'), unique=True)
    submission_key: Mapped[str] = mapped_column(String(192), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    report: Mapped[dict] = mapped_column(JSON)
    submitted_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'
    __table_args__ = (CheckConstraint("status IN ('DRAFT','ISSUED','CANCELLED')", name='valid_status'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    po_number: Mapped[str] = mapped_column(String(64), unique=True)
    creation_key: Mapped[str] = mapped_column(String(192), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('suppliers.id', ondelete='RESTRICT'), index=True)
    supplier_snapshot: Mapped[dict] = mapped_column(JSON)
    po_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    issued_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrderItem(Base):
    __tablename__ = 'purchase_order_items'
    __table_args__ = (
        UniqueConstraint('purchase_order_id', 'approval_id'),
        CheckConstraint('ordered_quantity > 0', name='positive_order_quantity'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    purchase_order_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_orders.id', ondelete='RESTRICT'), index=True)
    approval_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_approvals.id', ondelete='RESTRICT'), index=True)
    evidence_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('purchase_demand_evidence.id', ondelete='RESTRICT'))
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('consumables.id', ondelete='RESTRICT'))
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('units.id', ondelete='RESTRICT'))
    planning_version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('planning_versions.id', ondelete='RESTRICT'))
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    expected_delivery: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_hash: Mapped[str] = mapped_column(String(64))
    approval_snapshot: Mapped[dict] = mapped_column(JSON)
    material_snapshot: Mapped[dict] = mapped_column(JSON)
    pricing: Mapped[dict | None] = mapped_column(JSON)
    line_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 8))
