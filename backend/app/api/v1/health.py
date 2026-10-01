from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.error import ErrorResponse
from app.schemas.health import HealthResponse
from app.services.health import get_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
def health(session: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    return get_health(session)
