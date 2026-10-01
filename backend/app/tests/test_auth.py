from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends
from sqlalchemy.exc import OperationalError

from app.models.auth import Permission, Role, User
from app.schemas.auth import CurrentUser
from app.security.permissions import require_permissions
from app.security.tokens import create_access_token


@pytest.fixture
def auth_user(passwords):
    read = Permission(id=uuid4(), code="test.read", description="Synthetic test permission")
    role = Role(id=uuid4(), code="TEST_READER", name="Synthetic role", permissions=[read])
    return User(id=uuid4(), username="tester", password_hash=passwords.hash(" synthetic password "), is_active=True, roles=[role])


@pytest.fixture
def auth_repository(monkeypatch, auth_user):
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda session, username: auth_user if username == auth_user.username else None)
    monkeypatch.setattr("app.services.auth.find_user_with_permissions", lambda session, user_id: auth_user if user_id == auth_user.id else None)


@pytest.fixture
def protected_routes(app):
    @app.get("/_test/read", dependencies=[Depends(require_permissions("test.read"))])
    def read():
        return {"allowed": True}

    @app.get("/_test/both", dependencies=[Depends(require_permissions("test.read", "test.write"))])
    def both():
        return {"allowed": True}


def bearer_header(user, settings):
    return {"Authorization": "Bearer " + create_access_token(user.id, settings)}


def test_login_and_current_user_contract(client, auth_repository, auth_user):
    response = client.post("/api/v1/auth/login", json={"username": " TESTER ", "password": " synthetic password "})
    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 900
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + response.json()["access_token"]})
    assert me.status_code == 200
    assert me.json() == {"id": str(auth_user.id), "username": "tester", "roles": ["TEST_READER"], "permissions": ["test.read"]}
    assert "password_hash" not in me.text
    assert auth_user.password_hash not in response.text + me.text
    assert me.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("username,password,inactive", [
    ("tester", "wrong", False), ("unknown", "wrong", False),
    ("tester", " synthetic password ", True),
])
def test_login_failures_have_identical_generic_response(client, auth_repository, auth_user, username, password, inactive):
    auth_user.is_active = not inactive
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json() == {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password.", "details": {}}
    assert response.headers["www-authenticate"] == "Bearer"


def test_unknown_user_verifies_dummy_hash(client, app, monkeypatch):
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda *_: None)
    calls = []
    monkeypatch.setattr(app.state.passwords, "verify_dummy", calls.append)
    assert client.post("/api/v1/auth/login", json={"username": "unknown", "password": "test password"}).status_code == 401
    assert calls == ["test password"]


@pytest.mark.parametrize("payload", [
    {"username": "tester", "password": ""},
    {"username": " ", "password": "sensitive-value"},
    {"username": "tester", "password": "sensitive-value", "roles": ["ADMIN"]},
    {"username": "tester", "password": 12345},
    {"username": "tester"},
])
def test_login_input_validation_omits_credentials(client, payload):
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "sensitive-value" not in response.text
    assert "12345" not in response.text


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer malformed", "Bearer"])
def test_missing_or_malformed_authentication_is_401(client, header):
    response = client.get("/api/v1/auth/me", headers={"Authorization": header} if header else {})
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("mutation", [
    "expired", "future", "issuer", "audience", "subject", "type",
    "missing_exp", "missing_iat", "missing_iss", "missing_aud", "missing_sub", "missing_type",
    "signature", "algorithm", "unsigned", "tampered",
])
def test_invalid_tokens_fail_closed(client, auth_repository, auth_user, settings, mutation):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(auth_user.id), "iat": now, "exp": now + timedelta(minutes=15),
              "iss": settings.auth_token_issuer, "aud": settings.auth_token_audience, "token_type": "access"}
    key = settings.signing_key()
    algorithm = "HS256"
    if mutation == "expired":
        claims.update(iat=now - timedelta(minutes=30), exp=now - timedelta(minutes=1))
    elif mutation == "future":
        claims["iat"] = now + timedelta(minutes=1)
    elif mutation == "issuer":
        claims["iss"] = "incorrect"
    elif mutation == "audience":
        claims["aud"] = "incorrect"
    elif mutation == "subject":
        claims["sub"] = "invalid-user-id"
    elif mutation == "type":
        claims["token_type"] = "refresh"
    elif mutation.startswith("missing_"):
        claims.pop("token_type" if mutation == "missing_type" else mutation.removeprefix("missing_"))
    elif mutation == "signature":
        key = "different-synthetic-signing-key-0000000000"
    elif mutation == "algorithm":
        algorithm = "HS384"
    elif mutation == "unsigned":
        algorithm, key = "none", None
    token = jwt.encode(claims, key, algorithm=algorithm)
    if mutation == "tampered":
        header, payload, signature = token.split(".")
        token = header + "." + ("A" if payload[0] != "A" else "B") + payload[1:] + "." + signature
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"
    assert token not in response.text


