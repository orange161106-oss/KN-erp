import hashlib
import json
from datetime import timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.errors import ApplicationError
from app.domain.inventory_engine.projection import Event, Floor, calculate, condition
from app.models.audit import AuditLog
from app.models.projection import ProjectionInputSet
from app.repositories import projection as repository
from app.schemas.projection import ProjectionImportResult, ProjectionInputs, ProjectionReport, RequirementTotal
from app.services.plant_workflow import get_final_requirements


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def utc(value):
    # PostgreSQL supplies aware UTC; SQLite test storage loses its timezone marker.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def issue(code, message, blocking=True):
    return {'code': code, 'message': message, 'blocks_projection': blocking}


def context(session, material_id, version_id):
    material = repository.material(session, material_id)
    version = repository.version(session, version_id)
    if material is None or version is None:
        raise ApplicationError('PROJECTION_REFERENCE_NOT_FOUND', 'Consumable or planning version does not exist.', 404)
    totals = get_final_requirements(session, planning_version_id=version_id, consumable_id=material_id)
    # Keep source row identities/rule versions in evidence, rather than just a sum.
    calculations, adjustments, unit = repository.requirement_evidence(session, material_id, version_id, material.unit_id)
    manifest = {'version_id': str(version.id), 'status': version.status,
                'approved_at': None if version.approved_at is None else utc(version.approved_at).isoformat(),
                'approved_by': str(version.approved_by) if version.approved_by else None,
                'totals': sorted([row.model_dump(mode='json') for row in totals], key=lambda row: row['plant_id']),
                'calculations': [{'id': str(row.id), 'unit_id': str(row.unit_id), 'rule_id': str(row.rule_id),
                                  'rule_version': row.rule_version, 'prd_order_item_id': str(row.prd_order_item_id),
                                  'quantity': format(row.calculated_qty, '.4f')} for row in calculations],
                'adjustments': [{'id': str(row.id), 'plant_id': str(row.plant_id), 'uom': row.uom,
                                 'quantity': format(row.requested_qty, '.4f'), 'reviewed_by': str(row.reviewed_by),
                                 'reviewed_at': utc(row.reviewed_at).isoformat() if row.reviewed_at else None}
                                for row in adjustments]}
    limitations = []
    if version.approved_at is None or version.approved_by is None or version.status in {'DRAFT', 'SUPERSEDED'}:
        limitations.append(issue('FINAL_REQUIREMENT_NOT_APPROVED', 'The selected version lacks final approval evidence or is draft/superseded.'))
    if not totals:
        limitations.append(issue('REQUIREMENT_UNAVAILABLE', 'No final requirement is available for this material/version; absence is not zero demand.'))
    if any(row.unit_id != material.unit_id for row in calculations) or any(row.uom != unit.code for row in adjustments):
        limitations.append(issue('REQUIREMENT_UNIT_MISMATCH', 'Requirement source units do not match the stock unit.'))
    if any(row.final_required_qty < 0 for row in totals):
        limitations.append(issue('INVALID_FINAL_REQUIREMENT', 'A final requirement is negative.'))
    return material, version, totals, manifest, limitations


def canonical_payload(data):
    payload = data.model_dump(mode='json')
    if payload['demand'] is not None:
        payload['demand'].sort(key=lambda row: row['plant_id'])
        for row in payload['demand']:
            if row['events'] is not None:
                row['events'].sort(key=lambda event: event['source_id'])
    if payload['incoming'] is not None:
        payload['incoming'].sort(key=lambda row: row['source_id'])
    payload['msl_history'].sort(key=lambda row: row['effective_at'])
    return payload


def validate_reconciliation(data, totals):
    if data.demand is None:
        return
    authoritative = {row.plant_id: row.final_required_qty for row in totals}
    if {row.plant_id for row in data.demand} != set(authoritative):
        raise ApplicationError('DEMAND_SCOPE_MISMATCH', 'Demand must account for every plant in this material/version exactly once.', 409)
    for plan in data.demand:
        excluded = plan.fulfilled_quantity + plan.reserved_quantity
        total = authoritative[plan.plant_id]
        scheduled = sum((event.quantity for event in plan.events or []), Decimal('0'))
        if excluded > total or (plan.events is not None and excluded + scheduled != total):
            raise ApplicationError('DEMAND_RECONCILIATION_MISMATCH', 'Fulfilled, reserved and scheduled quantities must reconcile to the final requirement.', 409)


