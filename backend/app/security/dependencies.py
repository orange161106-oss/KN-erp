from typing import Annotated

from fastapi import Depends, Request
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
