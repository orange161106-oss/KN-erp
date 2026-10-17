from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.auth import Permission, Role, User
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.prd import ImportBatch, PlanningVersion
from app.models.purchase_approval import PurchaseApproval
from app.models.requirements import MonthlyRequirementRecord
from app.security.passwords import PasswordService
from app.security.tokens import create_access_token

BASE = "/api/v1/purchasing/workspace"


@pytest.fixture
def purchase_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else "")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user@127.0.0.1/kn_unit_test",
        auth_secret_key="test-secret-key-for-purchase-workspace-32b",
    )
    passwords = PasswordService()

    with Session(engine, expire_on_commit=False) as session:
        view_permission = Permission(code="purchasing:view", description="View purchasing approvals")
        role = Role(code="PURCHASE_VIEWER", name="Purchase viewer", permissions=[view_permission])
        user = User(
            username="purchase_operator",
            full_name="Purchase Operator",
            password_hash=passwords.hash("password"),
            purchase_orders_read=True,
            purchase_orders_create=True,
            roles=[role],
        )
        unit = Unit(code="KGS", name="Kilograms")
        session.add_all([user, unit])
        session.flush()

        consumable = Consumable(code="WLD-01", name="Welding Wire", unit_id=unit.id)
        supplier = Supplier(code="SUP-01", name="Alpha Supplies")
        session.add_all([consumable, supplier])
        session.flush()
        session.add(SupplierConsumable(consumable_id=consumable.id, supplier_id=supplier.id))

        version = PlanningVersion(
            planning_period="2026-10",
            version_number=0,
            revision_label="R0",
            source_filename="oct_plan.xlsx",
            status="CALCULATED",
            planning_month=10,
            planning_year=2026,
            created_by=user.id,
        )
        session.add(version)
        session.flush()

        session.add_all(
            [
                MonthlyRequirementRecord(
                    planning_version_id=version.id,
                    planning_period="2026-10",
                    planning_month=10,
                    planning_year=2026,
                    row_index=1,
                    part_name="Bracket",
                    part_number="PRD-01",
                    consumable_code="WLD-01",
                    consumable_name="Welding Wire",
                    process_name="Weld",
                    production_order_qty=Decimal("100.0000"),
                    scheduled_consumable_qty=Decimal("50.0000"),
                    stock_qty=Decimal("20.0000"),
                    po_pending_qty=Decimal("5.0000"),
                    shortage_qty=Decimal("25.0000"),
                    unit="KGS",
                    status="Critical shortage",
                    created_by=user.id,
                ),
                MonthlyRequirementRecord(
                    planning_version_id=version.id,
                    planning_period="2026-10",
                    planning_month=10,
                    planning_year=2026,
                    row_index=2,
                    part_name="Tray",
                    part_number="PRD-02",
                    consumable_code="WLD-01",
                    consumable_name="Welding Wire",
                    process_name="Weld",
                    production_order_qty=Decimal("80.0000"),
                    scheduled_consumable_qty=Decimal("30.0000"),
                    stock_qty=Decimal("4.0000"),
                    po_pending_qty=Decimal("1.0000"),
                    shortage_qty=Decimal("25.0000"),
                    unit="KGS",
                    status="Critical shortage",
                    created_by=user.id,
                ),
            ]
        )
        session.commit()

        app = create_app(settings)

        def database():
            with Session(engine, expire_on_commit=False, autoflush=False) as req_session:
                yield req_session

        app.dependency_overrides[get_db] = database
        headers = {"Authorization": "Bearer " + create_access_token(user.id, settings)}

        with TestClient(app) as client:
            yield client, session, user, headers
    engine.dispose()


