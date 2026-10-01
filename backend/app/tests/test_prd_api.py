from decimal import Decimal
import io
from uuid import uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.auth import Permission, Role, User
from app.models.masters import Product
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


def create_excel_bytes(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def api_test_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("btrim", 1, lambda s: s.strip() if s is not None else None)

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()

    # Create planner user
    planner_role = Role(id=uuid4(), code="PLANNER", name="Planner Role")
    user = User(
        id=uuid4(),
        username="planner_user",
        password_hash="dummy_hash",
        is_active=True,
        roles=[planner_role],
    )
    db.add(user)

    # Seed products
    p1 = Product(code="P-100", name="Widget 100", uom="PCS", is_active=True)
    db.add(p1)
    db.commit()

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user:pass@127.0.0.1/kn_unit_test",
        auth_secret_key=TEST_SIGNING_KEY,
    )
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app, raise_server_exceptions=True) as client:
        token = create_access_token(user.id, settings)
        auth_headers = {"Authorization": f"Bearer {token}"}

        yield client, db, auth_headers, user

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_api_masters_products_crud(api_test_setup):
    client, db, headers, user = api_test_setup

    # List existing products
    resp = client.get("/api/v1/masters/products", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["code"] == "P-100"

    # Create new product
    create_resp = client.post(
        "/api/v1/masters/products",
        headers=headers,
        json={"code": "P-200", "name": "Widget 200", "uom": "PCS"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["code"] == "P-200"

    # Duplicate code rejected
    dup_resp = client.post(
        "/api/v1/masters/products",
        headers=headers,
        json={"code": "P-200", "name": "Duplicate Widget", "uom": "PCS"},
    )
    assert dup_resp.status_code == 409


def test_api_prd_upload_and_promote(api_test_setup):
    client, db, headers, user = api_test_setup

    excel_bytes = create_excel_bytes([
        ["Product Code", "Plant Code", "Planned Quantity", "Target Period"],
        ["P-100", "PLANT-A", 150, "2026-10"],
    ])

    files = {"file": ("prd_oct.xlsx", io.BytesIO(excel_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"planning_period": "2026-10"}

    # Upload
    upload_resp = client.post("/api/v1/prd/upload", headers=headers, files=files, data=data)
    assert upload_resp.status_code == 201
    batch_data = upload_resp.json()
    assert batch_data["status"] == "VALIDATED"
    assert batch_data["row_count"] == 1
    assert batch_data["error_row_count"] == 0
    batch_id = batch_data["id"]

    # Get batch status
    get_batch_resp = client.get(f"/api/v1/prd/batches/{batch_id}", headers=headers)
    assert get_batch_resp.status_code == 200
    assert get_batch_resp.json()["id"] == batch_id

    # Promote
    promote_resp = client.post(
        f"/api/v1/prd/batches/{batch_id}/promote",
        headers=headers,
        data={"planning_period": "2026-10", "revision_label": "R0"},
    )
    assert promote_resp.status_code == 200
    promote_data = promote_resp.json()
    assert promote_data["status"] == "VALIDATED"
    assert promote_data["total_line_items"] == 1
    assert Decimal(promote_data["total_planned_qty"]) == Decimal("150.0000")
    version_id = promote_data["planning_version_id"]

    # View planning versions
    versions_resp = client.get("/api/v1/prd/planning-versions", headers=headers)
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 1
    assert versions[0]["id"] == version_id

    # View items
    items_resp = client.get(f"/api/v1/prd/planning-versions/{version_id}/items", headers=headers)
    assert items_resp.status_code == 200
    items = items_resp.json()
    assert len(items) == 1
    assert items[0]["product_code"] == "P-100"
    assert items[0]["plant_code"] == "PLANT-A"
    assert Decimal(items[0]["planned_quantity"]) == Decimal("150.0000")
