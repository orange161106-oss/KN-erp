from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StockStatementBatch(Base):
    """Monthly snapshot batch of KNL stock statement uploads."""

    __tablename__ = "stock_statement_batches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    statement_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    statement_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active, superseded

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    lines: Mapped[list["StockStatementLine"]] = relationship(
        "StockStatementLine",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="StockStatementLine.source_row",
    )
    uploader = relationship("User", foreign_keys=[uploaded_by])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class StockStatementLine(Base):
    """Detailed line in a monthly stock statement."""

    __tablename__ = "stock_statement_lines"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stock_statement_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consumable_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("consumables.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    item_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CONSUMABLE", server_default="CONSUMABLE", index=True
    )

    item_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cust_part_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    opening_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    opening_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    receipt_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    receipt_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    issue_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    issue_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    closing_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    closing_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 4), nullable=True
    )

    source_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_codes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    batch: Mapped["StockStatementBatch"] = relationship(
        "StockStatementBatch", back_populates="lines"
    )
    consumable = relationship("Consumable", foreign_keys=[consumable_id])


class StockParameterBatch(Base):
    """Batch upload for stock control parameters (MSL, Max, MOQ, Lead time)."""

    __tablename__ = "stock_parameter_batches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active, superseded

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    parameters: Mapped[list["StockParameter"]] = relationship(
        "StockParameter",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="StockParameter.source_row",
    )
    uploader = relationship("User", foreign_keys=[uploaded_by])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class StockParameter(Base):
    """Stock control parameter per consumable per month."""

    __tablename__ = "stock_parameters"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stock_parameter_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consumable_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("consumables.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    type_of_material: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    min_stock_level: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    max_stock_level: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    min_order_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    edited_after_import: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    source_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    batch: Mapped["StockParameterBatch"] = relationship(
        "StockParameterBatch", back_populates="parameters"
    )
    consumable = relationship("Consumable", foreign_keys=[consumable_id])
    updater = relationship("User", foreign_keys=[updated_by])

