from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class PlanningVersion(Base):
    __tablename__ = "planning_versions"
    __table_args__ = (
        UniqueConstraint("planning_period", "version_number", name="uq_planning_period_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_period: Mapped[str] = mapped_column(String(7), index=True, nullable=False)  # e.g., '2026-10'
    version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision_label: Mapped[str] = mapped_column(String(16), default="R0", nullable=False)  # e.g., 'R0', 'R1'
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)  # DRAFT, VALIDATED, LOCKED, CALCULATED, RELEASED_TO_PLANTS, SUPERSEDED
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    planning_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    planning_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    calculated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    items: Mapped[list["PRDOrderItem"]] = relationship(back_populates="planning_version", cascade="all, delete-orphan")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("planning_versions.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="STAGING", index=True, nullable=False)  # STAGING, VALIDATED, FAILED, PROMOTED
    staged_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    uploaded_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    errors: Mapped[list["ImportError"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class ImportError(Base):
    __tablename__ = "import_errors"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("import_batches.id", ondelete="CASCADE"), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    batch: Mapped["ImportBatch"] = relationship(back_populates="errors")


class PRDOrderHeader(Base):
    __tablename__ = "prd_order_headers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=False)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    planning_period: Mapped[str] = mapped_column(String(7), nullable=False)
    total_planned_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    total_line_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items: Mapped[list["PRDOrderItem"]] = relationship(back_populates="header", cascade="all, delete-orphan")


class PRDOrderItem(Base):
    __tablename__ = "prd_order_items"
    __table_args__ = (
        CheckConstraint("planned_quantity > 0", name="ck_planned_quantity_positive"),
        UniqueConstraint("planning_version_id", "product_id", "plant_code", "target_period", name="uq_prd_item_version_product_plant_period"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    header_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("prd_order_headers.id", ondelete="CASCADE"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    uom: Mapped[str] = mapped_column(String(16), default="PCS", nullable=False)
    target_period: Mapped[str] = mapped_column(String(7), nullable=False)
    customer_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    planning_version: Mapped["PlanningVersion"] = relationship(back_populates="items")
    header: Mapped["PRDOrderHeader"] = relationship(back_populates="items")


class PRDRecord(Base):
    __tablename__ = "prd_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    row_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plant: Mapped[str] = mapped_column(String(64), nullable=False)
    customer: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    product_code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    uom: Mapped[str] = mapped_column(String(32), default="Nos", nullable=False)
    target_period: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    planning_version: Mapped[str] = mapped_column(String(32), default="V1", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="SAVED", nullable=False)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
