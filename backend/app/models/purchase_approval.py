"""ORM model for M5.2 — Purchase Recommendation Review & Approval Queue."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PurchaseApproval(Base):
    __tablename__ = "purchase_approvals"
    __table_args__ = (
        Index("ix_purch_appr_consumable", "consumable_id"),
        Index("ix_purch_appr_supplier", "supplier_id"),
        Index("ix_purch_appr_status", "status"),
        Index("ix_purch_appr_version", "planning_version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    consumable_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    planning_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="SET NULL"), nullable=True
    )
    rule_version: Mapped[str] = mapped_column(String(16), default="M5.1_V1", nullable=False)

    raw_calculated_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    system_recommended_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    approved_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    uom: Mapped[str] = mapped_column(String(16), nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    requested_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    consumable: Mapped["Consumable"] = relationship("Consumable")  # noqa: F821
    supplier: Mapped["Supplier"] = relationship("Supplier")  # noqa: F821
    requested_by_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[requested_by]
    )
    reviewed_by_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[reviewed_by]
    )
