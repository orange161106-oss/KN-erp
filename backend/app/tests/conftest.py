from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, app_env="test",
        database_url="postgresql+psycopg://test_user@127.0.0.1/kn_unit_test",
    )


@pytest.fixture
def database_session():
    session = MagicMock(spec=Session)
    session.execute.return_value.scalar_one.return_value = 1
    return session


@pytest.fixture
def app(settings, database_session):
    application = create_app(settings)
    application.dependency_overrides[get_db] = lambda: database_session
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
