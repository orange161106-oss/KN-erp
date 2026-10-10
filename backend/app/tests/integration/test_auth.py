from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, session_scope
from app.main import create_app
from app.models.auth import Permission, Role, User, role_permissions, user_roles
from app.security.permissions import require_permissions

pytestmark = pytest.mark.integration


@pytest.fixture
def database_connection(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()


@pytest.fixture
def auth_session(database_connection):
    with Session(bind=database_connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as session:
        yield session


@pytest.fixture
def stored_user(auth_session, passwords):
    read = Permission(code="test.read", description="Synthetic read permission")
    write = Permission(code="test.write", description="Synthetic write permission")
    reader = Role(code="TEST_READER", name="Synthetic reader", permissions=[read])
    writer = Role(code="TEST_WRITER", name="Synthetic writer", permissions=[read, write])
    user = User(username=" Synthetic.User ", password_hash=passwords.hash(" synthetic password "), roles=[reader, writer])
    auth_session.add(user)
    auth_session.flush()
    return user


@pytest.fixture
def auth_client(postgres_settings, database_connection):
    application = create_app(postgres_settings)
    factory = sessionmaker(bind=database_connection, join_transaction_mode="create_savepoint", expire_on_commit=False)

    def database_dependency():
        with session_scope(factory) as session:
            yield session

    application.dependency_overrides[get_db] = database_dependency

    @application.get("/_test/both", dependencies=[Depends(require_permissions("test.read", "test.write"))])
    def protected():
        return {"allowed": True}

    @application.get("/_test/unknown", dependencies=[Depends(require_permissions("test.unknown"))])
    def unknown():
        return {"allowed": True}

    with TestClient(application) as client:
        yield client


def login_header(client):
    response = client.post("/api/v1/auth/login", json={"username": " SYNTHETIC.USER ", "password": " synthetic password "})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_real_login_current_user_and_permission_union(auth_client, stored_user):
    header = login_header(auth_client)
    response = auth_client.get("/api/v1/auth/me", headers=header)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(stored_user.id), "username": "synthetic.user",
        "roles": ["TEST_READER", "TEST_WRITER"], "permissions": ["test.read", "test.write"],
    }
    assert stored_user.password_hash not in response.text
    assert auth_client.get("/_test/both", headers=header).status_code == 200
    assert auth_client.get("/_test/unknown", headers=header).status_code == 403
    assert auth_client.get("/_test/both").status_code == 401
    assert stored_user.created_at.utcoffset().total_seconds() == 0
    assert stored_user.updated_at.utcoffset().total_seconds() == 0


def test_database_grant_removal_takes_effect_with_existing_token(auth_client, stored_user, auth_session):
    header = login_header(auth_client)
    assert auth_client.get("/_test/both", headers=header).status_code == 200
    writer = next(role for role in stored_user.roles if role.code == "TEST_WRITER")
    writer.permissions = [permission for permission in writer.permissions if permission.code != "test.write"]
    auth_session.flush()
    assert auth_client.get("/_test/both", headers=header).status_code == 403
    assert auth_client.get("/api/v1/auth/me", headers=header).json()["permissions"] == ["test.read"]


def test_database_role_removal_takes_effect_with_existing_token(auth_client, stored_user, auth_session):
    header = login_header(auth_client)
    stored_user.roles = []
    auth_session.flush()
    response = auth_client.get("/api/v1/auth/me", headers=header)
    assert response.status_code == 200
    assert response.json()["roles"] == []
    assert response.json()["permissions"] == []
    assert auth_client.get("/_test/both", headers=header).status_code == 403


def test_database_deactivation_blocks_login_and_existing_token(auth_client, stored_user, auth_session):
    header = login_header(auth_client)
    stored_user.is_active = False
    auth_session.flush()
    assert auth_client.get("/api/v1/auth/me", headers=header).status_code == 401
    assert auth_client.post("/api/v1/auth/login", json={"username": "synthetic.user", "password": " synthetic password "}).status_code == 401


def test_database_admin_category_has_no_implicit_grants(auth_client, stored_user, auth_session):
    stored_user.roles = [auth_session.scalar(select(Role).where(Role.code == "ADMIN"))]
    auth_session.flush()
    header = login_header(auth_client)
    assert auth_client.get("/api/v1/auth/me", headers=header).json()["permissions"] == []
    assert auth_client.get("/_test/both", headers=header).status_code == 403


@pytest.mark.parametrize("duplicate", ["username", "role", "permission", "user_role", "role_permission"])
def test_database_uniqueness_constraints(auth_session, stored_user, duplicate):
    with pytest.raises(IntegrityError):
        with auth_session.begin_nested():
            if duplicate == "username":
                auth_session.add(User(username=" SYNTHETIC.USER ", password_hash="synthetic-unused-hash"))
            elif duplicate == "role":
                auth_session.add(Role(code="ADMIN", name="Duplicate category"))
            elif duplicate == "permission":
                auth_session.add(Permission(code="test.read", description="Duplicate permission"))
            elif duplicate == "user_role":
                auth_session.execute(insert(user_roles).values(user_id=stored_user.id, role_id=stored_user.roles[0].id))
            else:
                role = stored_user.roles[0]
                auth_session.execute(insert(role_permissions).values(role_id=role.id, permission_id=role.permissions[0].id))
            auth_session.flush()


@pytest.mark.parametrize("association", ["user_role", "role_permission"])
def test_database_foreign_keys_reject_unknown_entities(auth_session, stored_user, association):
    with pytest.raises(IntegrityError):
        with auth_session.begin_nested():
            if association == "user_role":
                auth_session.execute(insert(user_roles).values(user_id=stored_user.id, role_id=uuid4()))
            else:
                auth_session.execute(insert(role_permissions).values(role_id=stored_user.roles[0].id, permission_id=uuid4()))


def test_database_rejects_unnormalized_direct_username(auth_session):
    with pytest.raises(IntegrityError):
        with auth_session.begin_nested():
            auth_session.execute(insert(User).values(id=uuid4(), username=" Unnormalized ", password_hash="synthetic-unused-hash"))
