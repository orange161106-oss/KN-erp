import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.repositories.auth import find_user_by_username, find_user_with_permissions
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.security.passwords import PasswordService
from app.security.tokens import InvalidAccessToken, create_access_token, decode_access_token
from app.security.policy import effective_permissions

logger = logging.getLogger("kn.backend.auth")
BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}


def authentication_required() -> ApplicationError:
    return ApplicationError(
        "NOT_AUTHENTICATED", "Valid authentication is required.", 401,
        headers=BEARER_HEADERS,
    )


def database_unavailable() -> ApplicationError:
    logger.warning("authentication_database_unavailable")
    return ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503)


def login(
    session: Session, credentials: LoginRequest,
    settings: Settings, passwords: PasswordService,
) -> TokenResponse:
    try:
        user = find_user_by_username(session, credentials.username)
    except SQLAlchemyError:
        raise database_unavailable() from None
    password = credentials.password.get_secret_value()
    if user is None:
        passwords.verify_dummy(password)
        valid = False
    else:
        valid = passwords.verify(password, user.password_hash) and user.is_active
    if not valid:
        raise ApplicationError(
            "INVALID_CREDENTIALS", "Invalid username or password.", 401,
            headers=BEARER_HEADERS,
        )
    token = create_access_token(user.id, settings)
    user_identity = current_user(session, token, settings)
    return TokenResponse(
        access_token=token,
        expires_in=settings.auth_access_token_expire_minutes * 60,
        user=user_identity,
    )


def current_user(session: Session, token: str, settings: Settings) -> CurrentUser:
    try:
        user_id = decode_access_token(token, settings)
    except InvalidAccessToken:
        raise authentication_required() from None
    try:
        user = find_user_with_permissions(session, user_id)
        if user is None or not user.is_active:
            raise authentication_required()
        crud_modules = [
            "masters", "production_mappings", "consumption_norms",
            "prd_planning", "requirements", "plant_workflow",
            "inventory", "purchase", "purchase_orders", "goods_receipts",
        ]
        crud_flags = {
            f"{module}_{op}": getattr(user, f"{module}_{op}", False)
            for module in crud_modules
            for op in ("read", "create", "update", "delete")
        }
        return CurrentUser(
            id=user.id,
            username=user.username,
            is_super_admin=getattr(user, "is_super_admin", False),
            roles=sorted(role.code for role in user.roles),
            permissions=sorted({permission.code for role in user.roles for permission in role.permissions}),
            plant_ids=[identity for slot, identity in getattr(settings, "plant_permission_ids", {}).items()
                       if getattr(user, f"can_access_plant_{slot}", False)],
            **crud_flags,
            can_access_plant_1=getattr(user, "can_access_plant_1", False),
            can_access_plant_2=getattr(user, "can_access_plant_2", False),
            can_access_plant_3=getattr(user, "can_access_plant_3", False),
            can_access_plant_4=getattr(user, "can_access_plant_4", False),
            can_access_plant_5=getattr(user, "can_access_plant_5", False),
            can_access_dashboard=getattr(user, "can_access_dashboard", False),
            can_access_reports=getattr(user, "can_access_reports", False),
            alert_production=getattr(user, "alert_production", False),
            alert_inventory=getattr(user, "alert_inventory", False),
            alert_purchasing=getattr(user, "alert_purchasing", False),
            alert_system=getattr(user, "alert_system", False),
        )
    except SQLAlchemyError:
        raise database_unavailable() from None
