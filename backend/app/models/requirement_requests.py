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
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RequirementRequestBatch(Base):
    """Batch for Plant and Department monthly consumable request imports."""

    __tablename__ = "requirement_request_batches"
    __table_args__ = (
        Index("ix_req_batch_period", "planning_year", "planning_month"),
        Index("ix_req_batch_source", "planning_year", "planning_month", "source_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_month: Mapped[int] = mapped_column(Integer, nullable=False)
    planning_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'PLANT' or 'DEPARTMENT'
    source_code: Mapped[str] = mapped_column(String(32), nullable=False)  # 'P1'..'P5', 'TOOL_ROOM', 'PMD', 'SALES', 'NPD', 'HRD', 'QAD'
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")  # ACTIVE, SUPERSEDED, DELETED

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    requests: Mapped[list["RequirementRequest"]] = relationship(
        "RequirementRequest", back_populates="batch", cascade="all, delete-orphan"
    )


class RequirementRequest(Base):
    """Line item for Plant and Department monthly consumable demand."""

    __tablename__ = "requirement_requests"
    __table_args__ = (
        UniqueConstraint(
            "planning_year",
            "planning_month",
            "source_code",
            "consumable_id",
            "import_batch_id",
            name="uq_req_requests_period_source_consumable_batch",
        ),
        Index("ix_req_requests_period_source", "planning_year", "planning_month", "source_code", "status"),
        Index("ix_req_requests_consumable", "consumable_id"),
        Index("ix_req_requests_batch", "import_batch_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_month: Mapped[int] = mapped_column(Integer, nullable=False)
    planning_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'PLANT' or 'DEPARTMENT'
    source_code: Mapped[str] = mapped_column(String(32), nullable=False)  # 'P1'..'P5', 'TOOL_ROOM', 'PMD', 'SALES', 'NPD', 'HRD', 'QAD'

    consumable_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)  # Unit as submitted in sheet

    import_batch_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("requirement_request_batches.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")

    created_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    batch: Mapped["RequirementRequestBatch"] = relationship("RequirementRequestBatch", back_populates="requests")
    consumable: Mapped["Consumable"] = relationship("Consumable")  # noqa: F821

