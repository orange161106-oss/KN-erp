from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.domain.purchase_engine.orders import line_value, pending_quantity
from app.models.audit import AuditLog
from app.models.auth import Permission, User
from app.models.inventory import StockSnapshot, StockTransaction
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseDemandEvidence, PurchaseOrder
from app.modules.po_grn.router import order_database
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import ReviewPurchaseApprovalRequest
from app.services.purchase_approval import review_purchase_approval
from app.tests.test_inventory import inventory_api
from app.tests.test_inventory_masters import masters_api
from app.tests.test_projection import projection_api, save
from app.tests.test_purchase_recommendation import purchase_api

BASE = '/api/v1/purchase-orders'
PERMISSIONS = ['purchase.orders.' + action for action in ('read', 'create', 'issue', 'cancel', 'price')] + ['purchase.demand.submit']
D = Decimal


@pytest.mark.parametrize('rounding,expected', [('HALF_UP', '1.01'), ('HALF_EVEN', '1.00'), ('DOWN', '1.00')])
def test_explicit_decimal_value_rounding(rounding, expected):
    assert line_value(D('1'), D('1.0050'), 2, rounding) == D(expected)


@pytest.mark.parametrize('fulfilled,pending', [(None, None), ('0', '10'), ('3.1234', '6.8766'), ('10', '0')])
def test_pending_requires_explicit_fulfilment(fulfilled, pending):
    assert pending_quantity(D('12'), D('2'), D(fulfilled) if fulfilled is not None else None) == (D(pending) if pending is not None else None)


def test_invalid_decimal_and_overfulfilment():
    with pytest.raises(ValueError): line_value(1.0, D('1'), 2, 'HALF_UP')
    with pytest.raises(ValueError): pending_quantity(D('1'), D('0'), D('2'))


def approve(session, identity, requester):
    reviewer = session.scalar(select(User).where(User.username == 'po_reviewer'))
    if reviewer is None:
        reviewer = User(username='po_reviewer', password_hash=requester.password_hash)
        session.add(reviewer)
        session.commit()
    return review_purchase_approval(session, identity, ReviewPurchaseApprovalRequest(action='APPROVE'),
        CurrentUser(id=reviewer.id, username=reviewer.username, roles=[], permissions=['purchasing:approve']))


def order_payload(approval_id, supplier_id, quantity='60', key='po-test-1'):
    return {'creation_key': key, 'supplier_id': str(supplier_id), 'po_date': '2020-01-02', 'reason': 'Synthetic approved order',
            'items': [{'approval_id': str(approval_id), 'ordered_quantity': quantity,
                       'expected_delivery': '2020-01-07T00:00:00Z'}]}


@pytest.fixture
def po_api(purchase_api):
    client, session, user, headers, projection, recommendation, adjustment_id = purchase_api
    user.roles[0].permissions.extend(Permission(code=code, description='Synthetic PO grant') for code in PERMISSIONS)
    session.commit()
    client.app.dependency_overrides[order_database] = client.app.dependency_overrides[get_db]
    save(client, headers, projection)
    submission = {'submission_key': 'demand-1', 'reason': 'Synthetic traced demand', 'recommendation': recommendation}
    result = client.post(BASE + '/demand', headers=headers, json=submission)
    assert result.status_code == 201, result.text
    identity = UUID(result.json()['approval_id'])
    approve(session, identity, user)
    return client, session, user, headers, submission, order_payload(identity, recommendation['supplier_id']), identity


