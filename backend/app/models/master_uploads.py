"""Period-scoped upload snapshots; canonical master identities remain shared."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasterUploadBatch(Base):
    __tablename__ = "master_upload_batches"
    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="year_range"),
        CheckConstraint("category IN ('consumables','sales_parts','assemble')", name="category"),
        CheckConstraint("status IN ('active','superseded','deleted')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        Index("uq_master_upload_active_period", "category", "year", "month", unique=True,
              postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    records: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
