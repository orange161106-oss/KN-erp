from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.auth import Permission, User
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.schemas.purchase_order import OrderCreate
from app.services.purchase_order import create as create_order
from app.tests.integration.test_inventory import postgres_inventory
from app.tests.integration.test_projection import postgres_projection
from app.tests.test_projection import BASE as PROJECTION_BASE
from app.tests.test_purchase_recommendation import payload as recommendation_payload
from app.tests.test_purchase_orders import BASE, PERMISSIONS, approve, order_payload
from app.tests.test_reorder import add_supplier

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_po(postgres_projection):
    engine, client, headers, ids, projection, _ = postgres_projection
    with Session(engine, expire_on_commit=False) as session:
        user = session.get(User, ids['actor_id'])
        user.roles[0].permissions.extend(session.scalars(select(Permission).where(Permission.code.in_(PERMISSIONS))).all())
        supplier_id = add_supplier(session, ids['material_id'])
        session.commit()
    assert client.post(PROJECTION_BASE + '/inputs', headers=headers, json=projection).status_code == 201
    submission = {'submission_key': 'pg-demand', 'reason': 'Synthetic integration evidence',
                  'recommendation': recommendation_payload(projection, supplier_id)}
    response = client.post(BASE + '/demand', headers=headers, json=submission)
    assert response.status_code == 201, response.text
    from uuid import UUID
    approval_id = UUID(response.json()['approval_id'])
    with Session(engine, expire_on_commit=False) as session:
        approve(session, approval_id, session.get(User, ids['actor_id']))
    return engine, client, headers, ids, order_payload(approval_id, supplier_id)


def test_postgres_create_issue_exact_value_and_source_links(postgres_po):
    engine, client, headers, ids, payload = postgres_po
    payload['items'][0]['pricing'] = {'unit_rate': '1.0050', 'currency': 'INR', 'decimal_places': 2,
                                    'rounding': 'HALF_UP', 'approval_reference': 'synthetic-price'}
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['total_value'] == '60.30000000'
    issued = client.post(BASE + '/' + saved['id'] + '/issue', headers=headers, json={'reason': 'Synthetic issue'})
    assert issued.status_code == 200, issued.text
    assert issued.json()['items'][0]['pending_quantity'] is None
    assert issued.json()['issued_at'].endswith('Z')


@pytest.mark.parametrize('statement', [
    'UPDATE purchase_order_items SET ordered_quantity=ordered_quantity+1',
    'DELETE FROM purchase_order_items', 'UPDATE purchase_demand_evidence SET payload_hash=payload_hash',
    'DELETE FROM purchase_demand_evidence', 'DELETE FROM purchase_orders',
    "UPDATE purchase_orders SET po_number='tampered'",
])
def test_postgres_preserves_po_and_calculation_history(postgres_po, statement):
    engine, client, headers, ids, payload = postgres_po
    assert client.post(BASE, headers=headers, json=payload).status_code == 201
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as connection:
            connection.execute(text(statement))
    assert error.value.orig.sqlstate == '55000'


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_orders_cannot_spend_approval_twice(postgres_po, same_key):
    engine, client, headers, ids, payload = postgres_po
    barrier = Barrier(2)
    def worker(index):
        data = OrderCreate.model_validate({**payload, 'creation_key': 'same' if same_key else f'concurrent-{index}'})
        with Session(engine, expire_on_commit=False) as session:
            session.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
            barrier.wait(timeout=10)
            try:
                return create_order(session, data, ids['actor_id'], False).id
            except ApplicationError as error:
                assert error.status_code == 409
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [f.result(timeout=30) for f in [pool.submit(worker, 0), pool.submit(worker, 1)]]
    assert any(outcomes)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1
        assert session.scalar(select(func.sum(PurchaseOrderItem.ordered_quantity))) == 60
    if same_key:
        response = client.post(BASE, headers=headers, json={**payload, 'creation_key': 'same'})
        assert response.status_code == 200 and response.json()['replayed']


def test_postgres_draft_cancel_releases_allocation(postgres_po):
    engine, client, headers, ids, payload = postgres_po
    saved = client.post(BASE, headers=headers, json=payload).json()
    cancelled = client.post(BASE + '/' + saved['id'] + '/cancel', headers=headers, json={'reason': 'Synthetic replacement'})
    assert cancelled.status_code == 200, cancelled.text
    assert client.post(BASE, headers=headers, json={**payload, 'creation_key': 'replacement'}).status_code == 201