def import_inputs(session, data: ProjectionInputs, actor_id, *, enabled):
    if not enabled:
        raise ApplicationError('PROJECTION_IMPORT_DISABLED', 'Projection source imports are disabled until source mapping is verified.', 409)
    payload = canonical_payload(data)
    payload_hash = digest(payload)
    try:
        previous = repository.source_set(session, data.source_set_id)
        if previous:
            if previous.payload_hash != payload_hash:
                raise ApplicationError('PROJECTION_SOURCE_CONFLICT', 'This source-set identity has different content; immutable evidence cannot be overwritten.', 409)
            return ProjectionImportResult(id=previous.id, source_set_id=previous.source_set_id, imported_at=previous.imported_at, replayed=True)
        material, version, totals, manifest, _ = context(session, data.consumable_id, data.planning_version_id)
        snapshot = repository.latest_stock(session, data.consumable_id)
        if snapshot is None or snapshot.id != data.stock_snapshot_id or utc(snapshot.as_of) != data.reconciled_as_of:
            raise ApplicationError('STOCK_BASELINE_MISMATCH', 'Inputs must reconcile to the latest source stock snapshot and its exact timestamp.', 409)
        if data.unit_id != material.unit_id or snapshot.unit_id != data.unit_id:
            raise ApplicationError('UNIT_MISMATCH', 'All projection inputs must use the material stock unit.', 409)
        if data.lead_time and not repository.supplier_mapping_exists(session, material.id, data.lead_time.supplier_id):
            raise ApplicationError('SUPPLIER_MAPPING_MISSING', 'The lead-time supplier must be mapped to this consumable.', 409)
        validate_reconciliation(data, totals)
        record = ProjectionInputSet(source_set_id=data.source_set_id, consumable_id=material.id,
                                    planning_version_id=version.id, stock_snapshot_id=snapshot.id,
                                    payload_hash=payload_hash, requirement_fingerprint=digest(manifest),
                                    requirement_manifest=manifest, payload=payload, imported_by=actor_id)
        session.add(record)
        session.flush()
        session.add(AuditLog(actor_id=actor_id, action='IMPORT_PROJECTION_INPUTS', entity_type='projection_input_sets',
                             entity_id=record.id, old_values=None,
                             new_values={'source_set_id': record.source_set_id, 'payload_hash': payload_hash,
                                         'requirement_fingerprint': record.requirement_fingerprint,
                                         'stock_snapshot_id': str(snapshot.id)}, reason=data.import_reason))
        session.commit()
        return ProjectionImportResult(id=record.id, source_set_id=record.source_set_id, imported_at=record.imported_at, replayed=False)
    except IntegrityError:
        session.rollback()
        raise ApplicationError('PROJECTION_SOURCE_CONFLICT', 'A concurrent source import conflicts; retry the unchanged source set.', 409) from None
    except SQLAlchemyError:
        session.rollback()
        raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None
    except Exception:
        session.rollback()
        raise


def report(session, material_id, version_id, cutoff, source_set_id=None):
    try:
        return _report(session, material_id, version_id, cutoff, source_set_id)
    except SQLAlchemyError:
        raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None


