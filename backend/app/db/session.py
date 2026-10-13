from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    is_sqlite = "sqlite" in str(settings.sqlalchemy_url).lower()
    if is_sqlite:
        return create_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            hide_parameters=True,
        )

    connect_args = {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "options": "-c timezone=UTC",
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        connect_args=connect_args,
        hide_parameters=True,
    )


def create_session_factory(engine: Engine | Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Close every session; services explicitly decide when to commit."""
    with factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def get_db(request: Request) -> Generator[Session, None, None]:
    with session_scope(request.app.state.session_factory) as session:
        yield session
