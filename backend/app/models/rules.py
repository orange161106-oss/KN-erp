from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ConsumptionNorm(Base):
    __tablename__ = "consumption_norms"
    __table_args__ = (
        Index(
            "ix_consumption_norms_lookup",
            "consumable_id",
            "product_id",
            "process_id",
            "plant_id",
            "is_active",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=True, index=True)
    process_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("processes.id", ondelete="RESTRICT"), nullable=True, index=True)
    plant_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("plants.id", ondelete="RESTRICT"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    rounding_policy: Mapped[str] = mapped_column(String(32), default="NONE", nullable=False)
    rounding_precision: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, default=func.current_date(), nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    consumable: Mapped["Consumable"] = relationship("Consumable")
    product: Mapped[Optional["Product"]] = relationship("Product")
    process: Mapped[Optional["Process"]] = relationship("Process")
    plant: Mapped[Optional["Plant"]] = relationship("Plant")
    unit: Mapped["Unit"] = relationship("Unit")
