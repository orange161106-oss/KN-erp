from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.audit import AuditLog
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.security.tokens import create_access_token
from app.services.inventory_masters import RESOURCES


@pytest.fixture
def masters_api(settings, passwords):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        grants = [Permission(code=f"masters.{resource.permission_name}.{action}", description="Synthetic grant") for resource in RESOURCES for action in ("read", "write")]
        role = Role(code="TEST_MASTERS", name="Synthetic master operator", permissions=grants)
        user = User(username="master_operator", password_hash=passwords.hash("synthetic password"), roles=[role])
        session.add(user)
        session.commit()
        application = create_app(settings)

        def database():
            with Session(engine, expire_on_commit=False, autoflush=False) as request_session:
                yield request_session

        application.dependency_overrides[get_db] = database
        headers = {"Authorization": "Bearer " + create_access_token(user.id, settings)}
        with TestClient(application) as client:
            yield client, session, user, headers
    engine.dispose()


def create(client, headers, resource, **data):
    response = client.post(f"/api/v1/masters/{resource}", headers=headers, json={"change_reason": "Synthetic setup", **data})
    assert response.status_code == 201, response.text
    return response.json()


def setup_mapping(client, headers):
    unit = create(client, headers, "units", code="kg", name="Kilogram")
    consumable = create(client, headers, "consumables", code="c-1", name="Synthetic material", unit_id=unit["id"])
    supplier = create(client, headers, "suppliers", code="s-1", name="Synthetic supplier")
    mapping = create(client, headers, "supplier-consumables", supplier_id=supplier["id"], consumable_id=consumable["id"])
    return unit, consumable, supplier, mapping


def status(client, headers, resource, record, active):
    return client.patch(f"/api/v1/masters/{resource}/{record['id']}/status", headers=headers,
                        json={"is_active": active, "change_reason": "Synthetic lifecycle change"})


@pytest.mark.parametrize("resource", ["units", "consumables", "suppliers", "supplier-consumables"])
def test_master_endpoints_require_authentication_and_explicit_permissions(masters_api, resource):
    client, session, user, headers = masters_api
    base = f"/api/v1/masters/{resource}"
    for method, url, data in (("GET", base, None), ("GET", base + "/" + str(uuid4()), None),
                              ("POST", base, {}), ("PATCH", base + "/" + str(uuid4()), {}),
                              ("PATCH", base + "/" + str(uuid4()) + "/status", {})):
        assert client.request(method, url, json=data).status_code == 401
    user.roles[0].permissions = []
    session.commit()
    for method, url in (("GET", base), ("POST", base), ("PATCH", base + "/" + str(uuid4()) + "/status")):
        assert client.request(method, url, headers=headers, json={}).status_code == 403
    user.roles[0].code = "ADMIN"
    session.commit()
    assert client.get(base, headers=headers).status_code == 403


def test_read_permission_does_not_allow_mutation(masters_api):
    client, session, user, headers = masters_api
    user.roles[0].permissions = [permission for permission in user.roles[0].permissions if permission.code == "masters.units.read"]
    session.commit()
    assert client.get("/api/v1/masters/units", headers=headers).status_code == 200
    assert client.post("/api/v1/masters/units", headers=headers, json={"code": "KG", "name": "Kilogram", "change_reason": "Test"}).status_code == 403
    assert client.get("/api/v1/masters/suppliers", headers=headers).status_code == 403


@pytest.mark.parametrize("resource", ["units", "consumables", "suppliers"])
def test_unique_normalized_codes_remain_reserved_after_inactivation(masters_api, resource):
    client, session, user, headers = masters_api
    data = {"code": " lower-case ", "name": "  Synthetic name  "}
    if resource == "consumables":
        data["unit_id"] = create(client, headers, "units", code="KG", name="Kilogram")["id"]
    record = create(client, headers, resource, **data)
    assert record["code"] == "LOWER-CASE"
    assert record["name"] == "Synthetic name"
    assert status(client, headers, resource, record, False).status_code == 200
    duplicate = client.post(f"/api/v1/masters/{resource}", headers=headers, json={**data, "code": "LOWER-CASE", "change_reason": "Duplicate"})
    assert duplicate.status_code == 409
    historical = client.get(f"/api/v1/masters/{resource}/{record['id']}", headers=headers)
    assert historical.status_code == 200 and historical.json()["is_active"] is False
    assert client.delete(f"/api/v1/masters/{resource}/{record['id']}", headers=headers).status_code == 405
    assert status(client, headers, resource, record, True).status_code == 200


