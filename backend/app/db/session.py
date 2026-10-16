from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.reliability import database_unavailable
from sqlalchemy.exc import SQLAlchemyError


def create_db_engine(settings: Settings, url: URL | None = None) -> Engine:
    target_url = url or settings.sqlalchemy_url
    is_sqlite = "sqlite" in str(target_url).lower()
    if is_sqlite:
        return create_engine(
            target_url,
            pool_pre_ping=True,
            hide_parameters=True,
        )

    connect_args = {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "options": "-c timezone=UTC",
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "prepare_threshold": None,  # Prevents psycopg from using prepared statements on transaction poolers
    }

    # For transaction pooling (port 6543) or Supabase pooler, use NullPool
    # NullPool delegates connection management to Supabase's transaction pooler
    # and prevents local workers from exhausting connection limits.
    is_transaction_pooler = target_url.port == 6543 or "pooler.supabase.com" in (target_url.host or "")
    if is_transaction_pooler:
        return create_engine(
            target_url,
            poolclass=NullPool,
            connect_args=connect_args,
            hide_parameters=True,
        )

    return create_engine(
        target_url,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_size=2,
        max_overflow=2,
        pool_timeout=15,
        connect_args=connect_args,
        hide_parameters=True,
    )


def create_session_factory(engine: Engine | Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def warm_remote_connection(engine: Engine, settings: Settings) -> None:
    """Prepare one remote connection before login; never migrate or write data."""
    if (not settings.db_warmup_on_startup or settings.app_env == "test"
            or settings.sqlalchemy_url.host in {None, "localhost", "127.0.0.1", "::1"}):
        return
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError as error:
        # A provider outage remains recoverable after startup. Diagnostics contain
        # codes only; it must not crash startup or rewrite the database.
        database_unavailable(error)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Close every session; services explicitly decide when to commit."""
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db(request: Request) -> Generator[Session, None, None]:
    with session_scope(request.app.state.session_factory) as session:
        yield session
