from datetime import datetime, timezone
from decimal import Decimal, localcontext
from functools import wraps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.purchase_engine.orders import line_value, satisfies_order_terms
from app.models.audit import AuditLog
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseDemandEvidence, PurchaseOrder, PurchaseOrderItem
from app.repositories import purchase_order as repository
from app.schemas.purchase_order import EligibleDemand, OrderItemResponse, OrderResponse
from app.services import purchase_recommendation
from app.services.projection import digest, utc


def transactional(function):
    @wraps(function)
    def wrapped(session, *args, **kwargs):
        try:
            return function(session, *args, **kwargs)
        except IntegrityError:
            session.rollback()
            raise ApplicationError('PO_CONFLICT', 'A concurrent request conflicts. Retry with the same request key.', 409) from None
        except SQLAlchemyError as error:
            session.rollback()
            if getattr(getattr(error, 'orig', None), 'sqlstate', None) in ('40001', '40P01'):
                raise ApplicationError('PO_RETRY_REQUIRED', 'Source or allocation changed concurrently. Retry the unchanged request.', 409) from None
            raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None
        except Exception:
            session.rollback()
            raise
    return wrapped


def audit(session, actor, identity, action, reason, values, old=None, entity='purchase_orders'):
    session.add(AuditLog(actor_id=actor, entity_type=entity, entity_id=identity, action=action,
                         reason=reason, old_values=old, new_values=values))


def approval_snapshot(row):
    return dict(id=str(row.id), consumable_id=str(row.consumable_id), supplier_id=str(row.supplier_id),
                planning_version_id=str(row.planning_version_id), rule_version=row.rule_version,
                raw_calculated_qty=format(row.raw_calculated_qty, '.4f'), system_recommended_qty=format(row.system_recommended_qty, '.4f'),
                approved_qty=format(row.approved_qty, '.4f') if row.approved_qty is not None else None,
                uom=row.uom, status=row.status, reason=row.reason, requested_by=str(row.requested_by),
                reviewed_by=str(row.reviewed_by), reviewed_at=utc(row.reviewed_at).isoformat() if row.reviewed_at else None)


def verified(session, row):
    if row is None:
        raise ApplicationError('APPROVAL_NOT_FOUND', 'Purchase approval does not exist.', 404)
    if (row.status not in ('APPROVED', 'MODIFIED') or row.approved_qty is None or row.approved_qty <= 0
            or not row.reviewed_by or not row.reviewed_at or row.reviewed_by == row.requested_by):
        raise ApplicationError('PO_APPROVAL_REQUIRED', 'A positive, independently reviewed approved recommendation is required.', 409)
    saved = repository.evidence(session, row.id)
    if not saved:
        raise ApplicationError('PO_TRACEABILITY_MISSING', 'This legacy approval has no calculation evidence. Resubmit through traced demand and obtain review.', 409)
    report = saved.report
    if (str(row.consumable_id) != report['request']['consumable_id'] or str(row.supplier_id) != report['supplier_id']
            or str(row.planning_version_id) != report['request']['planning_version_id']
            or row.rule_version != report['engine_version'] or row.requested_by != saved.submitted_by
            or row.system_recommended_qty != Decimal(report['recommended_quantity'])
            or row.raw_calculated_qty != Decimal(report['raw_quantity'])):
        raise ApplicationError('PO_APPROVAL_CHANGED', 'Approval identity or original quantities differ from the submitted evidence.', 409)
    if row.status == 'APPROVED' and row.approved_qty != row.system_recommended_qty:
        raise ApplicationError('PO_APPROVAL_CHANGED', 'An unchanged approval must equal the system recommendation.', 409)
    if row.status == 'MODIFIED' and not (row.reason or '').strip():
        raise ApplicationError('PO_OVERRIDE_REASON_REQUIRED', 'Modified approval requires its recorded reason.', 409)
    material, unit, supplier, mapping, version = repository.masters(session, row)
    if not all(obj is not None and obj.is_active for obj in (material, unit, supplier, mapping)):
        raise ApplicationError('PO_MASTER_INACTIVE', 'Active material, unit, supplier and mapping are required.', 409)
    if (version is None or version.status in ('DRAFT', 'SUPERSEDED') or not version.approved_at or not version.approved_by
            or row.uom != unit.code or str(unit.id) != report['request']['unit_id']):
        raise ApplicationError('PO_SOURCE_INELIGIBLE', 'Planning version or stock unit is no longer eligible.', 409)
    return saved, material, unit, supplier


