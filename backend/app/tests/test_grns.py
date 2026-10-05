from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models.audit import AuditLog
from app.models.auth import Permission
from app.models.grn import GRN, GRNItem
from app.models.inventory import StockImportBatch, StockSnapshot, StockTransaction
from app.tests.test_inventory_masters import masters_api
from app.tests.test_inventory import inventory_api, source_movement, source_payload
from app.tests.test_projection import projection_api
from app.tests.test_purchase_recommendation import purchase_api
from app.tests.test_purchase_orders import BASE as PO_BASE, create, po_api

BASE = '/api/v1/grns'
PERMISSIONS = ('purchase.grns.read', 'purchase.grns.import')


def receipt_payload(order, accepted='20', rejected='0', key='grn-1', day=8):
    line = order['items'][0]
    at = f'2020-01-{day:02d}T12:00:00Z'
    stock = source_payload(line['consumable_id'], line['unit_id'], export_id=key + ':stock', as_of=at, quantity='117.1234')
    stock['generated_at'] = at
    if Decimal(accepted):
        movement = source_movement(line['consumable_id'], line['unit_id'], key=key + ':event', quantity=accepted)
        movement['event_at'] = at
        stock['movements'] = [movement]
    return {'source_grn_id': key, 'purchase_order_id': order['id'], 'supplier_id': order['supplier_id'],
            'event_at': at, 'source_actor': 'synthetic-source-operator', 'source_status': 'POSTED',
            'reason': 'Synthetic posted ERP receipt', 'stock': stock,
            'items': [{'source_line_id': '1', 'purchase_order_item_id': line['id'],
                       'consumable_id': line['consumable_id'], 'unit_id': line['unit_id'],
                       'received_quantity': str(Decimal(accepted) + Decimal(rejected)), 'accepted_quantity': accepted,
                       'rejected_quantity': rejected, 'source_event_id': key + ':event' if Decimal(accepted) else None}]}


@pytest.fixture
def grn_api(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    user.roles[0].permissions.extend(Permission(code=code, description='Synthetic GRN grant') for code in PERMISSIONS)
    session.commit()
    order = create(client, headers, payload)
    result = client.post(PO_BASE + '/' + order['id'] + '/issue', headers=headers, json={'reason': 'Synthetic issue'})
    assert result.status_code == 200, result.text
    return client, session, user, headers, result.json()


def counts(session):
    return tuple(session.scalar(select(func.count()).select_from(model)) for model in
                 (GRN, GRNItem, StockImportBatch, StockTransaction, StockSnapshot, AuditLog))


def test_partial_rejected_replacement_full_and_snapshot_not_added_twice(grn_api):
    client, session, user, headers, order = grn_api
    data = receipt_payload(order, '20.1234', '2.0000')
    result = client.post(BASE + '/imports', headers=headers, json=data)
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved['items'][0]['accepted_quantity'] == '20.1234'
    po = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert po['fulfilment_status'] == 'PARTIAL'
    assert po['items'][0]['pending_quantity'] == '39.8766'
    assert po['items'][0]['rejected_quantity'] == '2.0000'
    balance = client.get('/api/v1/inventory/balances/' + data['items'][0]['consumable_id'], headers=headers).json()
    assert balance['usable_quantity'] == '117.1234'
    assert client.get(BASE + '/' + saved['id'], headers=headers).json()['source_grn_id'] == 'grn-1'
    assert len(client.get(BASE, headers=headers).json()) == 1
    replacement = receipt_payload(order, '39.8766', key='replacement', day=9)
    assert client.post(BASE + '/imports', headers=headers, json=replacement).status_code == 201
    po = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert po['fulfilment_status'] == 'COMPLETE'
    assert po['items'][0]['accepted_quantity'] == '60.0000'
    assert po['items'][0]['received_quantity'] == '62.0000'
    assert po['items'][0]['pending_quantity'] == '0.0000'


def test_duplicate_same_content_replay_changed_content_conflict(grn_api):
    client, session, user, headers, order = grn_api
    data = receipt_payload(order, '60')
    result = client.post(BASE + '/imports', headers=headers, json=data)
    assert result.status_code == 201, result.text
    before = counts(session)
    retry = client.post(BASE + '/imports', headers=headers, json=data)
    assert retry.status_code == 200 and retry.json()['replayed']
    assert retry.json()['id'] == result.json()['id']
    assert client.post(BASE + '/imports', headers=headers, json={**data, 'reason': 'Different content'}).status_code == 409
    assert counts(session) == before


def test_preimported_stock_is_linked_once(grn_api):
    client, session, user, headers, order = grn_api
    data = receipt_payload(order)
    assert client.post('/api/v1/inventory/imports', headers=headers, json=data['stock']).status_code == 201
    before = counts(session)
    result = client.post(BASE + '/imports', headers=headers, json=data)
    assert result.status_code == 201, result.text
    after = counts(session)
    assert after[2:5] == before[2:5]
    duplicate = {**data, 'source_grn_id': 'different-document'}
    assert client.post(BASE + '/imports', headers=headers, json=duplicate).status_code == 409
    assert counts(session) == after


def test_rejected_only_does_not_fulfil_or_post_stock(grn_api):
    client, session, user, headers, order = grn_api
    before = session.scalar(select(func.count()).select_from(StockTransaction))
    result = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order, '0', '10'))
    assert result.status_code == 201, result.text
    assert result.json()['items'][0]['stock_transaction_id'] is None
    assert session.scalar(select(func.count()).select_from(StockTransaction)) == before
    po = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert po['fulfilment_status'] == 'NOT_RECEIVED'
    assert po['items'][0]['pending_quantity'] == '60.0000'


