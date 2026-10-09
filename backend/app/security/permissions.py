from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.errors import ApplicationError
from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user


def check_permissions(user: CurrentUser, required: frozenset[str]) -> None:
    if not required:
        raise ValueError("Permission checks require at least one explicit permission code")
    
    # Super Admin and ADMIN base role bypass all permission checks
    if user.is_super_admin or "ADMIN" in user.roles:
        return

    # Evaluate granular feature flags
    for code in required:
        if "masters." in code or "masters" in code:
            if any(getattr(user, f"masters_{op}", False) for op in ("read", "create", "update", "delete")):
                return
            if any(getattr(user, f"production_mappings_{op}", False) for op in ("read", "create", "update", "delete")):
                return
            if any(getattr(user, f"consumption_norms_{op}", False) for op in ("read", "create", "update", "delete")):
                return
        if "prd." in code and any(getattr(user, f"prd_planning_{op}", False) for op in ("read", "create", "update", "delete")):
            return
        if "requirements." in code and any(getattr(user, f"requirements_{op}", False) for op in ("read", "create", "update", "delete")):
            return
        if "grns" in code and any(getattr(user, f"goods_receipts_{op}", False) for op in ("read", "create", "update", "delete")):
            return
        if "orders" in code and (
            any(getattr(user, f"purchase_orders_{op}", False) for op in ("read", "create", "update", "delete")) or
            any(getattr(user, f"purchase_{op}", False) for op in ("read", "create", "update", "delete"))
        ):
            return
        if code in user.permissions:
            return

    raise ApplicationError("PERMISSION_DENIED", "Required permission is missing.", 403)


def require_permissions(*codes: str) -> Callable[..., CurrentUser]:
    if not codes or any(not code or code != code.strip() for code in codes):
        raise ValueError("Permission checks require explicit non-empty permission codes")
    required = frozenset(codes)

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        check_permissions(user, required)
        return user

    return dependency


def require_feature_flag(flag_name: str) -> Callable[..., CurrentUser]:
    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.is_super_admin or "ADMIN" in user.roles:
            return user
        if getattr(user, flag_name, False):
            return user
        raise ApplicationError("PERMISSION_DENIED", f"Feature flag '{flag_name}' is required.", 403)

    return dependency