@transactional
def submit_demand(session, data, actor):
    payload_hash = digest(data.model_dump(mode='json'))
    previous = session.scalar(select(PurchaseDemandEvidence).where(PurchaseDemandEvidence.submission_key == data.submission_key))
    if previous:
        if previous.payload_hash != payload_hash:
            raise ApplicationError('DEMAND_KEY_CONFLICT', 'Submission key already has different content.', 409)
        return {'approval_id': previous.approval_id, 'evidence_id': previous.id, 'replayed': True}
    result = purchase_recommendation.report(session, data.recommendation)
    if result.status != 'RECOMMENDED' or not result.recommended_quantity or result.recommended_quantity <= 0:
        raise ApplicationError('DEMAND_NOT_RECOMMENDED', 'A complete positive server recommendation is required.', 409)
    # Existing M5.2 NUMERIC(14,4) remains unchanged; reject overflow rather than truncate.
    if abs(result.raw_quantity) >= Decimal('1e10') or result.recommended_quantity >= Decimal('1e10'):
        raise ApplicationError('APPROVAL_QUANTITY_RANGE', 'Quantity exceeds the approval queue precision.', 422)
    from app.models.inventory_masters import Unit
    unit = session.get(Unit, data.recommendation.unit_id)
    row = PurchaseApproval(consumable_id=data.recommendation.consumable_id, supplier_id=data.recommendation.supplier_id,
                           planning_version_id=data.recommendation.planning_version_id, rule_version=result.engine_version,
                           raw_calculated_qty=result.raw_quantity, system_recommended_qty=result.recommended_quantity,
                           uom=unit.code, status='PENDING', reason=data.reason, requested_by=actor)
    session.add(row)
    session.flush()
    saved = PurchaseDemandEvidence(approval_id=row.id, submission_key=data.submission_key, payload_hash=payload_hash,
                                   report=result.model_dump(mode='json'), submitted_by=actor)
    session.add(saved)
    session.flush()
    audit(session, actor, row.id, 'SUBMIT_TRACED_DEMAND', data.reason,
          {'evidence_id': str(saved.id), 'payload_hash': payload_hash, 'status': 'PENDING'}, entity='purchase_approval')
    session.commit()
    return {'approval_id': row.id, 'evidence_id': saved.id, 'replayed': False}


def response(session, order, replayed=False):
    lines = []
    for item in repository.items(session, order.id):
        saved = session.get(PurchaseDemandEvidence, item.evidence_id)
        lines.append(OrderItemResponse(id=item.id, approval_id=item.approval_id, evidence_id=item.evidence_id,
                     consumable_id=item.consumable_id, planning_version_id=item.planning_version_id,
                     code=item.material_snapshot['code'], name=item.material_snapshot['name'], unit_id=item.unit_id,
                     unit_code=item.material_snapshot['unit_code'], ordered_quantity=item.ordered_quantity,
                     pending_quantity=None if order.status == 'ISSUED' else Decimal('0'), expected_delivery=item.expected_delivery,
                     pricing=item.pricing, line_value=item.line_value, approval_snapshot=item.approval_snapshot,
                     recommendation_evidence=saved.report))
    with localcontext() as ctx:
        ctx.prec = 80
        total = sum((line.line_value for line in lines), Decimal('0')) if all(line.line_value is not None for line in lines) else None
    return OrderResponse(id=order.id, po_number=order.po_number, supplier_id=order.supplier_id,
                         supplier_code=order.supplier_snapshot['code'], supplier_name=order.supplier_snapshot['name'],
                         po_date=order.po_date, status=order.status, created_at=order.created_at,
                         issued_at=order.issued_at, cancelled_at=order.cancelled_at, items=lines,
                         currency=next((line.pricing.currency for line in lines if line.pricing), None), total_value=total,
                         pending_basis={'DRAFT': 'NOT_COMMITTED', 'ISSUED': 'FULFILMENT_NOT_CONNECTED', 'CANCELLED': 'CANCELLED_DRAFT'}[order.status],
                         replayed=replayed,
                         history=[{'action': row.action, 'at': row.created_at.isoformat(), 'actor_id': str(row.actor_id),
                                   'reason': row.reason} for row in repository.history(session, order.id)])


