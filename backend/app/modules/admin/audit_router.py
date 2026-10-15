from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_admin_role
from app.db.session import get_db
from app.models.audit import AuditLog, UserSession
from app.models.auth import User
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin-audit"])


class AuditLogItem(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    username: str
    action: str
    module: Optional[str] = None
    record_id: Optional[str] = None
    changes_summary: Optional[dict[str, Any]] = None
    timestamp: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int


class UserSessionItem(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    role: str
    ip_address: Optional[str] = None
    login_at: datetime
    logout_at: Optional[datetime] = None
    status: str


class UserSessionListResponse(BaseModel):
    items: list[UserSessionItem]
    total: int
    limit: int
    offset: int


@router.get("/audit-logs", response_model=AuditLogListResponse)
def get_audit_logs(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
    user_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditLogListResponse:
    query = select(AuditLog).options(selectinload(AuditLog.user))

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action and action.strip():
        query = query.where(func.upper(AuditLog.action) == action.strip().upper())
    if module and module.strip():
        query = query.where(func.lower(AuditLog.module).contains(module.strip().lower()))
    if date_from:
        query = query.where(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.where(AuditLog.timestamp <= date_to)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = session.scalars(query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)).all()

    items: list[AuditLogItem] = []
    for r in records:
        username = r.username or (r.user.username if r.user else "System")
        items.append(
            AuditLogItem(
                id=r.id,
                user_id=r.user_id,
                username=username,
                action=r.action,
                module=r.module or r.entity_type or "General",
                record_id=r.record_id or (str(r.entity_id) if r.entity_id else None),
                changes_summary=r.changes_summary or r.new_values,
                timestamp=r.timestamp or r.created_at,
            )
        )

    return AuditLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/active-sessions", response_model=UserSessionListResponse)
def get_active_sessions(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> UserSessionListResponse:
    query = select(UserSession).options(
        selectinload(UserSession.user).selectinload(User.roles)
    )

    if status and status.strip():
        query = query.where(func.upper(UserSession.status) == status.strip().upper())

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    sessions = session.scalars(query.order_by(UserSession.login_at.desc()).offset(offset).limit(limit)).all()

    items: list[UserSessionItem] = []
    for s in sessions:
        u = s.user
        role = (
            "SUPER_ADMIN"
            if (u and u.is_super_admin)
            else (u.roles[0].code if (u and u.roles) else "USER")
        )
        items.append(
            UserSessionItem(
                id=s.id,
                user_id=s.user_id,
                username=u.username if u else "Unknown",
                full_name=u.full_name if u else None,
                employee_id=u.employee_id if u else None,
                role=role,
                ip_address=s.ip_address,
                login_at=s.login_at,
                logout_at=s.logout_at,
                status=s.status,
            )
        )

    return UserSessionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
