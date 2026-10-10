from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class MonthlyRequirementRecord(Base):
    __tablename__ = "monthly_requirement_records"
    __table_args__ = (
        Index("ix_monthly_req_period", "planning_period"),
        Index("ix_monthly_req_consumable", "consumable_code"),
        Index("ix_monthly_req_part", "part_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    planning_period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    planning_month: Mapped[int] = mapped_column(Integer, nullable=False)
    planning_year: Mapped[int] = mapped_column(Integer, nullable=False)
    row_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 1. Component identifiers
    part_name: Mapped[str] = mapped_column(String(255), nullable=False)
    part_number: Mapped[str] = mapped_column(String(128), nullable=False)

    # 2. Consumable attributes & process specs
    consumable_code: Mapped[str] = mapped_column(String(64), nullable=False)
    consumable_name: Mapped[str] = mapped_column(String(255), nullable=False)
    process_name: Mapped[str] = mapped_column(String(128), nullable=False)
    part_thickness: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    process_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # 3. Monthly Quantities
    production_order_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    scheduled_consumable_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)

    # 4. Inventory, Unit & Status
    unit: Mapped[str] = mapped_column(String(32), default="NOS", nullable=False)
    plant: Mapped[str] = mapped_column(String(64), default="Plant 1", nullable=False)
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    shortage_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    po_pending_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    msl: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="DRAFT", nullable=False)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 5. Audit
    created_by: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    planning_version: Mapped[Optional["PlanningVersion"]] = relationship("PlanningVersion")  # noqa: F821