@pytest.mark.parametrize("missing", [False, True])
def test_valid_token_rejects_inactive_or_missing_user(client, auth_repository, auth_user, settings, monkeypatch, missing):
    header = bearer_header(auth_user, settings)
    if missing:
        monkeypatch.setattr("app.services.auth.find_user_with_permissions", lambda *_: None)
    else:
        auth_user.is_active = False
    assert client.get("/api/v1/auth/me", headers=header).status_code == 401


def test_permission_allow_deny_and_no_admin_bypass(client, protected_routes, auth_repository, auth_user, settings):
    header = bearer_header(auth_user, settings)
    assert client.get("/_test/read").status_code == 401
    assert client.get("/_test/read", headers=header).status_code == 200
    denied = client.get("/_test/both", headers=header)
    assert denied.status_code == 403
    assert denied.json() == {"code": "PERMISSION_DENIED", "message": "Required permission is missing.", "details": {}}
    auth_user.roles = [Role(id=uuid4(), code="ADMIN", name="ADMIN", permissions=[])]
    assert client.get("/_test/read", headers=header).status_code == 403


def test_multiple_roles_union_and_permission_removal(client, protected_routes, auth_repository, auth_user, settings):
    header = bearer_header(auth_user, settings)
    read = auth_user.roles[0].permissions[0]
    write = Permission(id=uuid4(), code="test.write", description="Synthetic write")
    auth_user.roles.append(Role(id=uuid4(), code="TEST_WRITER", name="Synthetic", permissions=[read, write]))
    assert client.get("/_test/both", headers=header).status_code == 200
    assert client.get("/api/v1/auth/me", headers=header).json()["permissions"] == ["test.read", "test.write"]
    auth_user.roles[1].permissions.remove(write)
    assert client.get("/_test/both", headers=header).status_code == 403


def test_token_embedded_grants_are_not_authority(client, protected_routes, auth_repository, auth_user, settings):
    claims = jwt.decode(create_access_token(auth_user.id, settings), settings.signing_key(), algorithms=["HS256"], audience=settings.auth_token_audience)
    assert set(claims) == {"sub", "iat", "exp", "iss", "aud", "token_type"}
    claims.update(roles=["ADMIN"], permissions=["test.write"])
    token = jwt.encode(claims, settings.signing_key(), algorithm="HS256")
    assert client.get("/_test/both", headers={"Authorization": "Bearer " + token}).status_code == 403


@pytest.mark.parametrize("path", ["login", "me"])
def test_auth_database_failures_are_sanitized(client, auth_user, settings, monkeypatch, path):
    def failure(*_):
        raise OperationalError("private query", {}, Exception("private-password"))

    monkeypatch.setattr("app.services.auth.find_user_by_username", failure)
    monkeypatch.setattr("app.services.auth.find_user_with_permissions", failure)
    if path == "login":
        response = client.post("/api/v1/auth/login", json={"username": "tester", "password": "not exposed"})
    else:
        response = client.get("/api/v1/auth/me", headers=bearer_header(auth_user, settings))
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "private-password" not in response.text


@pytest.mark.parametrize("codes", [(), ("",), (" test.read",)])
def test_empty_or_ambiguous_permission_configuration_is_rejected(codes):
    with pytest.raises(ValueError):
        require_permissions(*codes)


def test_auth_openapi_contract(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/auth/login"]["post"]["requestBody"]["content"].keys() == {"application/json"}
    assert schema["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "password_hash" not in schema["components"]["schemas"]["CurrentUser"]["properties"]
