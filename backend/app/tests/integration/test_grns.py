from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.auth import Permission, User
from app.models.grn import GRN, GRNItem
from app.models.inventory import StockTransaction
from app.schemas.grn import GRNImport
from app.services.grn import import_grn
from app.tests.integration.test_inventory import postgres_inventory
from app.tests.integration.test_projection import postgres_projection
from app.tests.integration.test_purchase_orders import postgres_po
from app.tests.test_grns import BASE, PERMISSIONS, PO_BASE, counts, receipt_payload

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_grn(postgres_po):
    engine, client, headers, ids, payload = postgres_po
    with Session(engine) as session:
        user = session.get(User, ids['actor_id'])
        user.roles[0].permissions.extend(session.scalars(select(Permission).where(Permission.code.in_(PERMISSIONS))).all())
        session.commit()
    created = client.post(PO_BASE, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    result = client.post(PO_BASE + '/' + created.json()['id'] + '/issue', headers=headers, json={'reason': 'Synthetic issue'})
    assert result.status_code == 200, result.text
    return engine, client, headers, ids, result.json()


def test_postgres_full_receipt_and_replay(postgres_grn):
    engine, client, headers, ids, order = postgres_grn
    data = receipt_payload(order, '60')
    result = client.post(BASE + '/imports', headers=headers, json=data)
    assert result.status_code == 201, result.text
    assert client.post(BASE + '/imports', headers=headers, json=data).status_code == 200
    saved = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert saved['fulfilment_status'] == 'COMPLETE'
    assert saved['items'][0]['pending_quantity'] == '0.0000'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GRN)) == 1
        assert session.scalar(select(func.sum(GRNItem.accepted_quantity))) == 60
        assert session.scalar(select(StockTransaction.quantity)) == 60


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_receipts_cannot_double_fulfil(postgres_grn, same_key):
    engine, client, headers, ids, order = postgres_grn
    barrier = Barrier(2)
    def worker(index):
        data = GRNImport.model_validate(receipt_payload(order, '40', key='same' if same_key else f'race-{index}', day=8 if same_key else 8 + index))
        with Session(engine, expire_on_commit=False) as session:
            session.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
            barrier.wait(timeout=10)
            try:
                return import_grn(session, data, ids['actor_id'], enabled=True).id
            except ApplicationError as error:
                assert error.status_code == 409
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, index) for index in range(2)]
        outcomes = [future.result(timeout=30) for future in futures]
    assert any(outcomes)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GRN)) == 1
        assert session.scalar(select(func.sum(GRNItem.accepted_quantity))) == 40
        assert session.scalar(select(func.sum(StockTransaction.quantity))) == 40
    if same_key:
        retry = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order, '40', key='same'))
        assert retry.status_code == 200 and retry.json()['replayed']
    else:
        loser = next(index for index, outcome in enumerate(outcomes) if outcome is None)
        retry = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order, '40', key=f'race-{loser}', day=8 + loser))
        assert retry.status_code == 409 and retry.json()['code'] == 'GRN_OVER_RECEIPT_TBD'


def test_concurrent_valid_partials_complete_after_retry(postgres_grn):
    engine, client, headers, ids, order = postgres_grn
    barrier = Barrier(2)
    payloads = [receipt_payload(order, '30', key=f'partial-{index}', day=8 + index) for index in range(2)]
    def worker(index):
        with Session(engine, expire_on_commit=False) as session:
            session.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
            barrier.wait(timeout=10)
            try:
                import_grn(session, GRNImport.model_validate(payloads[index]), ids['actor_id'], enabled=True)
                return True
            except ApplicationError as error:
                assert error.status_code == 409
                return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, index) for index in range(2)]
        outcomes = [future.result(timeout=30) for future in futures]
    assert any(outcomes)
    for index, succeeded in enumerate(outcomes):
        if not succeeded:
            result = client.post(BASE + '/imports', headers=headers, json=payloads[index])
            assert result.status_code == 201, result.text
    saved = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert saved['fulfilment_status'] == 'COMPLETE'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GRN)) == 2
        assert session.scalar(select(func.sum(StockTransaction.quantity))) == 60


def test_postgres_failure_after_stock_flush_rolls_back_everything(postgres_grn, monkeypatch):
    engine, client, headers, ids, order = postgres_grn
    with Session(engine) as session: before = counts(session)
    def fail(*args, **kwargs): raise SQLAlchemyError('Synthetic audit failure')
    monkeypatch.setattr('app.services.grn.audit', fail)
    result = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order))
    assert result.status_code == 503, result.text
    with Session(engine) as session: assert counts(session) == before
    saved = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert saved['fulfilment_status'] == 'NOT_RECEIVED'
    assert saved['items'][0]['pending_quantity'] == '60.0000'


@pytest.mark.parametrize('statement', ['UPDATE grns SET reason=reason', 'DELETE FROM grns',
                                     'UPDATE grn_items SET accepted_quantity=accepted_quantity', 'DELETE FROM grn_items'])
def test_postgres_receipt_history_is_immutable(postgres_grn, statement):
    engine, client, headers, ids, order = postgres_grn
    result = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order))
    assert result.status_code == 201, result.text
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as connection: connection.execute(text(statement))
    assert error.value.orig.sqlstate == '55000'