@pytest.mark.parametrize("changes", [{"code": " "}, {"name": " "}, {"code": None}, {"name": None},
                                    {"is_active": False}, {"MOQ": "1.25"}, {"pack_size": "0.5"},
                                    {"order_multiple": "2.5"}, {"lead_time_days": 3}, {"msq": "12"},
                                    {"change_reason": " "}, {"name": 123}])
def test_reject_invalid_and_unapproved_master_fields(masters_api, changes):
    client, session, user, headers = masters_api
    payload = {"code": "KG", "name": "Kilogram", "change_reason": "Test", **changes}
    assert client.post("/api/v1/masters/units", headers=headers, json=payload).status_code == 422
    assert session.scalars(select(Unit)).all() == []
    assert session.scalars(select(AuditLog)).all() == []


@pytest.mark.parametrize("invalid", [{"unit_id": None}, {"unit_id": "bad-id"}, {"unit_id": str(uuid4())}])
def test_consumable_requires_known_unit(masters_api, invalid):
    client, session, user, headers = masters_api
    response = client.post("/api/v1/masters/consumables", headers=headers, json={"code": "C1", "name": "Consumable", "change_reason": "Test", **invalid})
    assert response.status_code == (409 if invalid["unit_id"] and invalid["unit_id"] != "bad-id" else 422)


def test_inactive_unit_blocks_new_consumable_and_reactivation(masters_api):
    client, session, user, headers = masters_api
    unit = create(client, headers, "units", code="KG", name="Kilogram")
    consumable = create(client, headers, "consumables", code="C1", name="Consumable", unit_id=unit["id"])
    assert status(client, headers, "units", unit, False).status_code == 409
    assert status(client, headers, "consumables", consumable, False).status_code == 200
    assert status(client, headers, "units", unit, False).status_code == 200
    assert status(client, headers, "consumables", consumable, True).status_code == 409
    assert client.post("/api/v1/masters/consumables", headers=headers, json={"code": "C2", "name": "Blocked", "unit_id": unit["id"], "change_reason": "Test"}).status_code == 409


def test_mapping_unique_pair_reference_rules_and_inactive_history(masters_api):
    client, session, user, headers = masters_api
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    base = "/api/v1/masters/supplier-consumables"
    payload = {"supplier_id": supplier["id"], "consumable_id": consumable["id"], "change_reason": "Test"}
    assert client.post(base, headers=headers, json=payload).status_code == 409
    assert client.post(base, headers=headers, json={**payload, "supplier_id": str(uuid4())}).status_code == 409
    assert client.post(base, headers=headers, json={**payload, "consumable_id": str(uuid4())}).status_code == 409
    assert status(client, headers, "supplier-consumables", mapping, False).status_code == 200
    assert client.post(base, headers=headers, json=payload).status_code == 409
    assert status(client, headers, "suppliers", supplier, False).status_code == 200
    assert status(client, headers, "supplier-consumables", mapping, True).status_code == 409
    assert client.get(base + "/" + mapping["id"], headers=headers).json()["supplier_id"] == supplier["id"]
    assert status(client, headers, "suppliers", supplier, True).status_code == 200
    assert status(client, headers, "supplier-consumables", mapping, True).status_code == 200
    session.expire_all()
    assert len(session.scalars(select(SupplierConsumable)).all()) == 1


def test_consumable_unit_change_requires_unmapped_record(masters_api):
    client, session, user, headers = masters_api
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    other = create(client, headers, "units", code="L", name="Litre")
    response = client.patch("/api/v1/masters/consumables/" + consumable["id"], headers=headers, json={"unit_id": other["id"], "change_reason": "Test"})
    assert response.status_code == 409 and response.json()["code"] == "UNIT_CHANGE_CONFLICT"


