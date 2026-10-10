from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import Settings


class InvalidAccessToken(Exception):
    """A deliberately generic authentication failure."""


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id), "iat": now,
            "exp": now + timedelta(minutes=settings.auth_access_token_expire_minutes),
            "iss": settings.auth_token_issuer, "aud": settings.auth_token_audience,
            "token_type": "access",
        },
        settings.signing_key(), algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        claims = jwt.decode(
            token, settings.signing_key(), algorithms=["HS256"],
            issuer=settings.auth_token_issuer, audience=settings.auth_token_audience,
            options={"require": ["sub", "iat", "exp", "iss", "aud", "token_type"]},
        )
        if claims["token_type"] != "access":
            raise InvalidAccessToken()
        return UUID(claims["sub"])
    except (InvalidTokenError, ValueError, TypeError, AttributeError):
        raise InvalidAccessToken() from None
