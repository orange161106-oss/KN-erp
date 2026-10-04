"""ORM model for M4.4 — Inventory & MSL Alerts.

Alert Types:
    BELOW_MSL           — Usable stock is below Minimum Stock Level floor.
    LOW_STOCK           — Usable stock is approaching MSL warning threshold.
    REORDER_REQUIRED    — Reorder trigger point has been reached (M4.3 assessment).
    PO_DELAY            — Pending PO delivery is overdue.

Severities:
    CRITICAL, WARNING, INFO

Statuses:
    ACTIVE              — Alert condition currently exists.
    ACKNOWLEDGED        — User has reviewed and acknowledged the alert.
    RESOLVED            — Stock returned above threshold or issue resolved.
"""

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


class InventoryAlert(Base):
    __tablename__ = "inventory_alerts"
    __table_args__ = (
        Index("ix_inv_alerts_consumable", "consumable_id"),
        Index("ix_inv_alerts_status", "status"),
        Index("ix_inv_alerts_severity", "severity"),
        Index("ix_inv_alerts_type_status", "alert_type", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    consumable_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    current_stock: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    threshold_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    uom: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)

    acknowledged_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    consumable: Mapped["Consumable"] = relationship("Consumable")  # noqa: F821
    acknowledged_by_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[acknowledged_by]
    )
