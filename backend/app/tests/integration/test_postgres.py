import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import create_session_factory, session_scope
from app.main import create_app

pytestmark = pytest.mark.integration


def test_postgresql_connectivity_and_utc(postgres_engine):
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert connection.execute(text("SHOW timezone")).scalar_one() == "UTC"


def test_health_with_real_postgresql(postgres_settings, postgres_engine):
    with TestClient(create_app(postgres_settings)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.parametrize("raise_error", [False, True])
def test_uncommitted_transaction_is_rolled_back(postgres_engine, raise_error):
    with postgres_engine.connect() as connection:
        connection.execute(text("CREATE TEMP TABLE foundation_probe (value INTEGER)"))
        connection.commit()
        factory = create_session_factory(connection)
        try:
            with session_scope(factory) as session:
                session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
                if raise_error:
                    raise RuntimeError("service failed")
        except RuntimeError:
            assert raise_error
        assert connection.execute(text("SELECT COUNT(*) FROM foundation_probe")).scalar_one() == 0
        connection.execute(text("DROP TABLE foundation_probe"))
        connection.commit()
