from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.inventory_engine.ledger import Movement, signed_change, stock_quantity
from app.models.audit import AuditLog
from app.models.auth import Permission
from app.models.inventory import StockImportBatch, StockSnapshot, StockTransaction
from app.schemas.inventory import SourceImport
from app.tests.test_inventory_masters import create, masters_api


def source_payload(material_id, unit_id, *, export_id="source-export-1", as_of="2020-01-02T12:00:00Z", quantity="12.3456"):
    return {"export_id": export_id, "generated_at": "2020-01-03T12:00:00Z", "import_reason": "Synthetic source validation",
            "snapshots": [{"source_snapshot_id": export_id + ":stock", "consumable_id": str(material_id),
                           "unit_id": str(unit_id), "usable_quantity": quantity, "as_of": as_of,
                           "nonusable_excluded": True, "reservations_excluded": True}], "movements": []}


def source_movement(material_id, unit_id, *, key="event-1", movement="RECEIPT", quantity="2.0001"):
    return {"source_event_id": key, "consumable_id": str(material_id), "unit_id": str(unit_id),
            "source_unit_id": str(unit_id), "source_quantity": quantity, "movement": movement,
            "event_at": "2020-01-01T12:00:00Z", "source_actor": "synthetic-source-operator",
            "condition": "USABLE", "source_status": "POSTED"}


@pytest.fixture
def inventory_api(masters_api):
    client, session, user, headers = masters_api
    user.roles[0].permissions.extend([Permission(code="inventory.stock.read", description="Synthetic stock reader"), Permission(code="inventory.stock.import", description="Synthetic source importer")])
    session.commit()
    client.app.state.settings.inventory_import_enabled = True
    unit = create(client, headers, "units", code="KG", name="Kilogram")
    material = create(client, headers, "consumables", code="C1", name="Synthetic material", unit_id=unit["id"])
    return client, session, user, headers, material, unit


@pytest.mark.parametrize("movement,expected", [(Movement.RECEIPT, "1.0001"), (Movement.ISSUE, "-1.0001"), (Movement.RETURN, "1.0001")])
def test_exact_confirmed_direction(movement, expected):
    assert signed_change(movement, Decimal("1.0001")) == Decimal(expected)


def test_decimal_conversion_and_rejection_of_unapproved_rounding():
    assert stock_quantity(Decimal("0.1"), Decimal("3")) == Decimal("0.3000")
    assert stock_quantity(Decimal("2.0000"), Decimal("25.125")) == Decimal("50.2500")
    for quantity, factor in (("0.0001", "0.5"), ("99999999999999.9999", "2")):
        with pytest.raises(ApplicationError, match="exact positive"):
            stock_quantity(Decimal(quantity), Decimal(factor))


@pytest.mark.parametrize("quantity", ["-1", "NaN", "Infinity", "0.00001", "100000000000000", 0.1, True])
def test_invalid_snapshot_decimal_is_rejected_without_rounding(quantity):
    data = source_payload(uuid4(), uuid4(), quantity=quantity)
    with pytest.raises(ValidationError):
        SourceImport.model_validate(data)


@pytest.mark.parametrize("change", [{"condition": "DAMAGED"}, {"source_status": "PENDING"}, {"movement": "PO"},
                                   {"movement": "OPENING"}, {"movement": "ADJUSTMENT"}, {"source_quantity": "0"},
                                   {"source_actor": " "}, {"event_at": "2020-01-01T12:00:00"}])
def test_unsupported_source_movements_are_rejected(change):
    data = source_payload(uuid4(), uuid4())
    data["movements"] = [{**source_movement(data["snapshots"][0]["consumable_id"], data["snapshots"][0]["unit_id"]), **change}]
    with pytest.raises(ValidationError):
        SourceImport.model_validate(data)


@pytest.mark.parametrize("field,value", [("nonusable_excluded", False), ("reservations_excluded", False),
                                         ("nonusable_excluded", "true"), ("reservations_excluded", 1)])
def test_usable_balance_requires_explicit_source_exclusions(field, value):
    data = source_payload(uuid4(), uuid4())
    data["snapshots"][0][field] = value
    with pytest.raises(ValidationError):
        SourceImport.model_validate(data)


