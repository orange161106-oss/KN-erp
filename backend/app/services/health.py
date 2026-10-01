import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.repositories.health import check_database
from app.schemas.health import HealthResponse

logger = logging.getLogger("kn.backend.health")


def get_health(session: Session) -> HealthResponse:
    try:
        check_database(session)
    except SQLAlchemyError:
        logger.warning("database_unavailable")
        raise ApplicationError(
            "DATABASE_UNAVAILABLE", "Database is unavailable.", 503,
        ) from None
    return HealthResponse()
