"""Period-scoped parameter deletion uses only an isolated SQLite database."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.stock_statements import StockParameterBatch, StockParameter
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import StockParameterDeleteRequest
from app.security.dependencies import get_current_user
from app.services import stock_management_service as service


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else "")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        user = User(id=uuid4(), username="delete_operator", password_hash="unused-test-credential")
        session.add(user)
        session.commit()
        yield session
    engine.dispose()


def identity(db, **flags):
    user = db.scalar(select(User))
    return CurrentUser(id=user.id, username=user.username, roles=[], permissions=[], **flags)


def seed(db, month=9, year=2026, status="active"):
    actor = identity(db)
    batch = StockParameterBatch(
        id=uuid4(), month=month, year=year,
        effective_date=date(year, month, 1), source_filename="synthetic-stock.xlsx",
        file_hash="a" * 64, status=status, row_count=2, 
        created_by=actor.id, updated_by=actor.id, uploaded_by=actor.id,
    )
    db.add(batch)
    db.flush()
    db.add_all([
        StockParameter(batch_id=batch.id, item_id=f"TEST-{number}", source_row=number,
                           min_stock_level=10, max_stock_level=20, min_order_qty=5, lead_time_days=2)
        for number in (1, 2)
    ])
    db.commit()
    return batch


def payload(batch):
    return StockParameterDeleteRequest(batch_id=batch.id, reason="  Uploaded for the wrong period.  ")


def delete(db, batch):
    return service.delete_stock_parameters(db, month=9, year=2026, payload=payload(batch),
                                          user=identity(db, inventory_delete=True))


def test_deletion_affects_only_reviewed_period_and_preserves_history(db):
    selected = seed(db)
    next_month = seed(db, month=10)
    previous_year = seed(db, year=2025)
    historical = seed(db, status="superseded")

    result = delete(db, selected)
    assert result.deleted_row_count == 2 and not result.replayed
    assert not service.get_stock_management(db, 9, 2026).metadata.has_parameters
    assert service.get_stock_management(db, 10, 2026).metadata.batch_id == str(next_month.id)
    assert service.get_stock_management(db, 9, 2025).metadata.batch_id == str(previous_year.id)
    assert db.get(StockParameterBatch, historical.id).status == "superseded"
    assert db.scalar(select(func.count()).select_from(StockParameter)) == 8
    assert db.get(StockParameterBatch, selected.id).status == "deleted"
    assert db.get(StockParameterBatch, selected.id).updated_by == identity(db).id
    history = service.list_stock_parameter_history(db, 9, 2026)
    assert {entry.status for entry in history} == {"deleted", "superseded"}
    audit = db.scalar(select(AuditLog))
    assert audit.actor_id == identity(db).id and audit.entity_id == selected.id
    assert audit.action == "DELETE" and audit.reason == "Uploaded for the wrong period."
    assert audit.old_values["status"] == "active" and audit.new_values["status"] == "deleted"


def test_wrong_period_cannot_delete_another_month_or_year(db):
    batch = seed(db, month=10)
    with pytest.raises(ApplicationError) as failure:
        delete(db, batch)
    assert failure.value.status_code == 404
    assert db.get(StockParameterBatch, batch.id).status == "active"
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_stale_confirmation_cannot_delete_replacement_upload(db):
    old = seed(db, status="superseded")
    replacement = seed(db)
    with pytest.raises(ApplicationError) as failure:
        delete(db, old)
    assert failure.value.code == "PARAMETERS_CHANGED"
    assert service.get_stock_management(db, 9, 2026).metadata.batch_id == str(replacement.id)


def test_repeat_delete_does_not_remove_later_upload_or_duplicate_audit(db):
    old = seed(db)
    delete(db, old)
    replacement = seed(db)
    repeated = delete(db, old)
    assert repeated.replayed
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert service.get_stock_management(db, 9, 2026).metadata.batch_id == str(replacement.id)


@pytest.mark.parametrize("failure_point", ["audit", "commit"])
def test_delete_rolls_back_with_audit_or_commit_failure(db, failure_point):
    batch = seed(db)
    def fail_commit():
        db.flush()
        raise RuntimeError("synthetic failure")

    target = patch.object(service, "log_audit_event", side_effect=RuntimeError("synthetic failure")) \
        if failure_point == "audit" else patch.object(db, "commit", side_effect=fail_commit)
    with target, pytest.raises(RuntimeError, match="synthetic failure"):
        delete(db, batch)
    assert db.get(StockParameterBatch, batch.id).status == "active"
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert db.scalar(select(func.count()).select_from(StockParameter)) == 2


def client_for(db, user):
    app = create_app(Settings(_env_file=None, app_env="test", database_url="postgresql://test@localhost/disposable",
                              auth_secret_key="synthetic-delete-test-signing-secret-32-bytes"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.mark.parametrize("flags,roles", [
    ({"inventory_read": True}, []),
    ({"inventory_create": True}, []),
    ({"inventory_update": True}, []),
    ({"inventory_read": True}, ["ADMIN"]),
])
def test_read_import_update_and_role_labels_do_not_authorize_delete(db, flags, roles):
    batch = seed(db)
    user = identity(db, **flags)
    user.roles = roles
    with client_for(db, user) as client:
        response = client.request("DELETE", "/api/v1/inventory/management?month=9&year=2026",
                                  json=payload(batch).model_dump(mode="json"))
    assert response.status_code == 403
    assert db.get(StockParameterBatch, batch.id).status == "active"


@pytest.mark.parametrize("flags", [{"inventory_delete": True}, {"is_super_admin": True}])
def test_http_delete_allows_explicit_flag_or_super_admin(db, flags):
    batch = seed(db)
    with client_for(db, identity(db, **flags)) as client:
        response = client.request("DELETE", "/api/v1/inventory/management?month=9&year=2026",
                                  json=payload(batch).model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json()["month"] == 9
    assert response.json()["year"] == 2026
    assert response.json()["batch_id"] == str(batch.id)


@pytest.mark.parametrize("query,body_change", [
    ("month=0&year=2026", {}), ("month=13&year=2026", {}),
    ("month=9&year=1999", {}), ("month=9&year=2101", {}),
    ("month=9&year=2026", {"reason": "   "}),
    ("month=9&year=2026", {"batch_id": "not-a-uuid"}),
    ("month=9&year=2026", {"delete_all": True}),
])
def test_http_delete_validates_period_batch_and_reason(db, query, body_change):
    batch = seed(db)
    body = payload(batch).model_dump(mode="json") | body_change
    with client_for(db, identity(db, inventory_delete=True)) as client:
        response = client.request("DELETE", f"/api/v1/inventory/management?{query}", json=body)
    assert response.status_code == 422
    assert db.get(StockParameterBatch, batch.id).status == "active"


def test_deleted_parameters_cannot_be_edited(db):
    from app.schemas.stock_statements import StockParameterBatchUpdateRequest, StockParameterUpdateItem
    batch = seed(db)
    parameter = db.scalar(select(StockParameter).where(StockParameter.batch_id == batch.id))
    delete(db, batch)
    with pytest.raises(ApplicationError) as failure:
        service.batch_update_stock_parameters(db,
            request=StockParameterBatchUpdateRequest(month=9, year=2026,
                updates=[StockParameterUpdateItem(id=str(parameter.id), min_stock_level=15)]),
            current_user=identity(db, inventory_update=True))
    assert failure.value.status_code == 404
    assert db.get(StockParameter, parameter.id).min_stock_level == 10
