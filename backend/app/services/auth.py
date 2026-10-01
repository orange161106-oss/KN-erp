import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.repositories.auth import find_user_by_username, find_user_with_permissions
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.security.passwords import PasswordService
from app.security.tokens import InvalidAccessToken, create_access_token, decode_access_token

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
            id=user.id, username=user.username,
            roles=sorted(role.code for role in user.roles),
            permissions=sorted({permission.code for role in user.roles for permission in role.permissions}),
        )
    except SQLAlchemyError:
        raise database_unavailable() from None