def create(client, headers, payload):
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_traced_submission_uses_server_values_and_replays(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    saved = session.get(PurchaseApproval, identity)
    assert saved.system_recommended_qty == D('60')
    assert session.scalar(select(func.count()).select_from(PurchaseDemandEvidence)) == 1
    response = client.post(BASE + '/demand', headers=headers, json=submission)
    assert response.status_code == 200 and response.json()['approval_id'] == str(identity)
    assert client.post(BASE + '/demand', headers=headers, json={**submission, 'reason': 'Different reason'}).status_code == 409
    assert client.post(BASE + '/demand', headers=headers, json={**submission, 'recommended_quantity': '999'}).status_code == 422


def test_po_draft_issue_traceability_and_no_stock_effect(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    before = (session.scalar(select(func.count()).select_from(StockTransaction)), session.scalar(select(StockSnapshot.usable_quantity)))
    order = create(client, headers, payload)
    assert order['status'] == 'DRAFT' and order['items'][0]['pending_quantity'] == '0.0000'
    assert order['total_value'] is None and order['items'][0]['line_value'] is None
    assert order['items'][0]['recommendation_evidence']['projection']['source_set_id'] == 'synthetic-inputs-1'
    result = client.post(BASE + '/' + order['id'] + '/issue', headers=headers, json={'reason': 'Approved commitment'})
    assert result.status_code == 200, result.text
    issued = result.json()
    assert issued['status'] == 'ISSUED' and issued['items'][0]['pending_quantity'] is None
    assert issued['pending_basis'] == 'FULFILMENT_NOT_CONNECTED'
    assert len(issued['history']) == 2
    repeat = client.post(BASE + '/' + order['id'] + '/issue', headers=headers, json={'reason': 'Retry'})
    assert repeat.json()['replayed'] and len(repeat.json()['history']) == 2
    assert before == (session.scalar(select(func.count()).select_from(StockTransaction)), session.scalar(select(StockSnapshot.usable_quantity)))
    assert client.post(BASE + '/' + order['id'] + '/cancel', headers=headers, json={'reason': 'Unsafe cancellation'}).status_code == 409


@pytest.mark.parametrize('status', ['PENDING', 'REJECTED'])
def test_unapproved_and_rejected_cannot_create(po_api, status):
    client, session, user, headers, submission, payload, identity = po_api
    session.get(PurchaseApproval, identity).status = status
    session.commit()
    assert client.post(BASE, headers=headers, json=payload).status_code == 409
    assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 0


def test_modified_review_with_reason_is_valid(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    row = session.get(PurchaseApproval, identity)
    row.status, row.approved_qty, row.reason = 'MODIFIED', D('30'), 'Synthetic reviewer override'
    session.commit()
    payload['items'][0]['ordered_quantity'] = '30'
    assert create(client, headers, payload)['items'][0]['approval_snapshot']['status'] == 'MODIFIED'


def test_legacy_approval_not_eligible(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    # SQLite-only fixture deletion simulates a pre-M5.3 legacy row.
    session.delete(session.scalar(select(PurchaseDemandEvidence)))
    session.commit()
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 409 and response.json()['code'] == 'PO_TRACEABILITY_MISSING'
    result = client.get(BASE + '/eligible', headers=headers).json()
    assert result[0]['eligible'] is False and 'Resubmit' in result[0]['limitation']


def test_draft_allocation_cancel_and_retry_are_audited(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    order = create(client, headers, payload)
    assert client.post(BASE, headers=headers, json=payload).status_code == 200
    changed = {**payload, 'creation_key': 'another'}
    assert client.post(BASE, headers=headers, json=changed).status_code == 409
    assert client.post(BASE, headers=headers, json={**payload, 'reason': 'Changed'}).status_code == 409
    cancelled = client.post(BASE + '/' + order['id'] + '/cancel', headers=headers, json={'reason': 'Rebuild terms'})
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'CANCELLED'
    assert create(client, headers, changed)['status'] == 'DRAFT'


def test_partial_allocations_never_exceed_approval(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    row = session.get(PurchaseApproval, identity)
    row.status, row.approved_qty, row.reason = 'MODIFIED', D('120'), 'Synthetic larger reviewed demand'
    session.commit()
    payload['items'][0]['ordered_quantity'] = '60'
    create(client, headers, payload)
    payload['creation_key'] = 'part-2'
    payload['items'][0]['ordered_quantity'] = '60'
    create(client, headers, payload)
    payload['creation_key'] = 'part-3'
    payload['items'][0]['ordered_quantity'] = '0.0001'
    assert client.post(BASE, headers=headers, json=payload).status_code == 409


def test_splitting_cannot_bypass_supplier_increments(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    payload['items'][0]['ordered_quantity'] = '20'
    result = client.post(BASE, headers=headers, json=payload)
    assert result.status_code == 409 and result.json()['code'] == 'PO_SPLIT_CONSTRAINT_CONFLICT'


def test_changed_approval_blocks_issue(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    order = create(client, headers, payload)
    row = session.get(PurchaseApproval, identity)
    row.reason = 'Later modified source reason'
    session.commit()
    assert client.post(BASE + '/' + order['id'] + '/issue', headers=headers, json={'reason': 'Issue'}).status_code == 409


def test_exact_price_and_permission(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    payload['items'][0]['pricing'] = {'unit_rate': '1.0050', 'currency': 'INR', 'decimal_places': 2,
                                    'rounding': 'HALF_UP', 'approval_reference': 'synthetic-approved-quote'}
    order = create(client, headers, payload)
    assert D(order['total_value']) == D('60.30')
    assert D(order['items'][0]['pricing']['unit_rate']) == D('1.0050')
    user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code != 'purchase.orders.price']
    session.commit()
    payload['creation_key'] = 'new-price'
    assert client.post(BASE, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize('quantity', [0.1, True, '-1', '0', 'NaN', '1.00001'])
def test_invalid_quantity_rejected(po_api, quantity):
    client, session, user, headers, submission, payload, identity = po_api
    payload['items'][0]['ordered_quantity'] = quantity
    assert client.post(BASE, headers=headers, json=payload).status_code == 422


def test_permissions_no_admin_bypass(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    assert client.get(BASE).status_code == 401
    user.roles[0].permissions = []
    user.roles[0].code = 'ADMIN'
    session.commit()
    assert client.get(BASE, headers=headers).status_code == 403
    assert client.post(BASE, headers=headers, json=payload).status_code == 403


def test_wrong_supplier_and_duplicate_items(po_api):
    client, session, user, headers, submission, payload, identity = po_api
    assert client.post(BASE, headers=headers, json={**payload, 'supplier_id': str(uuid4())}).status_code == 409
    assert client.post(BASE, headers=headers, json={**payload, 'items': payload['items'] * 2}).status_code == 422


def test_order_and_audit_rollback_together(po_api, monkeypatch):
    from app.services import purchase_order
    client, session, user, headers, submission, payload, identity = po_api
    def fail(*args, **kwargs): raise SQLAlchemyError('secret connection detail')
    monkeypatch.setattr(purchase_order, 'audit', fail)
    result = client.post(BASE, headers=headers, json=payload)
    assert result.status_code == 503 and 'secret connection detail' not in result.text
    assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 0
