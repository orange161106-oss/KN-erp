from decimal import Decimal
from uuid import UUID

import pytest

pytest_plugins = (
    "app.tests.test_inventory_masters",
    "app.tests.test_inventory",
    "app.tests.test_projection",
    "app.tests.test_purchase_recommendation",
)

from app.models.auth import Permission
from app.modules.inventory.projection_router import projection_database
from app.modules.po_grn.router import order_database
from app.tests.test_purchase_orders import approve
from app.db.session import get_db
from app.tests.test_inventory import inventory_api, source_payload
from app.tests.test_projection import at, input_payload, save, seed_requirement
from app.tests.test_purchase_recommendation import add_supplier, payload as purchase_payload


@pytest.fixture
def purchase_reports_api(inventory_api):
    client, session, user, headers, material, unit = inventory_api
    user.roles[0].permissions.extend([
        Permission(code="inventory.projection.read", description="Synthetic projection reader"),
        Permission(code="inventory.projection.import", description="Synthetic projection importer"),
    ])
    session.commit()
    client.app.dependency_overrides[projection_database] = client.app.dependency_overrides[get_db]
    client.app.dependency_overrides[order_database] = client.app.dependency_overrides[get_db]
    client.app.state.settings.projection_import_enabled = True
    material_id, unit_id = UUID(material["id"]), UUID(unit["id"])
    plant_id, version_id, _ = seed_requirement(session, user.id, material_id, unit["code"])
    stock = source_payload(material_id, unit_id, as_of=at(2).isoformat(), quantity="100")
    assert client.post("/api/v1/inventory/imports", headers=headers, json=stock).status_code == 201
    from sqlalchemy import select
    from app.models.inventory import StockSnapshot
    snapshot_id = session.scalar(select(StockSnapshot.id))
    data = input_payload(material_id, unit_id, plant_id, version_id, snapshot_id)
    supplier_id = add_supplier(session, material_id)
    return client, session, user, headers, data, purchase_payload(data, supplier_id)


def test_inventory_report_permission_is_explicit_and_stock_source_is_visible(masters_api):
    client, session, user, headers = masters_api
    client.app.dependency_overrides[projection_database] = client.app.dependency_overrides[get_db]
    endpoint = "/api/v1/reports/material-stock"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=headers).status_code == 403

    user.roles[0].permissions.append(Permission(
        code="reports.inventory.read", description="Synthetic inventory report reader"))
    session.commit()
    client.app.dependency_overrides[projection_database] = client.app.dependency_overrides[get_db]
    response = client.get(endpoint, headers=headers)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total"] == 0
    assert report["items"] == []
    assert client.get("/api/v1/reports/supplier-purchase-plan", headers=headers).status_code == 403


def test_purchase_flow_reads_saved_recommendation_and_marks_imported_coverage(purchase_reports_api):
    client, session, user, headers, data, recommendation = purchase_reports_api
    save(client, headers, data)
    user.roles[0].permissions.extend([
        Permission(code="purchase.demand.submit", description="Synthetic demand submitter"),
        Permission(code="purchase.orders.create", description="Synthetic PO creator"),
        Permission(code="purchase.orders.issue", description="Synthetic PO issuer"),
        Permission(code="reports.purchase.read", description="Synthetic purchase report reader"),
    ])
    session.commit()
    response = client.post("/api/v1/purchase-orders/demand", headers=headers, json={
        "submission_key": "report-trace-submission",
        "reason": "Synthetic traced demand for report",
        "recommendation": recommendation,
    })
    assert response.status_code == 201, response.text
    approval_id = UUID(response.json()["approval_id"])
    approve(session, approval_id, user)
    order = client.post("/api/v1/purchase-orders", headers=headers, json={
        "creation_key": "report-trace-order",
        "supplier_id": recommendation["supplier_id"],
        "po_date": "2020-01-02",
        "reason": "Synthetic report trace PO",
        "items": [{"approval_id": str(approval_id), "ordered_quantity": "60.0000",
                   "expected_delivery": "2020-01-07T00:00:00Z"}],
    })
    assert order.status_code == 201, order.text
    issued = client.post(f"/api/v1/purchase-orders/{order.json()['id']}/issue", headers=headers,
                         json={"reason": "Synthetic report trace issue"})
    assert issued.status_code == 200, issued.text

    report = client.get("/api/v1/reports/recommendation-fulfilment", headers=headers)
    assert report.status_code == 200, report.text
    result = report.json()
    assert result["is_live"] is False
    assert result["receipt_coverage"] == "IMPORTED_NONLIVE"
    assert result["total"] == 1
    item = result["items"][0]
    assert item["recommendation_status"] == "RECOMMENDED"
    assert Decimal(item["recommended_quantity"]) == Decimal("60.0000")
    assert item["approval_status"] == "APPROVED"
    assert Decimal(item["approved_quantity"]) == Decimal("60.0000")
    assert Decimal(item["issued_ordered_quantity"]) == Decimal("60.0000")
    assert Decimal(item["pending_quantity"]) == Decimal("60.0000")

    filtered = client.get("/api/v1/reports/recommendation-fulfilment", headers=headers, params={
        "po_status": "ISSUED", "po_date_from": "2020-01-01", "po_date_until": "2020-02-01"})
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    outside = client.get("/api/v1/reports/recommendation-fulfilment", headers=headers, params={
        "po_status": "DRAFT", "po_date_from": "2020-01-01", "po_date_until": "2020-02-01"})
    assert outside.status_code == 200, outside.text
    assert outside.json()["total"] == 0
    pending = client.get("/api/v1/reports/pending-purchase-orders", headers=headers)
    assert pending.status_code == 200 and pending.json()["total"] == 1

    grns = client.get("/api/v1/reports/grns", headers=headers)
    assert grns.status_code == 200, grns.text
    assert grns.json()["source"] == "EXISTING_ERP"
    assert grns.json()["items"] == []
