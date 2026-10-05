from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.audit import AuditLog
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.tests.test_inventory_masters import create, setup_mapping, status

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_masters(postgres_engine, postgres_settings, passwords):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                grants = session.scalars(select(Permission).where(Permission.code.like("masters.%"))).all()
                user = User(username="postgres_master_operator", password_hash=passwords.hash("synthetic password"),
                            roles=[Role(code="TEST_PG_MASTERS", name="Synthetic PostgreSQL writer", permissions=grants)])
                session.add(user)
                session.flush()
                app = create_app(postgres_settings)
                def database():
                    with Session(connection, expire_on_commit=False, autoflush=False, join_transaction_mode="create_savepoint") as request_session:
                        yield request_session
                app.dependency_overrides[get_db] = database
                with TestClient(app) as client:
                    login = client.post("/api/v1/auth/login", json={"username": user.username, "password": "synthetic password"})
                    assert login.status_code == 200
                    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                    yield client, session, user, headers
        finally:
            if transaction.is_active:
                transaction.rollback()


def test_postgres_login_master_flow_audit_utc_and_live_permission_removal(postgres_masters):
    client, session, user, headers = postgres_masters
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    assert status(client, headers, "suppliers", supplier, False).status_code == 200
    history = client.get("/api/v1/masters/supplier-consumables?is_active=true&supplier_id=" + supplier["id"], headers=headers)
    assert history.status_code == 200 and history.json()["total"] == 1
    events = session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()
    assert len(events) == 5
    assert all(event.actor_id == user.id and event.created_at.utcoffset().total_seconds() == 0 for event in events)
    assert events[-1].old_values["is_active"] is True and events[-1].new_values["is_active"] is False
    assert client.get("/api/v1/masters/units/" + unit["id"], headers=headers).json()["created_at"].endswith("Z")
    user.roles[0].permissions = [permission for permission in user.roles[0].permissions if permission.code != "masters.units.write"]
    session.flush()
    assert client.patch("/api/v1/masters/units/" + unit["id"], headers=headers, json={"name": "Denied", "change_reason": "Test"}).status_code == 403


@pytest.mark.parametrize("case", ["duplicate_code", "unnormalized_code", "unknown_unit", "unknown_supplier", "duplicate_pair", "restricted_delete"])
def test_postgres_master_constraints_protect_direct_writes(postgres_masters, case):
    client, session, user, headers = postgres_masters
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            if case == "duplicate_code":
                session.add(Unit(code="KG", name="Duplicate"))
            elif case == "unnormalized_code":
                session.execute(insert(Unit).values(id=uuid4(), code=" kg ", name="Unnormalized"))
            elif case == "unknown_unit":
                session.add(Consumable(code="BAD", name="Bad", unit_id=uuid4()))
            elif case == "unknown_supplier":
                session.add(SupplierConsumable(supplier_id=uuid4(), consumable_id=UUID(consumable["id"])))
            elif case == "duplicate_pair":
                session.add(SupplierConsumable(supplier_id=UUID(supplier["id"]), consumable_id=UUID(consumable["id"])))
            else:
                session.delete(session.get(Supplier, UUID(supplier["id"])))
            session.flush()
