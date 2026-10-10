"""Audit logging service helper for M8.1 — Atomic Audit Trail."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_audit_event(
    session: Session,
    *,
    actor_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_values: dict[str, Any] | None = None,
    old_values: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    """Create and stage an AuditLog record in the active database session.

    Ensures 100% atomic execution: the audit record is staged within the active
    SQLAlchemy session and commits in the exact same transaction as the business operation.
    """
    audit = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        reason=reason,
    )
    session.add(audit)
    return audit