@pytest.mark.parametrize('change', ['item', 'material', 'unit', 'supplier', 'excess', 'stock_mismatch', 'missing_snapshot', 'float', 'precision', 'inspection'])
def test_invalid_source_rejected_atomically(grn_api, change):
    client, session, user, headers, order = grn_api
    data = receipt_payload(order)
    if change in ('item', 'material', 'unit'):
        field = {'item': 'purchase_order_item_id', 'material': 'consumable_id', 'unit': 'unit_id'}[change]
        data['items'][0][field] = str(uuid4())
    elif change == 'supplier': data['supplier_id'] = str(uuid4())
    elif change == 'excess': data = receipt_payload(order, '61')
    elif change == 'stock_mismatch': data['stock']['movements'][0]['source_quantity'] = '19'
    elif change == 'missing_snapshot': data['stock']['snapshots'] = []
    elif change == 'float': data['items'][0]['accepted_quantity'] = 20.0
    elif change == 'precision': data['items'][0]['accepted_quantity'] = '20.00001'
    else: data['items'][0]['received_quantity'] = '21'
    before = counts(session)
    response = client.post(BASE + '/imports', headers=headers, json=data)
    assert response.status_code in (409, 422), response.text
    assert counts(session) == before


@pytest.mark.parametrize('permission', ['purchase.grns.read', 'purchase.grns.import', 'inventory.stock.import'])
def test_permission_denial_has_no_role_bypass(grn_api, permission):
    client, session, user, headers, order = grn_api
    user.roles[0].permissions[:] = [row for row in user.roles[0].permissions if row.code != permission]
    session.commit()
    if permission.endswith('read'):
        assert client.get(BASE, headers=headers).status_code == 403
    else:
        assert client.post(BASE + '/imports', headers=headers, json=receipt_payload(order)).status_code == 403


def test_import_disabled(grn_api):
    client, session, user, headers, order = grn_api
    client.app.state.settings.inventory_import_enabled = False
    assert client.post(BASE + '/imports', headers=headers, json=receipt_payload(order)).status_code == 409


@pytest.mark.parametrize('cancel', [False, True])
def test_draft_or_cancelled_po_cannot_receive(po_api, cancel):
    client, session, user, headers, submission, payload, identity = po_api
    user.roles[0].permissions.extend(Permission(code=code, description='Synthetic GRN grant') for code in PERMISSIONS)
    session.commit()
    order = create(client, headers, payload)
    if cancel:
        assert client.post(PO_BASE + '/' + order['id'] + '/cancel', headers=headers, json={'reason': 'Synthetic cancellation'}).status_code == 200
    before = counts(session)
    result = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order))
    assert result.status_code == 409 and result.json()['code'] == 'GRN_PO_STATE'
    assert counts(session) == before


def test_audit_failure_rolls_back_stock_grn_and_fulfilment(grn_api, monkeypatch):
    client, session, user, headers, order = grn_api
    before = counts(session)
    def fail(*args, **kwargs): raise SQLAlchemyError('synthetic failure after stock and GRN flush')
    monkeypatch.setattr('app.services.grn.audit', fail)
    result = client.post(BASE + '/imports', headers=headers, json=receipt_payload(order))
    assert result.status_code == 503, result.text
    assert counts(session) == before
    po = client.get(PO_BASE + '/' + order['id'], headers=headers).json()
    assert po['items'][0]['pending_quantity'] == '60.0000'
