from uuid import UUID, uuid4
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog, UserSession
from app.models.auth import Role, User
from app.security.passwords import PasswordService
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


def test_auth_login_creates_session_and_audit_log(db_session, client):
    passwords = PasswordService()
    admin_role = Role(code="ADMIN", name="Administrator")
    db_session.add(admin_role)

    user = User(
        username="superadmin",
        password_hash=passwords.hash("adminsecret"),
        full_name="Super Administrator",
        employee_id="EMP001",
        is_super_admin=True,
        roles=[admin_role],
    )
    db_session.add(user)
    db_session.commit()

    # 1. Login
    res = client.post("/api/v1/auth/login", json={"username": "superadmin", "password": "adminsecret"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert "session_id" in data
    session_id = data["session_id"]
    assert session_id is not None

    # Verify UserSession is created in DB
    session_row = db_session.scalar(select(UserSession).where(UserSession.id == UUID(session_id)))
    assert session_row is not None
    assert session_row.status == "ACTIVE"
    assert session_row.user_id == user.id

    # Verify LOGIN AuditLog entry exists
    login_audit = db_session.scalar(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "LOGIN")
    )
    assert login_audit is not None
    assert login_audit.module == "Authentication"

    # 2. Logout
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    logout_res = client.post("/api/v1/auth/logout", json={"session_id": session_id}, headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "LOGGED_OUT"

    # Verify session is marked LOGGED_OUT
    db_session.refresh(session_row)
    assert session_row.status == "LOGGED_OUT"
    assert session_row.logout_at is not None

    # Verify LOGOUT AuditLog entry exists
    logout_audit = db_session.scalar(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "LOGOUT")
    )
    assert logout_audit is not None


def test_admin_audit_logs_and_sessions_endpoints(db_session, client):
    settings = app.state.settings
    passwords = PasswordService()

    admin_role = Role(code="ADMIN", name="Admin")
    user_role = Role(code="USER", name="User")
    db_session.add_all([admin_role, user_role])

    admin = User(
        username="audit_admin",
        password_hash=passwords.hash("pass123"),
        full_name="Audit Administrator",
        employee_id="ADM999",
        is_super_admin=True,
        roles=[admin_role],
    )
    standard_user = User(
        username="standard_worker",
        password_hash=passwords.hash("pass123"),
        full_name="Worker John",
        employee_id="WRK001",
        is_super_admin=False,
        roles=[user_role],
    )
    db_session.add_all([admin, standard_user])
    db_session.commit()

    admin_token = create_access_token(admin.id, settings)
    user_token = create_access_token(standard_user.id, settings)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 1. Standard user is blocked from admin endpoints
    audit_forbidden = client.get("/api/v1/admin/audit-logs", headers=user_headers)
    assert audit_forbidden.status_code == 403

    sessions_forbidden = client.get("/api/v1/admin/active-sessions", headers=user_headers)
    assert sessions_forbidden.status_code == 403

    # 2. Insert some activity logs
    db_session.add_all([
        AuditLog(
            user_id=admin.id,
            username=admin.username,
            action="CREATE",
            module="Product Master - Consumables",
            record_id="CON-001",
            changes_summary={"item_id": "CON-001", "name": "Grease"},
        ),
        AuditLog(
            user_id=admin.id,
            username=admin.username,
            action="UPDATE",
            module="Product Master - Consumables",
            record_id="CON-001",
            changes_summary={"rate": 150.0},
        ),
        AuditLog(
            user_id=admin.id,
            username=admin.username,
            action="DELETE",
            module="Product Master - Consumables",
            record_id="CON-001",
            changes_summary={"is_active": False},
        ),
    ])
    # And a user session
    db_session.add(
        UserSession(
            user_id=admin.id,
            ip_address="127.0.0.1",
            status="ACTIVE",
        )
    )
    db_session.commit()

    # 3. Query audit logs with Admin
    audit_res = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["total"] >= 3
    assert len(audit_data["items"]) >= 3

    # Query with action filter
    filter_res = client.get("/api/v1/admin/audit-logs?action=DELETE", headers=admin_headers)
    assert filter_res.status_code == 200
    filter_data = filter_res.json()
    assert filter_data["total"] == 1
    assert filter_data["items"][0]["action"] == "DELETE"

    # 4. Query active sessions with Admin
    session_res = client.get("/api/v1/admin/active-sessions", headers=admin_headers)
    assert session_res.status_code == 200
    session_data = session_res.json()
    assert session_data["total"] >= 1
    first_session = session_data["items"][0]
    assert first_session["username"] == "audit_admin"
    assert first_session["full_name"] == "Audit Administrator"
    assert first_session["role"] == "SUPER_ADMIN"
    assert first_session["status"] == "ACTIVE"
