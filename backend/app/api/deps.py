from typing import Annotated
from fastapi import Depends, HTTPException, status

from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user


def require_admin_role(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Enforces admin access. Raises 403 Forbidden if user is strictly USER or lacks admin privileges."""
    if current_user.is_super_admin:
        return current_user

    roles_normalized = [r.upper().strip() for r in current_user.roles]
    if "SUPER ADMIN" in roles_normalized or "SUPER_ADMIN" in roles_normalized or "ADMIN" in roles_normalized:
        return current_user

    # If role is strictly USER or lacks admin privileges
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role required. Access denied for standard users.",
    )
