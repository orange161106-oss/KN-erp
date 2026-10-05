from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database(session: Session) -> None:
    session.execute(text("SELECT 1")).scalar_one()
