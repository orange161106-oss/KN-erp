"""Keep incoming MRP issue reporting compatible with the saved purchase workflow."""
import csv
from decimal import Decimal
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import register_error_handlers
from app.db.session import get_db
from app.models.rules import ConsumptionNorm
from app.security.dependencies import get_current_user
from app.services import requirements_workspace as monthly
from app.services.purchase_workspace import list_purchase_workspace
from app.tests.test_central_basic_planning import db, catalog, calculated
from app.tests.test_permission_foundation import actor


def plan_with_issue(db, catalog):
    norm = db.scalar(select(ConsumptionNorm).where(ConsumptionNorm.product_id == catalog[4].id))
    norm.is_active = False
    db.commit()
    calculated(db, catalog)


def test_new_issue_count_and_existing_purchase_warning_both_survive_the_merge(db, catalog):
    plan_with_issue(db, catalog)
    metadata = monthly.get_monthly_plan_metadata(db, 10, 2026)
    assert metadata.record_count == 1 and metadata.issue_count == 1
    purchase = list_purchase_workspace(db, month=10, year=2026)
    assert '1 requirement configuration issues' in purchase.notice
    assert purchase.records[0].required_qty == Decimal('200')
    assert purchase.records[0].system_recommended_qty is None


def test_incoming_issue_list_and_csv_use_real_source_identity_without_formula_execution(db, catalog):
    plan_with_issue(db, catalog)
    issues = monthly.get_period_calculation_issues(db, month=10, year=2026)
    assert len(issues) == 1
    assert (issues[0]['product_code'], issues[0]['part_number'], issues[0]['item_id']) == ('PROD-B', 'PART-B', 'ITEM-B')
    assert monthly.get_period_calculation_issues(db, month=11, year=2026) == []
    catalog[4].name = '=SUM(1,2)'
    db.commit()
    document = monthly.export_period_calculation_issues_csv(db, month=10, year=2026)
    assert document.startswith(b'\xef\xbb\xbf')
    rows = list(csv.reader(StringIO(document.decode('utf-8-sig'))))
    assert rows[0][:3] == ['Part No.', 'Item ID', 'Product Code']
    assert rows[1][:4] == ['PART-B', 'ITEM-B', 'PROD-B', "'=SUM(1,2)"]
    assert rows[1][5] == issues[0]['error_code']


def test_issues_endpoints_keep_the_existing_read_grant_and_return_a_download(db, catalog):
    from app.modules.requirements.requirements_workspace_router import router
    plan_with_issue(db, catalog)
    user = actor()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        path = '/api/v1/requirements/workspace/issues'
        assert client.get(path + '?month=10&year=2026').status_code == 403
        user = actor(requirements_read=True)
        assert client.get(path + '?month=10&year=2026').json()[0]['product_code'] == 'PROD-B'
        response = client.get(path + '/export?month=10&year=2026')
        assert response.status_code == 200 and 'text/csv' in response.headers['content-type']
        assert 'Requirement_Issues_2026_10.csv' in response.headers['content-disposition']
        assert 'PART-B,ITEM-B,PROD-B' in response.content.decode('utf-8-sig')
