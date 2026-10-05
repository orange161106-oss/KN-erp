import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.inventory_masters import Supplier

from app.tests.integration.test_inventory import postgres_inventory
from app.tests.integration.test_projection import postgres_projection
from app.tests.test_projection import BASE as PROJECTION_BASE
from app.tests.test_purchase_recommendation import BASE, payload
from app.tests.test_reorder import add_supplier

pytestmark = pytest.mark.integration


def test_postgres_purchase_uses_consistent_projection_and_exact_quantities(postgres_projection, monkeypatch):
    from app.repositories import purchase_recommendation
    engine, client, headers, ids, data, _ = postgres_projection
    with Session(engine) as session:
        supplier_id = add_supplier(session, ids['material_id'])
    assert client.post(PROJECTION_BASE + '/inputs', headers=headers, json=data).status_code == 201
    original = purchase_recommendation.context
    def checked(session, *args):
        assert session.execute(text('SHOW transaction_isolation')).scalar_one() == 'repeatable read'
        # M4.2 has established the source snapshot. A concurrent master change
        # must not be mixed into that same report's source view.
        with Session(engine) as writer:
            writer.get(Supplier, supplier_id).is_active = False
            writer.commit()
        return original(session, *args)
    monkeypatch.setattr(purchase_recommendation, 'context', checked)
    response = client.post(BASE, headers=headers, json=payload(data, supplier_id))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['recommended_quantity'] == '60.0000' and result['raw_quantity'] == '13.0000'
    assert result['projection']['source_set_id'] == data['source_set_id']
    monkeypatch.setattr(purchase_recommendation, 'context', original)
    response = client.post(BASE, headers=headers, json=payload(data, supplier_id))
    assert response.status_code == 409 and response.json()['code'] == 'PURCHASE_MASTER_INACTIVE'
