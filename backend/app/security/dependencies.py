from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.services.auth import authentication_required, current_user

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CurrentUser:
    if credentials is None:
        raise authentication_required()
    return current_user(session, credentials.credentials, request.app.state.settings)


def require_admin_role(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Enforces admin access. Raises 403 Forbidden if user is strictly USER or lacks admin privileges."""
    if current_user.is_super_admin:
        return current_user

    roles_normalized = [r.upper().strip() for r in current_user.roles]
    if "SUPER ADMIN" in roles_normalized or "SUPER_ADMIN" in roles_normalized or "ADMIN" in roles_normalized:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role required. Access denied for standard users.",
    )
