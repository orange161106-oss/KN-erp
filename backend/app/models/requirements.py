from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CalculatedRequirement(Base):
    __tablename__ = "calculated_requirements"
    __table_args__ = (
        UniqueConstraint(
            "prd_order_item_id",
            "process_id",
            "consumable_id",
            name="uq_calculated_req_item_process_consumable",
        ),
        Index("ix_calc_req_version", "planning_version_id"),
        Index("ix_calc_req_version_plant", "planning_version_id", "plant_id"),
        Index("ix_calc_req_version_consumable", "planning_version_id", "consumable_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=False
    )
    prd_order_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prd_order_items.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    plant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False
    )
    process_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("processes.id", ondelete="RESTRICT"), nullable=False
    )
    consumable_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False
    )
    rule_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumption_norms.id", ondelete="RESTRICT"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    source_production_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    raw_requirement: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    rounding_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    rounding_precision: Mapped[int] = mapped_column(Integer, nullable=False)
    calculated_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    unit_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    uom: Mapped[str] = mapped_column(String(16), nullable=False)

    calculation_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    explanation_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    planning_version: Mapped["PlanningVersion"] = relationship("PlanningVersion")  # noqa: F821
    prd_order_item: Mapped["PRDOrderItem"] = relationship("PRDOrderItem")  # noqa: F821
    product: Mapped["Product"] = relationship("Product")  # noqa: F821
    plant: Mapped["Plant"] = relationship("Plant")  # noqa: F821
    process: Mapped["Process"] = relationship("Process")  # noqa: F821
    consumable: Mapped["Consumable"] = relationship("Consumable")  # noqa: F821
    rule: Mapped["ConsumptionNorm"] = relationship("ConsumptionNorm")  # noqa: F821
    unit: Mapped["Unit"] = relationship("Unit")  # noqa: F821


class RequirementCalculationError(Base):
    __tablename__ = "requirement_calculation_errors"
    __table_args__ = (
        Index("ix_calc_err_version", "planning_version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=False
    )
    prd_order_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prd_order_items.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    plant_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("plants.id", ondelete="SET NULL"), nullable=True
    )
    consumable_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    context_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    planning_version: Mapped["PlanningVersion"] = relationship("PlanningVersion")  # noqa: F821
    prd_order_item: Mapped["PRDOrderItem"] = relationship("PRDOrderItem")  # noqa: F821
    product: Mapped["Product"] = relationship("Product")  # noqa: F821
    plant: Mapped[Optional["Plant"]] = relationship("Plant")  # noqa: F821
    consumable: Mapped[Optional["Consumable"]] = relationship("Consumable")  # noqa: F821

