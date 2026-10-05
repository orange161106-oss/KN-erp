import pytest
from sqlalchemy.orm import Session

from app.tests.integration.test_inventory import postgres_inventory
from app.tests.integration.test_projection import postgres_projection
from app.tests.test_projection import BASE as PROJECTION_BASE
from app.tests.test_reorder import BASE, add_supplier, payload

pytestmark = pytest.mark.integration


def test_postgres_reorder_composes_source_evidence(postgres_projection):
    engine, client, headers, ids, data, _ = postgres_projection
    with Session(engine) as session:
        supplier_id = add_supplier(session, ids['material_id'])
    assert client.post(PROJECTION_BASE + '/inputs', headers=headers, json=data).status_code == 201
    response = client.post(BASE, headers=headers, json=payload(data, supplier_id))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'DETERMINED' and result['reorder_required'] is False
    assert result['latest_safe_order_at'] == '2020-01-03T00:00:00Z'
    assert result['projection']['source_set_id'] == data['source_set_id']
