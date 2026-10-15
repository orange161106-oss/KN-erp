from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now(), nullable=False)
    logout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", server_default=text("'ACTIVE'"), nullable=False, index=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    record_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    changes_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now(), nullable=False, index=True)

    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id], lazy="selectin")

    # Legacy/compatibility fields for existing codebase
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now(), nullable=True)

    def __init__(self, **kwargs: Any) -> None:
        # Sync user_id and actor_id
        if "user_id" in kwargs and "actor_id" not in kwargs:
            kwargs["actor_id"] = kwargs["user_id"]
        elif "actor_id" in kwargs and "user_id" not in kwargs:
            kwargs["user_id"] = kwargs["actor_id"]

        # Sync module and entity_type
        if "module" in kwargs and "entity_type" not in kwargs:
            kwargs["entity_type"] = kwargs["module"]
        elif "entity_type" in kwargs and "module" not in kwargs:
            kwargs["module"] = kwargs["entity_type"]

        # Sync record_id and entity_id
        if "record_id" in kwargs and "entity_id" not in kwargs:
            try:
                kwargs["entity_id"] = UUID(str(kwargs["record_id"]))
            except (ValueError, TypeError):
                pass
        elif "entity_id" in kwargs and "record_id" not in kwargs:
            kwargs["record_id"] = str(kwargs["entity_id"])

        # Sync changes_summary and new_values
        if "changes_summary" in kwargs and "new_values" not in kwargs:
            kwargs["new_values"] = kwargs["changes_summary"]
        elif "new_values" in kwargs and "changes_summary" not in kwargs:
            kwargs["changes_summary"] = kwargs["new_values"]

        # Sync timestamp and created_at
        if "timestamp" in kwargs and "created_at" not in kwargs:
            kwargs["created_at"] = kwargs["timestamp"]
        elif "created_at" in kwargs and "timestamp" not in kwargs:
            kwargs["timestamp"] = kwargs["created_at"]

        # Reason default
        if "reason" not in kwargs and "action" in kwargs:
            kwargs["reason"] = kwargs["action"]

        super().__init__(**kwargs)
