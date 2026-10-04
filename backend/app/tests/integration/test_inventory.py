from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import BACKEND_ROOT
from app.core.errors import ApplicationError
from app.db.session import create_db_engine, get_db
from app.main import create_app
from app.models.audit import AuditLog
from app.models.auth import Permission, Role, User
from app.models.inventory import StockImportBatch, StockSnapshot, StockTransaction
from app.models.inventory_masters import Consumable, Unit
from app.schemas.inventory import SourceImport
from app.services.inventory import import_source
from app.tests.test_inventory import source_movement, source_payload

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_inventory(postgres_settings, passwords):
    # Committed, concurrent work requires a dedicated schema, not a shared savepoint.
    schema = "m41_test_" + uuid4().hex
    administration = create_db_engine(postgres_settings)
    with administration.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_db_engine(postgres_settings)
    @event.listens_for(engine, "connect")
    def isolate(connection, record):
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO " + schema)
        connection.commit()
    try:
        with engine.begin() as connection:
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        settings = postgres_settings.model_copy(update={"inventory_import_enabled": True})
        with Session(engine, expire_on_commit=False) as session:
            unit = Unit(code="KG", name="Synthetic kilogram")
            session.add(unit)
            session.flush()
            material = Consumable(code="SYNTHETIC-C1", name="Synthetic source material", unit_id=unit.id)
            grants = session.scalars(select(Permission).where(Permission.code.like("inventory.%"))).all()
            user = User(username="synthetic_inventory_operator", password_hash=passwords.hash("synthetic password"),
                        roles=[Role(code="TEST_STOCK", name="Synthetic test importer", permissions=grants)])
            session.add_all([material, user])
            session.commit()
            ids = {"unit_id": unit.id, "material_id": material.id, "actor_id": user.id}
        application = create_app(settings)
        def database():
            with Session(engine, expire_on_commit=False, autoflush=False) as session:
                yield session
        application.dependency_overrides[get_db] = database
        with TestClient(application) as client:
            login = client.post("/api/v1/auth/login", json={"username": "synthetic_inventory_operator", "password": "synthetic password"})
            assert login.status_code == 200
            yield engine, client, {"Authorization": "Bearer " + login.json()["access_token"]}, ids
    finally:
        engine.dispose()
        try:
            with administration.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        finally:
            administration.dispose()


def data_for(ids, export_id="source-1"):
    data = source_payload(ids["material_id"], ids["unit_id"], export_id=export_id, quantity="100.1234")
    data["movements"] = [source_movement(ids["material_id"], ids["unit_id"], quantity="0.1001")]
    return data


def counts(engine):
    with Session(engine) as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (StockImportBatch, StockTransaction, StockSnapshot, AuditLog))


def test_postgres_source_import_api_decimal_utc_and_no_double_count(postgres_inventory):
    engine, client, headers, ids = postgres_inventory
    response = client.post("/api/v1/inventory/imports", headers=headers, json=data_for(ids))
    assert response.status_code == 201, response.text
    assert response.json()["imported_at"].endswith("Z")
    balance = client.get("/api/v1/inventory/balances/" + str(ids["material_id"]), headers=headers).json()
    assert balance["usable_quantity"] == "100.1234" and balance["as_of"].endswith("Z")
    assert balance["is_live"] is False
    entry = client.get("/api/v1/inventory/transactions", headers=headers).json()["items"][0]
    assert entry["quantity"] == "0.1001" and entry["event_at"].endswith("Z")
    with Session(engine) as session:
        row = session.scalar(select(StockTransaction))
        assert str(row.quantity) == "0.1001" and row.event_at.utcoffset().total_seconds() == 0
    assert counts(engine) == (1, 1, 1, 1)


@pytest.mark.parametrize("table", ["stock_import_batches", "stock_transactions", "stock_snapshots"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_postgres_history_is_append_only_even_for_direct_sql(postgres_inventory, table, operation):
    engine, client, headers, ids = postgres_inventory
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data_for(ids)).status_code == 201
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as connection:
            statement = f"UPDATE {table} SET id=id" if operation == "UPDATE" else f"DELETE FROM {table}"
            connection.execute(text(statement))
    assert error.value.orig.sqlstate == "55000"
    assert counts(engine) == (1, 1, 1, 1)


@pytest.mark.parametrize("case", ["same_export", "same_events", "conflicting_event"])
def test_concurrent_source_imports_do_not_duplicate_or_overwrite_stock(postgres_inventory, case):
    engine, client, headers, ids = postgres_inventory
    first = data_for(ids)
    second = data_for(ids, "source-2" if case != "same_export" else "source-1")
    # Different exports may include the same unchanged source snapshot and event.
    second["snapshots"][0]["source_snapshot_id"] = first["snapshots"][0]["source_snapshot_id"]
    if case == "conflicting_event":
        second["movements"][0]["source_quantity"] = "2.0000"
    barrier = Barrier(2)
    def worker(payload):
        with Session(engine, expire_on_commit=False, autoflush=False) as session:
            barrier.wait(timeout=10)
            try:
                imported = import_source(session, SourceImport.model_validate(payload), ids["actor_id"], enabled=True)
                return "replay" if imported.replayed else "imported"
            except ApplicationError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(worker, item) for item in (first, second)]
        results = [future.result(timeout=20) for future in futures]
    if case == "same_export":
        assert sorted(results) == ["imported", "replay"]
        assert counts(engine) == (1, 1, 1, 1)
    elif case == "same_events":
        assert results == ["imported", "imported"]
        assert counts(engine) == (2, 1, 1, 2)
    else:
        assert sorted(results) == ["SOURCE_CONFLICT", "imported"]
        assert counts(engine) == (1, 1, 1, 1)


def test_concurrent_older_snapshot_cannot_replace_latest_source_balance(postgres_inventory):
    engine, client, headers, ids = postgres_inventory
    older = source_payload(ids["material_id"], ids["unit_id"], export_id="older", as_of="2020-01-01T00:00:00Z", quantity="20")
    newer = source_payload(ids["material_id"], ids["unit_id"], export_id="newer", quantity="90.0001")
    barrier = Barrier(2)
    def worker(payload):
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            return import_source(session, SourceImport.model_validate(payload), ids["actor_id"], enabled=True)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(worker, payload) for payload in (newer, older)]
        [future.result(timeout=20) for future in futures]
    assert client.get("/api/v1/inventory/balances/" + str(ids["material_id"]), headers=headers).json()["usable_quantity"] == "90.0001"


def test_failed_conversion_rolls_back_snapshot_and_batch_on_postgres(postgres_inventory):
    engine, client, headers, ids = postgres_inventory
    with Session(engine) as session:
        other = Unit(code="SOURCE", name="Synthetic source unit")
        session.add(other)
        session.commit()
        other_id = other.id
    data = data_for(ids)
    data["movements"][0].update(source_unit_id=str(other_id), source_quantity="0.0001", conversion_factor="0.5", conversion_reference="synthetic-factor")
    response = client.post("/api/v1/inventory/imports", headers=headers, json=data)
    assert response.status_code == 422 and response.json()["code"] == "INVALID_CONVERSION"
    assert counts(engine) == (0, 0, 0, 0)
