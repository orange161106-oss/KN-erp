from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import Role, User
from app.security.tokens import create_access_token


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda val: val.strip() if val else "")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(db_session):
    settings = app.state.settings
    admin_role = Role(code="ADMIN", name="Administrator")
    db_session.add(admin_role)
    admin_user = User(
        username="admin_planner",
        password_hash="secret",
        is_super_admin=True,
        roles=[admin_role],
    )
    db_session.add(admin_user)
    db_session.commit()

    token = create_access_token(admin_user.id, settings)
    return {"Authorization": f"Bearer {token}"}


def test_issues_export_unauthenticated_returns_401(client):
    res = client.get("/api/v1/requirements/workspace/issues/export?period=2026-10")
    assert res.status_code == 401


def test_issues_export_with_period_param_returns_csv(client, auth_headers):
    res = client.get("/api/v1/requirements/workspace/issues/export?period=2026-10", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]
    # Verify CSV headers are in content
    assert "Part No." in res.text
    assert "Issue Description" in res.text


def test_issues_export_with_month_year_params_returns_csv(client, auth_headers):
    res = client.get("/api/v1/requirements/workspace/issues/export?month=10&year=2026", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]


def test_issues_export_alias_route(client, auth_headers):
    res = client.get("/api/v1/requirements/issues/export?period=2026-10", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]
