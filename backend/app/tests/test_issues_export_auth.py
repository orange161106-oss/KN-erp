from uuid import uuid4
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import Role, User
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.models.masters import Product
from app.models.requirements import RequirementCalculationError
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


@pytest.fixture
def auth_context(db_session):
    settings = app.state.settings
    admin_role = Role(code="ADMIN", name="Administrator")
    db_session.add(admin_role)
    admin_user = User(
        username="admin_planner",
        password_hash="secret",
        is_super_admin=True,
        roles=[admin_role],
    )
    db_session.add(admin_user)
    db_session.commit()

    token = create_access_token(admin_user.id, settings)
    return {
        "user": admin_user,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def auth_headers(auth_context):
    return auth_context["headers"]


def test_issues_export_unauthenticated_returns_401(client):
    res = client.get("/api/v1/requirements/workspace/issues/export?period=2026-10")
    assert res.status_code == 401


def test_issues_export_with_period_param_returns_csv(client, auth_headers):
    res = client.get("/api/v1/requirements/workspace/issues/export?period=2026-10", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]
    # Verify CSV headers are in content
    assert "Part No." in res.text
    assert "Issue Description" in res.text


def test_issues_export_with_month_year_params_returns_csv(client, auth_headers):
    res = client.get("/api/v1/requirements/workspace/issues/export?month=10&year=2026", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]


def test_issues_export_alias_route(client, auth_headers):
    res = client.get("/api/v1/requirements/issues/export?period=2026-10", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]


def test_issues_export_with_actual_error_records(client, db_session, auth_context):
    user = auth_context["user"]
    headers = auth_context["headers"]
    version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=1,
        revision_label="R1",
        status="CALCULATED_WITH_ERRORS",
        source_filename="test_upload.xlsx",
        created_by=user.id,
    )
    batch = ImportBatch(
        id=uuid4(),
        filename="test_upload.xlsx",
        file_size_bytes=1024,
        uploaded_by=user.id,
    )
    header = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=version.id,
        import_batch_id=batch.id,
        planning_period="2026-10",
        total_planned_qty=100.0,
        total_line_items=1,
    )
    product = Product(
        id=uuid4(),
        code="PROD-PART-1",
        name="Engine Bracket",
        part_number="P-ENG-001",
        item_id="ITEM-101",
    )
    prd_item = PRDOrderItem(
        id=uuid4(),
        planning_version_id=version.id,
        header_id=header.id,
        source_row_number=1,
        product_id=product.id,
        product_code=product.code,
        plant_code="PLANT-1",
        target_period="2026-10",
        planned_quantity=100.0,
    )
    calc_err = RequirementCalculationError(
        id=uuid4(),
        planning_version_id=version.id,
        prd_order_item_id=prd_item.id,
        product_id=product.id,
        error_code="MISSING_NORM",
        error_message="No consumption norm mapped for Engine Bracket.",
    )
    db_session.add_all([version, batch, header, product, prd_item, calc_err])
    db_session.commit()

    res = client.get("/api/v1/requirements/workspace/issues/export?period=2026-10", headers=headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="requirement_issues_2026_10.csv"' in res.headers["content-disposition"]
    # Check that error details are in CSV
    assert "P-ENG-001" in res.text
    assert "ITEM-101" in res.text
    assert "PROD-PART-1" in res.text
    assert "MISSING_NORM" in res.text
    assert "No consumption norm mapped for Engine Bracket." in res.text