@transactional
def create(session, data, actor, can_price):
    normalized = data.model_dump(mode='json')
    normalized['items'].sort(key=lambda row: row['approval_id'])
    payload_hash = digest(normalized)
    previous = session.scalar(select(PurchaseOrder).where(PurchaseOrder.creation_key == data.creation_key))
    if previous:
        if previous.payload_hash != payload_hash:
            raise ApplicationError('PO_KEY_CONFLICT', 'Creation key already has different content.', 409)
        return response(session, previous, True)
    if any(row.pricing for row in data.items) and not can_price:
        raise ApplicationError('PO_PRICING_DENIED', 'Explicit PO pricing permission is required to enter approved terms.', 403)
    sources = []
    for line in sorted(data.items, key=lambda row: str(row.approval_id)):
        approval = repository.approval(session, line.approval_id, lock=True)
        saved, material, unit, supplier = verified(session, approval)
        if supplier.id != data.supplier_id:
            raise ApplicationError('PO_SUPPLIER_MISMATCH', 'All lines must belong to the selected approved supplier.', 409)
        if line.ordered_quantity + repository.allocated(session, approval.id) > approval.approved_qty:
            raise ApplicationError('PO_APPROVED_QUANTITY_EXCEEDED', 'Quantity exceeds the unallocated approved demand, including existing drafts.', 409)
        whole_reviewed_override = approval.status == 'MODIFIED' and line.ordered_quantity == approval.approved_qty
        if not whole_reviewed_override and not satisfies_order_terms(line.ordered_quantity, saved.report['constraints']):
            raise ApplicationError('PO_SPLIT_CONSTRAINT_CONFLICT', 'This split violates the approved MOQ, pack, multiple or maximum order terms. Use a compliant quantity or obtain a reviewed whole-quantity override.', 409)
        sources.append((line, approval, saved, material, unit, supplier))
    identity = uuid4()
    order = PurchaseOrder(id=identity, po_number='PO-' + identity.hex.upper(), creation_key=data.creation_key,
                          payload_hash=payload_hash, supplier_id=data.supplier_id,
                          supplier_snapshot={'code': sources[0][-1].code, 'name': sources[0][-1].name},
                          po_date=data.po_date, status='DRAFT', reason=data.reason, created_by=actor)
    session.add(order)
    session.flush()
    for line, approval, saved, material, unit, supplier in sources:
        snapshot = approval_snapshot(approval)
        price = line.pricing
        session.add(PurchaseOrderItem(purchase_order_id=order.id, approval_id=approval.id, evidence_id=saved.id,
                    consumable_id=material.id, unit_id=unit.id, planning_version_id=approval.planning_version_id,
                    ordered_quantity=line.ordered_quantity, expected_delivery=line.expected_delivery,
                    approval_hash=digest(snapshot), approval_snapshot=snapshot,
                    material_snapshot={'code': material.code, 'name': material.name, 'unit_code': unit.code},
                    pricing=price.model_dump(mode='json') if price else None,
                    line_value=line_value(line.ordered_quantity, price.unit_rate, price.decimal_places, price.rounding) if price else None))
    audit(session, actor, order.id, 'CREATE_PO', data.reason, {'status': 'DRAFT', 'po_number': order.po_number})
    session.commit()
    return response(session, order)


@transactional
def transition(session, identity, action, data, actor):
    order = repository.order(session, identity, lock=True)
    if not order:
        raise ApplicationError('PO_NOT_FOUND', 'Purchase order does not exist.', 404)
    target = 'ISSUED' if action == 'ISSUE' else 'CANCELLED'
    if order.status == target:
        return response(session, order, True)
    if order.status != 'DRAFT':
        raise ApplicationError('PO_STATE_CONFLICT', 'Only drafts can be issued or cancelled. Issued cancellation requires the future fulfilment/reversal contract.', 409)
    for item in sorted(repository.items(session, identity), key=lambda row: str(row.approval_id)):
        approval = repository.approval(session, item.approval_id, lock=True)
        if action == 'ISSUE':
            verified(session, approval)
            if digest(approval_snapshot(approval)) != item.approval_hash:
                raise ApplicationError('PO_APPROVAL_CHANGED', 'Approval changed after drafting; cancel and recreate from the reviewed source.', 409)
            if repository.allocated(session, approval.id) > approval.approved_qty:
                raise ApplicationError('PO_APPROVED_QUANTITY_EXCEEDED', 'Allocated quantity exceeds current approval.', 409)
    now = datetime.now(timezone.utc)
    order.status = target
    if action == 'ISSUE':
        order.issued_by, order.issued_at = actor, now
    else:
        order.cancelled_by, order.cancelled_at = actor, now
    audit(session, actor, identity, action + '_PO', data.reason, {'status': target}, old={'status': 'DRAFT'})
    session.commit()
    return response(session, order)


@transactional
def get(session, identity):
    order = repository.order(session, identity)
    if not order:
        raise ApplicationError('PO_NOT_FOUND', 'Purchase order does not exist.', 404)
    return response(session, order)


@transactional
def list_orders(session, limit, offset):
    orders = session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id).limit(limit).offset(offset)).all()
    return [response(session, row) for row in orders]


@transactional
def eligible(session, limit, offset):
    approvals = session.scalars(select(PurchaseApproval).where(PurchaseApproval.status.in_(['APPROVED', 'MODIFIED']))
                               .order_by(PurchaseApproval.created_at.desc(), PurchaseApproval.id).limit(limit).offset(offset)).all()
    result = []
    for row in approvals:
        limitation, remaining = None, None
        try:
            verified(session, row)
            remaining = max(Decimal('0'), row.approved_qty - repository.allocated(session, row.id))
            if not remaining:
                limitation = 'Approved quantity is fully allocated.'
        except ApplicationError as error:
            limitation = error.message
        result.append(EligibleDemand(approval_id=row.id, supplier_id=row.supplier_id, supplier_name=row.supplier.name,
                      consumable_code=row.consumable.code, consumable_name=row.consumable.name, unit_code=row.uom,
                      approved_quantity=row.approved_qty, remaining_quantity=remaining, eligible=limitation is None, limitation=limitation))
    return result