def _report(session, material_id, version_id, cutoff, source_set_id):
    material, version, totals, manifest, limitations = context(session, material_id, version_id)
    snapshot = repository.latest_stock(session, material_id)
    record = repository.source_set(session, source_set_id) if source_set_id else None
    if source_set_id and record is None:
        raise ApplicationError('PROJECTION_SOURCE_NOT_FOUND', 'Projection source set does not exist.', 404)
    if record and (record.consumable_id != material_id or record.planning_version_id != version_id):
        raise ApplicationError('PROJECTION_SCOPE_MISMATCH', 'Source set belongs to another material or version.', 409)
    data = ProjectionInputs.model_validate(record.payload) if record else None
    baseline = utc(snapshot.as_of) if snapshot else None
    opening = snapshot.usable_quantity if snapshot else None
    if snapshot is None:
        limitations.append(issue('STOCK_UNAVAILABLE', 'No usable stock snapshot has been imported.'))
    elif cutoff <= baseline:
        raise ApplicationError('INVALID_PROJECTION_CUTOFF', 'Projection cutoff must follow the stock snapshot.', 422)
    if record and record.requirement_fingerprint != digest(manifest):
        limitations.append(issue('REQUIREMENT_INPUTS_CHANGED', 'Requirements or approval evidence changed after this source set; reconcile a new set.'))
    if record and (snapshot is None or record.stock_snapshot_id != snapshot.id):
        limitations.append(issue('STOCK_INPUTS_CHANGED', 'A newer stock snapshot requires a newly reconciled source set.'))
    if data is None:
        limitations.extend([issue('TIMING_UNCONFIRMED', 'Requirements are monthly totals; no approved dated demand schedule has been supplied.'),
                            issue('INCOMING_UNCONFIRMED', 'Confirmed incoming supply coverage has not been supplied; it is not assumed zero.'),
                            issue('RECONCILIATION_UNCONFIRMED', 'Fulfilled/reserved demand and received supply must be reconciled to the stock snapshot.')])
    else:
        if data.coverage_until < cutoff:
            limitations.append(issue('INPUT_COVERAGE_EXCEEDED', 'Requested cutoff exceeds verified source coverage.'))
        if data.demand is None or any(plan.events is None for plan in data.demand):
            limitations.append(issue('TIMING_UNCONFIRMED', 'No complete approved dated demand schedule exists; monthly totals are not spread.'))
        if data.incoming is None:
            limitations.append(issue('INCOMING_UNCONFIRMED', 'Incoming source data is missing; an explicit empty list is required for verified no incoming.'))
        if data.reconciliation_reference is None:
            limitations.append(issue('RECONCILIATION_UNCONFIRMED', 'No source evidence reconciles fulfilled/reserved demand and received supply to this snapshot.'))

    excluded, receipts, demands = [], [], []
    if data:
        for row in data.incoming or []:
            remaining = row.scheduled_quantity - row.received_quantity - row.cancelled_quantity
            excluded.append({'source_id': 'receipt:' + row.source_id, 'reason': 'ALREADY_RECEIVED_OR_CANCELLED', 'quantity': row.received_quantity + row.cancelled_quantity})
            if row.status != 'CONFIRMED':
                excluded.append({'source_id': 'receipt:' + row.source_id, 'reason': row.status, 'quantity': remaining})
            elif remaining:
                if row.available_at is None or baseline is None or row.available_at <= baseline:
                    limitations.append(issue('SUPPLY_TIMING_UNCONFIRMED', 'Outstanding confirmed supply has no usable-availability time after the baseline.'))
                else:
                    receipts.append(Event(row.source_id, row.available_at, remaining))
        for plan in data.demand or []:
            excluded.extend([{'source_id': str(plan.plant_id), 'reason': 'DEMAND_ALREADY_FULFILLED', 'quantity': plan.fulfilled_quantity},
                             {'source_id': str(plan.plant_id), 'reason': 'RESERVED_DEMAND_ALREADY_EXCLUDED_FROM_USABLE_STOCK', 'quantity': plan.reserved_quantity}])
            demands.extend(Event(event.source_id, event.at, event.quantity) for event in plan.events or [] if event.quantity)
    values = {'status': 'INCOMPLETE', 'cutoff': cutoff, 'opening_stock': opening}
    if data and snapshot and record.stock_snapshot_id == snapshot.id:
        effective = max((row for row in data.msl_history if row.effective_at <= baseline), key=lambda row: row.effective_at, default=None)
        values['current_msl'] = effective.quantity if effective else None
        values['current_msl_condition'] = condition(opening, values['current_msl'])
    if not any(row['blocks_projection'] for row in limitations):
        values = calculate(opening=opening, baseline=baseline, cutoff=cutoff, receipts=tuple(receipts), demands=tuple(demands),
                           floors=tuple(Floor(row.source_id, row.effective_at, row.quantity) for row in data.msl_history),
                           lead_time_at=data.lead_time.usable_at if data.lead_time else None)
    values['limitations'] = [*limitations, *values.get('limitations', [])]
    values['excluded'] = [*excluded, *values.get('excluded', [])]
    return ProjectionReport(**values, consumable_id=material.id, unit_id=material.unit_id,
                            planning_version_id=version.id, planning_period=version.planning_period,
                            stock_snapshot_id=snapshot.id if snapshot else None, stock_as_of=baseline,
                            source_set_id=record.source_set_id if record else None,
                            requirement_fingerprint=digest(manifest),
                            requirement_totals=[RequirementTotal(plant_id=row.plant_id, final_quantity=row.final_required_qty,
                                                                 is_fully_confirmed=row.is_fully_confirmed) for row in totals], inputs=data)