def test_source_structure_duplicate_ids_unknown_fields_and_future_records():
    data = source_payload(uuid4(), uuid4())
    for changed in ({**data, "opening_stock": "10"}, {**data, "snapshots": data["snapshots"] * 2},
                    {**data, "movements": [], "snapshots": []},
                    {**data, "generated_at": "2019-01-01T00:00:00Z"}):
        with pytest.raises(ValidationError):
            SourceImport.model_validate(changed)


def test_authentication_permissions_and_no_admin_bypass(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    assert client.get("/api/v1/inventory/status").status_code == 401
    user.roles[0].code = "ADMIN"
    user.roles[0].permissions = []
    session.commit()
    assert client.get("/api/v1/inventory/balances", headers=headers).status_code == 403
    assert client.post("/api/v1/inventory/imports", headers=headers, json=source_payload(material["id"], unit["id"])).status_code == 403


def test_read_permission_and_disabled_import_gate(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    client.app.state.settings.inventory_import_enabled = False
    assert client.get("/api/v1/inventory/status", headers=headers).json()["import_enabled"] is False
    response = client.post("/api/v1/inventory/imports", headers=headers, json=source_payload(material["id"], unit["id"]))
    assert response.status_code == 409 and response.json()["code"] == "INVENTORY_IMPORT_DISABLED"
    assert session.scalar(select(func.count()).select_from(StockImportBatch)) == 0
    user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code == "inventory.stock.read"]
    session.commit()
    assert client.get("/api/v1/inventory/balances", headers=headers).status_code == 200
    assert client.post("/api/v1/inventory/imports", headers=headers, json=source_payload(material["id"], unit["id"])).status_code == 403


def test_atomic_import_replay_and_conflict(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    data = source_payload(material["id"], unit["id"])
    data["movements"] = [source_movement(material["id"], unit["id"])]
    first = client.post("/api/v1/inventory/imports", headers=headers, json=data)
    assert first.status_code == 201, first.text
    assert first.json()["movement_count"] == first.json()["snapshot_count"] == 1
    repeated = client.post("/api/v1/inventory/imports", headers=headers, json=data)
    assert repeated.status_code == 200 and repeated.json()["replayed"] is True
    assert repeated.json()["id"] == first.json()["id"]
    audit = session.scalars(select(AuditLog).where(AuditLog.entity_type == "stock_import_batches")).all()
    assert len(audit) == 1 and audit[0].actor_id == user.id
    assert audit[0].new_values["movement_count"] == 1
    changed = deepcopy(data)
    changed["snapshots"][0]["usable_quantity"] = "999"
    assert client.post("/api/v1/inventory/imports", headers=headers, json=changed).status_code == 409
    assert session.scalar(select(func.count()).select_from(StockSnapshot)) == 1


def test_balances_are_source_snapshots_not_partial_history_totals(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    empty = client.get("/api/v1/inventory/balances/" + material["id"], headers=headers).json()
    assert empty["availability"] == "NOT_IMPORTED" and empty["usable_quantity"] is None
    data = source_payload(material["id"], unit["id"], quantity="100.1234")
    data["movements"] = [source_movement(material["id"], unit["id"], movement="ISSUE", quantity="9")]
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 201
    old = source_payload(material["id"], unit["id"], export_id="older-export", as_of="2020-01-01T00:00:00Z", quantity="1")
    assert client.post("/api/v1/inventory/imports", headers=headers, json=old).status_code == 201
    balance = client.get("/api/v1/inventory/balances/" + material["id"], headers=headers).json()
    assert balance["usable_quantity"] == "100.1234" and balance["is_live"] is False
    assert balance["source_export_id"] == data["export_id"]
    assert client.get("/api/v1/inventory/balances/" + str(uuid4()), headers=headers).status_code == 404


def test_history_precision_conversion_and_source_actor(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    box = create(client, headers, "units", code="BOX", name="Box")
    data = source_payload(material["id"], unit["id"])
    data["movements"] = [source_movement(material["id"], unit["id"], key=kind, movement=kind) for kind in ("RECEIPT", "ISSUE", "RETURN")]
    data["movements"][0].update(source_unit_id=box["id"], source_quantity="2", conversion_factor="25.125", conversion_reference="synthetic-approved-factor")
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 201
    rows = client.get("/api/v1/inventory/transactions", headers=headers).json()["items"]
    receipt = next(row for row in rows if row["movement"] == "RECEIPT")
    assert receipt["quantity"] == "50.2500" and receipt["source_unit_code"] == "BOX"
    assert receipt["source_actor"] == "synthetic-source-operator" and receipt["imported_by"] == str(user.id)
    assert next(row for row in rows if row["movement"] == "ISSUE")["signed_quantity"] == "-2.0001"
    filtered = client.get("/api/v1/inventory/transactions?movement=RETURN&limit=1", headers=headers).json()
    assert filtered["total"] == 1 and filtered["items"][0]["signed_quantity"] == "2.0001"
    assert client.get("/api/v1/inventory/transactions?since=2020-01-04T00:00:00Z&until=2020-01-01T00:00:00Z", headers=headers).status_code == 422
    assert client.get("/api/v1/inventory/transactions?since=2020-01-01T00:00:00", headers=headers).status_code == 422


def test_invalid_reference_or_conversion_rolls_back_whole_batch(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    data = source_payload(material["id"], unit["id"])
    data["movements"] = [source_movement(uuid4(), unit["id"])]
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 409
    data["movements"] = [source_movement(material["id"], unit["id"])]
    data["movements"][0]["source_unit_id"] = str(uuid4())
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 422
    data["movements"][0].update(conversion_factor="1", conversion_reference="synthetic-factor")
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 409
    assert session.scalar(select(func.count()).select_from(StockImportBatch)) == 0
    future = source_payload(material["id"], unit["id"])
    future["generated_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/api/v1/inventory/imports", headers=headers, json=future).status_code == 422


def test_source_identity_and_snapshot_timestamp_conflicts_preserve_records(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    data = source_payload(material["id"], unit["id"])
    data["movements"] = [source_movement(material["id"], unit["id"])]
    assert client.post("/api/v1/inventory/imports", headers=headers, json=data).status_code == 201
    changed = deepcopy(data)
    changed["export_id"] = "second-export"
    changed["movements"][0]["source_quantity"] = "3"
    assert client.post("/api/v1/inventory/imports", headers=headers, json=changed).status_code == 409
    changed["movements"] = []
    changed["snapshots"][0]["source_snapshot_id"] = "different-id-same-timestamp"
    assert client.post("/api/v1/inventory/imports", headers=headers, json=changed).status_code == 409
    assert session.scalar(select(func.count()).select_from(StockImportBatch)) == 1


def test_audit_failure_rolls_back_and_hides_diagnostics(inventory_api, monkeypatch):
    client, session, user, headers, material, unit = inventory_api
    from app.services import inventory
    def fail_audit(**values):
        raise SQLAlchemyError("private-driver-detail")
    monkeypatch.setattr(inventory, "AuditLog", fail_audit)
    response = client.post("/api/v1/inventory/imports", headers=headers, json=source_payload(material["id"], unit["id"]))
    assert response.status_code == 503 and "private-driver-detail" not in response.text
    assert session.scalar(select(func.count()).select_from(StockSnapshot)) == 0
    assert session.scalar(select(func.count()).select_from(StockImportBatch)) == 0


def test_history_freezes_stock_unit_and_exposes_no_local_mutations(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    assert client.post("/api/v1/inventory/imports", headers=headers, json=source_payload(material["id"], unit["id"])).status_code == 201
    other = create(client, headers, "units", code="PCS", name="Pieces")
    response = client.patch("/api/v1/masters/consumables/" + material["id"], headers=headers,
                            json={"unit_id": other["id"], "change_reason": "Synthetic invalid unit change"})
    assert response.status_code == 409 and response.json()["code"] == "UNIT_CHANGE_CONFLICT"
    for method, path in (("POST", "/transactions"), ("PATCH", "/transactions"), ("DELETE", "/transactions"), ("POST", "/balances")):
        assert client.request(method, "/api/v1/inventory" + path, headers=headers, json={}).status_code == 405
    assert client.get("/api/v1/inventory/balances?q=%25", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/inventory/balances?limit=101", headers=headers).status_code == 422
