from sqlalchemy.orm import Session

from app.db.reliability import read_only
from app.repositories.health import check_database
from app.schemas.health import HealthResponse

def get_health(session: Session) -> HealthResponse:
    read_only(session, lambda: check_database(session))
    return HealthResponse()
