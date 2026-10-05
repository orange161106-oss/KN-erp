from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_timeout=settings.db_connect_timeout_seconds,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": "-c timezone=UTC",
        },
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
