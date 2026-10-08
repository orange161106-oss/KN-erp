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
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.auth_access_token_expire_minutes * 60,
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
        return CurrentUser(
            id=user.id,
            username=user.username,
            is_super_admin=getattr(user, "is_super_admin", False),
            roles=sorted(role.code for role in user.roles),
            permissions=effective_permissions(user, {p.code for role in user.roles for p in role.permissions}),
            plant_ids=[identity for slot, identity in settings.plant_permission_ids.items()
                       if getattr(user, f"can_access_plant_{slot}", False)],
            can_view_master_data=getattr(user, "can_view_master_data", False),
            can_edit_master_data=getattr(user, "can_edit_master_data", False),
            can_view_planning=getattr(user, "can_view_planning", False),
            can_run_calculations=getattr(user, "can_run_calculations", False),
            can_confirm_demand=getattr(user, "can_confirm_demand", False),
            can_approve_extra_demand=getattr(user, "can_approve_extra_demand", False),
            can_create_po=getattr(user, "can_create_po", False),
            can_approve_po=getattr(user, "can_approve_po", False),
            can_upload_grn=getattr(user, "can_upload_grn", False),
            can_view_reports=getattr(user, "can_view_reports", False),
            can_access_masters=getattr(user, "can_access_masters", False),
            can_access_production_mappings=getattr(user, "can_access_production_mappings", False),
            can_access_consumption_norms=getattr(user, "can_access_consumption_norms", False),
            can_access_prd_planning=getattr(user, "can_access_prd_planning", False),
            can_access_requirements=getattr(user, "can_access_requirements", False),
            can_access_plant_workflow=getattr(user, "can_access_plant_workflow", False),
            can_access_inventory=getattr(user, "can_access_inventory", False),
            can_access_purchase=getattr(user, "can_access_purchase", False),
            can_access_purchase_orders=getattr(user, "can_access_purchase_orders", False),
            can_access_goods_receipts=getattr(user, "can_access_goods_receipts", False),
            can_access_plant_1=getattr(user, "can_access_plant_1", False),
            can_access_plant_2=getattr(user, "can_access_plant_2", False),
            can_access_plant_3=getattr(user, "can_access_plant_3", False),
            can_access_plant_4=getattr(user, "can_access_plant_4", False),
            can_access_plant_5=getattr(user, "can_access_plant_5", False),
        )
    except SQLAlchemyError:
        raise database_unavailable() from None
