import os
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.schema import CreateSchema, DropSchema
from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_ROOT, Settings, parse_database_url
from app.db.session import create_db_engine


@pytest.fixture(scope="session")
def postgres_settings():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    url = parse_database_url(value)
    if not url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a disposable database ending in _test")
    runtime_url = os.environ.get("DATABASE_URL")
    if runtime_url:
        runtime = parse_database_url(runtime_url)
        if (url.host, url.port or 5432, url.database) == (runtime.host, runtime.port or 5432, runtime.database):
            pytest.fail("TEST_DATABASE_URL must differ from the application database")
    return Settings(_env_file=None, app_env="test", database_url=value, auth_secret_key=secrets.token_urlsafe(48))


@pytest.fixture(scope="session")
def postgres_engine(postgres_settings):
    # All mutations are confined to a uniquely named schema created by this fixture.
    schema = "m13_test_" + uuid4().hex
    administration_engine = create_db_engine(postgres_settings)
    with administration_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_db_engine(postgres_settings)

    @event.listens_for(engine, "connect")
    def set_test_schema(dbapi_connection, connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET search_path TO " + schema)
        dbapi_connection.commit()

    try:
        with engine.begin() as connection:
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        try:
            with administration_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        finally:
            administration_engine.dispose()
