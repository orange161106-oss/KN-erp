"""No connection secrets are stored in Alembic's INI or log configuration."""

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import String, inspect
from sqlalchemy.sql.elements import ClauseElement

from app import models  # noqa: F401 -- register future models here before autogeneration
from app.core.config import load_settings
from app.db.base import Base
from app.db.session import create_db_engine

target_metadata = Base.metadata


class KnPostgresqlImpl(PostgresqlImpl):
    """Keep merged/shared revision IDs intact when they exceed Alembic's default."""

    __dialect__ = "postgresql"

    def version_table_impl(self, **kwargs):
        table = super().version_table_impl(**kwargs)
        table.c.version_num.type = String(128)
        return table

    def bulk_insert(self, table, rows, multiinsert=True):
        # M3.4/M3.5 seed rows contain SQL UUID expressions. Psycopg cannot bind
        # expressions as scalar parameters; compile them into INSERT values.
        # Offline behavior already emits expressions and stays unchanged.
        if not self.as_sql and any(isinstance(value, ClauseElement) for row in rows for value in row.values()):
            for row in rows:
                self._exec(table.insert().inline().values(**row))
        else:
            super().bulk_insert(table, rows, multiinsert=multiinsert)


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
        if context.get_starting_revision_argument() not in (None, "base"):
            context.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
        context.run_migrations()


def run_migrations_online() -> None:
    # Supplied connections allow tests/tools to control the migration transaction.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_with_connection(connection)
        return
    engine = create_db_engine(load_settings())
    try:
        with engine.begin() as connection:
            run_with_connection(connection)
    finally:
        engine.dispose()


def run_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        inspector = inspect(connection)
        if inspector.has_table("alembic_version"):
            column = next(item for item in inspector.get_columns("alembic_version") if item["name"] == "version_num")
            length = getattr(column["type"], "length", None)
            if length is not None and length < 128:
                context.get_context().impl.alter_column(
                    "alembic_version", "version_num", type_=String(128),
                    existing_type=column["type"], existing_nullable=False,
                )
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
