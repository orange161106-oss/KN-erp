from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.errors import ApplicationError
from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user
from app.security.policy import allows


def check_permissions(user: CurrentUser, required: frozenset[str]) -> None:
    if not required:
        raise ValueError("Permission checks require at least one explicit permission code")
    if not all(allows(user, code) for code in required):
        raise ApplicationError("PERMISSION_DENIED", "Required permission is missing.", 403)


def require_permissions(*codes: str) -> Callable[..., CurrentUser]:
    if not codes or any(not code or code != code.strip() for code in codes):
        raise ValueError("Permission checks require explicit non-empty permission codes")
    required = frozenset(codes)

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        check_permissions(user, required)
        return user

    return dependency
