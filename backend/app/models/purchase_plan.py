"""ORM models for Monthly Purchase Planning (Normal View & MD View)."""

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


class PurchasePlan(Base):
    __tablename__ = "purchase_plans"
    __table_args__ = (
        UniqueConstraint("planning_period", name="uq_purchase_plan_period"),
        Index("ix_purchase_plan_period", "planning_period"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_period: Mapped[str] = mapped_column(String(7), nullable=False)  # 'YYYY-MM', e.g. '2026-10'
    planning_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="SET NULL"), nullable=True
    )
    revision_label: Mapped[str] = mapped_column(String(16), default="R1", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)  # DRAFT, CALCULATED, SUBMITTED, APPROVED

    msl_days_gas: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("2.0"), nullable=False)
    msl_days_general: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("10.0"), nullable=False)
    month_days: Mapped[int] = mapped_column(Integer, default=31, nullable=False)
    working_days: Mapped[int] = mapped_column(Integer, default=27, nullable=False)

    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    modified_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])  # noqa: F821
    modifier: Mapped[Optional["User"]] = relationship("User", foreign_keys=[modified_by])  # noqa: F821
    planning_version: Mapped[Optional["PlanningVersion"]] = relationship("PlanningVersion")  # noqa: F821

    items: Mapped[list["PurchasePlanItem"]] = relationship(
        "PurchasePlanItem", back_populates="plan", cascade="all, delete-orphan", order_by="PurchasePlanItem.s_no"
    )


class PurchasePlanItem(Base):
    __tablename__ = "purchase_plan_items"
    __table_args__ = (
        Index("ix_purchase_plan_item_plan", "plan_id"),
        Index("ix_purchase_plan_item_code", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_plans.id", ondelete="CASCADE"), nullable=False
    )

    # Core identification
    s_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    req_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    type_of_material: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Unit & outputs
    unit: Mapped[str] = mapped_column(String(32), default="PCS", nullable=False)
    purchasing_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    output_per_unit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Stock & Commercial parameters
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    moq: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    min_stock_level: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    max_stock_level: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Previous Month Stock (O/s, Receipt, Issues, C/s, Prd. Qty)
    prev_opening_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_opening_val: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_receipt_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_issue_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_closing_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_closing_val: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    prev_prd_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Selected Month Plan (R1)
    sch_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    req_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    order_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    order_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    receipt_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    receipt_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Revision 2 (R2)
    sch_qty_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    req_qty_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    order_qty_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    order_value_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    receipt_qty_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    receipt_val_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Actual Purchase
    pur_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    pur_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    bal_pur_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    bal_pur_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Supplier / Usage attributes (MD View)
    supplier_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    part_no_saleable: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    saleable_part_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    used_part_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    process_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    thickness_gsm: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    no_of_process_per_part: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Plant-wise allocations JSON (p1, p2, p3, p4, p5, tool_room, quality, pmd, npd, hrd, accounts, admin, sales, req_by_users, total_value)
    plant_allocations: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)

    # Consumption and stock analysis JSON
    consumption_analysis: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)

    # Audit & User overrides
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    plan: Mapped["PurchasePlan"] = relationship("PurchasePlan", back_populates="items")
