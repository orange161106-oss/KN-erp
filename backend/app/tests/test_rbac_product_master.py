from uuid import uuid4
from fastapi.testclient import TestClient
import pytest
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


def test_standard_user_forbidden_on_destructive_endpoints_but_allowed_on_get(db_session, client):
    settings = app.state.settings

    # 1. Create standard USER
    user_role = Role(code="USER", name="Standard User")
    db_session.add(user_role)
    standard_user = User(
        username="standard_worker",
        password_hash="secret",
        is_super_admin=False,
        roles=[user_role],
        masters_read=True,
    )
    db_session.add(standard_user)
    db_session.commit()

    token = create_access_token(standard_user.id, settings)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify GET /consumables is allowed (200 OK)
    get_res = client.get("/api/v1/masters/product-master/consumables", headers=headers)
    assert get_res.status_code == 200

    # 3. Verify POST /consumables/single is forbidden (403 Forbidden)
    post_res = client.post(
        "/api/v1/masters/product-master/consumables/single",
        headers=headers,
        json={
            "item_id": "CS-999",
            "description": "Test Consumable",
            "category": "RAW",
            "type_of_material": "STEEL",
            "supplier_name": "Supplier X",
            "output_unit": "KG",
            "rate": "100.00",
        },
    )
    assert post_res.status_code == 403
    assert "Admin role required" in post_res.json()["message"]

    # 4. Verify PUT /consumables/{id} is forbidden (403 Forbidden)
    random_id = str(uuid4())
    put_res = client.put(
        f"/api/v1/masters/product-master/consumables/{random_id}",
        headers=headers,
        json={"description": "Hacked"},
    )
    assert put_res.status_code == 403

    # 5. Verify PATCH /consumables/{id}/deactivate is forbidden (403 Forbidden)
    patch_res = client.patch(
        f"/api/v1/masters/product-master/consumables/{random_id}/deactivate",
        headers=headers,
    )
    assert patch_res.status_code == 403

    # 6. Verify DELETE /consumables/{id} is forbidden (403 Forbidden)
    del_res = client.delete(
        f"/api/v1/masters/product-master/consumables/{random_id}",
        headers=headers,
    )
    assert del_res.status_code == 403


def test_admin_user_allowed_on_destructive_endpoints(db_session, client):
    settings = app.state.settings

    # Create ADMIN user
    admin_role = Role(code="ADMIN", name="Administrator")
    db_session.add(admin_role)
    admin_user = User(
        username="lead_admin",
        password_hash="secret",
        is_super_admin=False,
        roles=[admin_role],
        masters_read=True,
        masters_create=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    token = create_access_token(admin_user.id, settings)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify POST /consumables/single succeeds (201 Created)
    post_res = client.post(
        "/api/v1/masters/product-master/consumables/single",
        headers=headers,
        json={
            "item_id": "CS-ADMIN-01",
            "description": "Admin Created Consumable",
            "category": "RAW",
            "type_of_material": "STEEL",
            "supplier_name": "Supplier X",
            "output_unit": "KG",
            "rate": "100.00",
        },
    )
    assert post_res.status_code == 201
    created_id = post_res.json()["id"]

    # Verify PUT succeeds
    put_res = client.put(
        f"/api/v1/masters/product-master/consumables/{created_id}",
        headers=headers,
        json={"description": "Admin Updated"},
    )
    assert put_res.status_code == 200

    # Verify PATCH deactivate succeeds
    patch_res = client.patch(
        f"/api/v1/masters/product-master/consumables/{created_id}/deactivate",
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False
