"""No connection secrets are stored in Alembic's INI or log configuration."""

from alembic import context

from app import models  # noqa: F401 -- register future models here before autogeneration
from app.core.config import load_settings
from app.db.base import Base
from app.db.session import create_db_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = load_settings()
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Supplied connections allow tests/tools to control the migration transaction.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_with_connection(connection)
        return
    engine = create_db_engine(load_settings())
    try:
        with engine.connect() as connection:
            run_with_connection(connection)
    finally:
        engine.dispose()


def run_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
