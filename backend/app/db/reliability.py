"""Safe diagnostics and bounded recovery for explicitly read-only operations."""
import logging

from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError

logger = logging.getLogger("kn.backend.database")


def database_failure(error: SQLAlchemyError | None) -> tuple[str, str]:
    state = getattr(getattr(error, "orig", None), "sqlstate", None)
    state = state if isinstance(state, str) and len(state) == 5 and state.isalnum() else "none"
    if state in {"42703", "42P01"}:
        category = "schema"
    elif state.startswith("28"):
        category = "credentials"
    elif state == "53300" or isinstance(error, TimeoutError):
        category = "capacity"
    elif (state.startswith("08") or state in {"57P01", "57P02", "57P03"}
          or isinstance(error, DBAPIError) and error.connection_invalidated
          or isinstance(error, OperationalError) and state == "none"):
        category = "connection"
    else:
        category = "other"
    return category, state


def database_unavailable(error: SQLAlchemyError | None = None) -> ApplicationError:
    category, state = database_failure(error)
    # Do not log raw SQL, exceptions, URLs, passwords or submitted data.
    logger.warning("database_unavailable category=%s sqlstate=%s", category, state)
    return ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503,
                            details={"category": category, "retryable": category == "connection"})


def read_only(session: Session, operation):
    """Retry one read after rollback; never wrap a write or a locked transaction."""
    for attempt in range(2):
        try:
            return operation()
        except SQLAlchemyError as error:
            category, state = database_failure(error)
            if attempt == 0 and category == "connection":
                logger.warning("database_reconnecting sqlstate=%s", state)
                try:
                    session.rollback()
                except SQLAlchemyError as rollback_error:
                    raise database_unavailable(rollback_error) from None
                continue
            raise database_unavailable(error) from None
