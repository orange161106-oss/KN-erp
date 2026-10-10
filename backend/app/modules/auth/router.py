from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.schemas.error import ErrorResponse
from app.security.dependencies import get_current_user
from app.services.auth import login

router = APIRouter(prefix="/auth", tags=["authentication"])
AUTH_RESPONSES = {401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post("/login", response_model=TokenResponse, responses=AUTH_RESPONSES)
def login_route(
    credentials: LoginRequest, request: Request, response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return login(session, credentials, request.app.state.settings, request.app.state.passwords)


@router.get("/me", response_model=CurrentUser, responses=AUTH_RESPONSES)
def current_user_route(
    response: Response, user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return user
