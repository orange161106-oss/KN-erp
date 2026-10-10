from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectionInputSet(Base):
    """Immutable normalized source evidence, not a second PO or requirements system."""
    __tablename__ = 'projection_input_sets'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_set_id: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('consumables.id', ondelete='RESTRICT'), index=True, nullable=False)
    planning_version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('planning_versions.id', ondelete='RESTRICT'), nullable=False)
    stock_snapshot_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('stock_snapshots.id', ondelete='RESTRICT'), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    imported_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