def test_update_mapping_duplicate_and_parent_validation(masters_api):
    client, session, user, headers = masters_api
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    second = create(client, headers, "consumables", code="C2", name="Second", unit_id=unit["id"])
    other = create(client, headers, "supplier-consumables", supplier_id=supplier["id"], consumable_id=second["id"])
    base = "/api/v1/masters/supplier-consumables/" + mapping["id"]
    assert client.patch(base, headers=headers, json={"consumable_id": second["id"], "change_reason": "Test"}).status_code == 409
    assert status(client, headers, "supplier-consumables", other, False).status_code == 200
    assert client.patch(base, headers=headers, json={"supplier_id": str(uuid4()), "change_reason": "Test"}).status_code == 409
    assert client.get(base, headers=headers).json()["consumable_id"] == consumable["id"]


def test_edit_status_audit_actor_snapshots_and_idempotency(masters_api):
    client, session, user, headers = masters_api
    unit = create(client, headers, "units", code="KG", name="Kilogram")
    assert client.patch("/api/v1/masters/units/" + unit["id"], headers=headers, json={"name": "Updated", "change_reason": "Correct label"}).status_code == 200
    assert status(client, headers, "units", unit, False).status_code == 200
    assert status(client, headers, "units", unit, False).status_code == 200
    events = session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.action)).all()
    assert len(events) == 3
    assert {event.action for event in events} == {"CREATE", "UPDATE", "DEACTIVATE"}
    update = next(event for event in events if event.action == "UPDATE")
    assert update.actor_id == user.id and update.reason == "Correct label"
    assert update.old_values["name"] == "Kilogram" and update.new_values["name"] == "Updated"
    assert "password_hash" not in str(update.new_values)


@pytest.mark.parametrize("operation", ["create", "update"])
def test_audit_failure_rolls_back_entire_mutation(masters_api, monkeypatch, operation):
    client, session, user, headers = masters_api
    record = create(client, headers, "units", code="KG", name="Kilogram") if operation == "update" else None
    def failed_audit(*args, **kwargs):
        raise SQLAlchemyError("synthetic diagnostic with confidential values")
    monkeypatch.setattr("app.services.inventory_masters.audit", failed_audit)
    if record:
        response = client.patch("/api/v1/masters/units/" + record["id"], headers=headers, json={"name": "Must roll back", "change_reason": "Test"})
    else:
        response = client.post("/api/v1/masters/units", headers=headers, json={"code": "KG", "name": "Kilogram", "change_reason": "Test"})
    assert response.status_code == 503 and "confidential" not in response.text
    session.expire_all()
    records = session.scalars(select(Unit)).all()
    assert len(records) == (1 if record else 0)
    if record:
        assert records[0].name == "Kilogram"
    assert len(session.scalars(select(AuditLog)).all()) == (1 if record else 0)


def test_pagination_literal_search_status_filters_and_missing_record(masters_api):
    client, session, user, headers = masters_api
    for code in ("A_1", "AX1", "B"):
        create(client, headers, "units", code=code, name=code)
    base = "/api/v1/masters/units"
    assert client.get(base + "?q=_", headers=headers).json()["total"] == 1
    page = client.get(base + "?limit=1&offset=1", headers=headers).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["items"][0]["code"] == "A_1"
    assert client.get(base + "?is_active=false", headers=headers).json()["total"] == 0
    assert client.get(base + "?limit=101", headers=headers).status_code == 422
    assert client.get(base + "/" + str(uuid4()), headers=headers).status_code == 404
    assert client.patch(base + "/" + str(uuid4()), headers=headers, json={"name": "Missing", "change_reason": "Test"}).status_code == 404


def test_unknown_quantity_constraints_are_rejected_for_supplier_mapping(masters_api):
    client, session, user, headers = masters_api
    unit, consumable, supplier, mapping = setup_mapping(client, headers)
    for field in ("moq", "MOQ", "pack_size", "order_multiple", "lead_time_days", "msq"):
        response = client.patch("/api/v1/masters/supplier-consumables/" + mapping["id"], headers=headers,
                                json={field: "0.1000", "change_reason": "Unapproved field"})
        assert response.status_code == 422