def test_purchase_workspace_aggregates_requirement_shortage(purchase_client):
    client, _, _, headers = purchase_client

    response = client.get(f"{BASE}?month=10&year=2026", headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["plan_metadata"]["revision_label"] == "R0"
    assert len(data["records"]) == 1

    row = data["records"][0]
    assert row["consumable_code"] == "WLD-01"
    assert row["supplier_code"] == "SUP-01"
    assert Decimal(row["required_qty"]) == Decimal("80.0000")
    assert Decimal(row["stock_qty"]) == Decimal("24.0000")
    assert Decimal(row["po_pending_qty"]) == Decimal("6.0000")
    assert Decimal(row["shortage_qty"]) == Decimal("50.0000")
    assert Decimal(row["system_recommended_qty"]) == Decimal("50.0000")
    assert row["status"] == "READY_FOR_APPROVAL"


def test_purchase_workspace_submission_uses_existing_approval_queue(purchase_client):
    client, session, _, headers = purchase_client

    workspace = client.get(f"{BASE}?month=10&year=2026", headers=headers).json()
    record_id = workspace["records"][0]["id"]

    submit = client.post(
        f"{BASE}/submit?month=10&year=2026",
        headers=headers,
        json={"record_ids": [record_id], "reason": "Monthly purchase plan"},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["submitted_count"] == 1

    approval = session.scalar(select(PurchaseApproval))
    assert approval is not None
    assert approval.status == "PENDING"
    assert approval.system_recommended_qty == Decimal("50.0000")
    assert approval.reason == "Monthly purchase plan"

    handoff = client.get("/api/v1/purchasing/approvals/approved-handoff", headers=headers)
    assert handoff.status_code == 200
    assert handoff.json() == []
def test_duplicate_workspace_submission_does_not_create_duplicate_approval(
    purchase_client,
):
    client, session, _, headers = purchase_client

    workspace = client.get(
        f"{BASE}?month=10&year=2026",
        headers=headers,
    )
    assert workspace.status_code == 200

    record_id = workspace.json()["records"][0]["id"]

    payload = {
        "record_ids": [record_id],
        "reason": "Duplicate submission regression test",
    }

    first = client.post(
        f"{BASE}/submit?month=10&year=2026",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"{BASE}/submit?month=10&year=2026",
        headers=headers,
        json=payload,
    )
    assert second.status_code == 200, second.text

    count = session.scalar(
        select(func.count(PurchaseApproval.id))
    )
    assert count == 1


def test_central_workspace_api_does_not_fall_back_to_stale_monthly_rows(purchase_client):
    client, session, user, headers = purchase_client
    version = session.scalar(select(PlanningVersion))
    session.add(ImportBatch(filename='central-production.xlsx', file_size_bytes=1, uploaded_by=user.id,
        planning_version_id=version.id, status='VALIDATED', row_count=2, valid_row_count=2,
        validation_summary={'workflow':'BASIC_CENTRAL_V1'}))
    session.commit()
    response = client.get(f'{BASE}?month=10&year=2026', headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['plan_metadata']['source_workflow'] == 'BASIC_CENTRAL_V1'
    assert response.json()['records'] == []
    assert 'no saved consumable requirements' in response.json()['notice']
    export = client.get(f'{BASE}/export?month=10&year=2026', headers=headers)
    assert export.status_code == 200
    submit = client.post(f'{BASE}/submit?month=10&year=2026', headers=headers,
        json={'record_ids':['stale-monthly-row'], 'reason':'Synthetic central guard'})
    assert submit.status_code == 409
    assert 'CENTRAL_PURCHASE_ASSESSMENT_REQUIRED' in submit.text


def test_purchase_edit_api_enforces_update_permissions_and_rejects_calculated_fields(purchase_client):
    client, session, user, headers = purchase_client
    row = client.get(f'{BASE}?month=10&year=2026', headers=headers).json()['records'][0]
    edit = {'record_id': row['id'], 'expected_draft_version': 0,
        'expected_name': row['consumable_name'], 'expected_master_unit': row['master_unit'],
        'requested_purchase_qty': '12.3456', 'purchase_notes': 'Synthetic API proposal'}
    payload = {'edits': [edit], 'reason': 'Synthetic API verification'}
    url = f'{BASE}/save?month=10&year=2026'
    assert client.post(url, headers=headers, json=payload).status_code == 403
    user.purchase_update = True
    session.commit()
    saved = client.post(url, headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()['records'][0]['requested_purchase_qty']) == Decimal('12.3456')
    assert Decimal(saved.json()['records'][0]['system_recommended_qty']) == Decimal('50')
    edit['required_qty'] = '999'
    assert client.post(url, headers=headers, json=payload).status_code == 422
