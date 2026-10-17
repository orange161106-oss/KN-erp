from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AuditLog, UserSession


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


def log_activity(
    session: Session,
    *,
    user: Any | None = None,
    action: str,
    module: str,
    record_id: str | None = None,
    details: dict[str, Any] | str | None = None,
    user_id: UUID | None = None,
    username: str | None = None,
) -> AuditLog:
    """Reusable mutation hook for user activities across modules."""
    if user is not None:
        if getattr(user, "id", None) and user_id is None:
            user_id = user.id
        if getattr(user, "username", None) and username is None:
            username = user.username

    changes_summary = (
        details if isinstance(details, dict)
        else ({"message": str(details)} if details is not None else None)
    )

    audit = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        module=module,
        record_id=str(record_id) if record_id is not None else None,
        changes_summary=changes_summary,
    )
    session.add(audit)
    return audit


def create_user_session(
    session: Session,
    *,
    user_id: UUID,
    ip_address: str | None = None,
) -> UserSession:
    """Create a new active session record upon successful authentication."""
    user_session = UserSession(
        user_id=user_id,
        ip_address=ip_address,
        status="ACTIVE",
    )
    session.add(user_session)
    return user_session


def close_user_session(
    session: Session,
    *,
    user_id: UUID | str,
    session_id: UUID | str | None = None,
) -> UserSession | None:
    """Mark an active user session as LOGGED_OUT with current timestamp."""
    uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
    query = session.query(UserSession).filter(
        UserSession.user_id == uid,
        UserSession.status == "ACTIVE",
    )
    if session_id:
        try:
            sid = UUID(str(session_id)) if not isinstance(session_id, UUID) else session_id
            query = query.filter(UserSession.id == sid)
        except (ValueError, TypeError):
            pass
    active_session = query.order_by(UserSession.login_at.desc()).first()
    if active_session:
        active_session.status = "LOGGED_OUT"
        active_session.logout_at = func.now()
    return active_session
