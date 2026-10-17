"""User purchase proposals, separate from calculated and approved quantities."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PurchasePlanDraft(Base):
    __tablename__ = 'purchase_plan_drafts'
    __table_args__ = (
        UniqueConstraint('planning_version_id', 'consumable_id', name='uq_purchase_plan_draft_version_material'),
        CheckConstraint('requested_qty IS NULL OR requested_qty >= 0', name='nonnegative_requested_qty'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('planning_versions.id', ondelete='RESTRICT'), nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('consumables.id', ondelete='RESTRICT'), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('units.id', ondelete='RESTRICT'), nullable=False)
    requested_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
