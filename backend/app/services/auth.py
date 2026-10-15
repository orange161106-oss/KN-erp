import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.reliability import database_failure as _database_failure, database_unavailable, read_only
from app.repositories.auth import find_user_by_username, find_user_with_permissions
from app.schemas.auth import CurrentUser, LoginRequest, LogoutResponse, TokenResponse
from app.security.passwords import PasswordService
from app.security.tokens import InvalidAccessToken, create_access_token, decode_access_token
from app.security.policy import effective_permissions
from app.services.audit import close_user_session, create_user_session, log_activity

logger = logging.getLogger("kn.backend.auth")
BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}


def authentication_required() -> ApplicationError:
    return ApplicationError(
        "NOT_AUTHENTICATED", "Valid authentication is required.", 401,
        headers=BEARER_HEADERS,
    )


def _read_authentication(session: Session, operation):
    return read_only(session, operation)


def login(
    session: Session, credentials: LoginRequest,
    settings: Settings, passwords: PasswordService,
    client_ip: str | None = None,
) -> TokenResponse:
    user = _read_authentication(session, lambda: find_user_by_username(session, credentials.username))
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

    # Session tracking & audit logging
    user_session = create_user_session(session, user_id=user.id, ip_address=client_ip)
    session.flush()
    log_activity(
        session,
        user=user,
        action="LOGIN",
        module="Authentication",
        record_id=str(user_session.id),
        details={"ip_address": client_ip, "status": "ACTIVE"},
    )
    session.commit()

    return TokenResponse(
        access_token=token,
        expires_in=settings.auth_access_token_expire_minutes * 60,
        user=user_identity,
        session_id=user_session.id,
    )


def logout(
    session: Session,
    user: CurrentUser,
    session_id: UUID | None = None,
) -> LogoutResponse:
    closed_session = close_user_session(session, user_id=user.id, session_id=session_id)
    log_activity(
        session,
        user=user,
        action="LOGOUT",
        module="Authentication",
        record_id=str(closed_session.id) if closed_session else None,
        details={"status": "LOGGED_OUT"},
    )
    session.commit()
    return LogoutResponse(
        message="Logged out successfully",
        status="LOGGED_OUT",
    )


def current_user(session: Session, token: str, settings: Settings) -> CurrentUser:
    try:
        user_id = decode_access_token(token, settings)
    except InvalidAccessToken:
        raise authentication_required() from None
    try:
        user = _read_authentication(session, lambda: find_user_with_permissions(session, user_id))
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
        assigned_plant_val = getattr(user, "assigned_plant", None)
        if not assigned_plant_val:
            for slot in (1, 2, 3, 4, 5):
                if getattr(user, f"can_access_plant_{slot}", False):
                    assigned_plant_val = f"PLANT_{slot}"
                    break

        return CurrentUser(
            id=user.id,
            username=user.username,
            assigned_plant=assigned_plant_val,
            is_super_admin=getattr(user, "is_super_admin", False),
            is_superuser=getattr(user, "is_super_admin", False),
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
            alert_production=getattr(user, "alert_production", False),
            alert_inventory=getattr(user, "alert_inventory", False),
            alert_purchasing=getattr(user, "alert_purchasing", False),
            alert_system=getattr(user, "alert_system", False),
        )
    except SQLAlchemyError as error:
        raise database_unavailable(error) from None
