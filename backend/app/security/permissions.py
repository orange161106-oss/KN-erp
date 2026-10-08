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
        if "masters." in code and (getattr(user, "can_access_masters", False) or getattr(user, "can_access_production_mappings", False) or getattr(user, "can_access_consumption_norms", False)):
            return
        if "prd." in code and getattr(user, "can_access_prd_planning", False):
            return
        if "requirements." in code and getattr(user, "can_access_requirements", False):
            return
        if "grns" in code and getattr(user, "can_access_goods_receipts", False):
            return
        if "orders" in code and (getattr(user, "can_access_purchase_orders", False) or getattr(user, "can_access_purchase", False)):
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
