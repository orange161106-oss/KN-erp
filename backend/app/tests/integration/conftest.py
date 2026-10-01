import os

import pytest
from sqlalchemy import inspect

from app.core.config import Settings, parse_database_url
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
    return Settings(_env_file=None, app_env="test", database_url=value)


@pytest.fixture(scope="session")
def postgres_engine(postgres_settings):
    engine = create_db_engine(postgres_settings)
    try:
        # Only a dedicated, otherwise empty public schema is accepted for this foundation.
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        yield engine
    finally:
        engine.dispose()
