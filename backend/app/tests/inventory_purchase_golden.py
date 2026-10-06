"""M7.2 replay tooling. Test-only fixtures; calculations use existing services.

Run from backend: python -m app.tests.inventory_purchase_golden --help
No application settings, .env files or operational databases are read.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter, field_validator, model_validator
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.auth import User
from app.models.inventory import StockSnapshot
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.plant_workflow import RequirementAdjustment
from app.models.prd import PlanningVersion
from app.models.production import Plant
from app.schemas.inventory import Input, Key, Quantity, SourceImport, Timestamp
from app.schemas.projection import DemandEvent, IncomingSupply, MslRevision, ProjectionInputs
from app.schemas.purchase_recommendation import PurchaseRequest, SupplierConstraints, TargetStock
from app.schemas.reorder import ReorderLeadTime, ReorderRequest, TimingPolicy
from app.services import inventory, projection, purchase_recommendation, reorder

DATA = Path(__file__).parent / 'data' / 'inventory_purchase'
IDS = {name: uuid4() for name in ('material', 'unit', 'supplier', 'version', 'snapshot')}
REQUIRED = {
    'stock': {'usable_quantity', 'as_of', 'source_export_id'},
    'projection': {'status', 'projected_stock', 'current_msl', 'current_msl_condition',
                   'projected_msl_condition', 'future_breach', 'first_future_breach_at', 'limitation_codes'},
    'reorder': {'status', 'reorder_required', 'already_breached', 'expected_msl_crossing_at',
                'latest_safe_order_at', 'latest_safe_order_inclusive',
                'earliest_usable_at_if_ordered_now', 'limitation_codes'},
    'purchase': {'status', 'final_requirement', 'current_stock', 'projected_stock_at_receipt',
                 'confirmed_incoming_before_receipt', 'msl_at_receipt', 'target_stock', 'raw_quantity',
                 'quantity_after_moq', 'combined_increment', 'candidate_quantity',
                 'recommended_quantity', 'stock_after_receipt', 'limitation_codes'},
}
QUANTITIES = {'usable_quantity', 'projected_stock', 'current_msl', 'projected_msl',
              'final_requirement', 'current_stock', 'projected_stock_at_receipt',
              'confirmed_incoming_before_receipt', 'msl_at_receipt', 'target_stock', 'raw_quantity',
              'quantity_after_moq', 'combined_increment', 'candidate_quantity',
              'recommended_quantity', 'stock_after_receipt', 'opening_stock',
              'lead_time_balance', 'balance_before', 'balance_after', 'receipts',
              'requirements', 'msl', 'quantity'}
DECIMAL_TEXT = re.compile(r'^-?\d+(?:\.\d{1,4})?$')


def validate_expectations(value):
    if isinstance(value, list):
        for item in value:
            validate_expectations(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in QUANTITIES and item is not None:
                if not isinstance(item, str) or not DECIMAL_TEXT.fullmatch(item):
                    raise ValueError(f'{key} requires exact decimal text, at most four places')
            elif (key.endswith('_at') or key in {'as_of', 'at'}) and item is not None:
                if not isinstance(item, str):
                    raise ValueError('Expected event times require aware ISO timestamp strings')
                TypeAdapter(Timestamp).validate_python(item)
            validate_expectations(item)


class Evidence(Input):
    kind: Literal['KNL_APPROVED', 'SYNTHETIC']
    input_reference: Key
    expected_reference: Key
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    approved_by: Key | None
    approved_at: Timestamp | None

    @model_validator(mode='after')
    def company_approval(self):
        if self.kind == 'KNL_APPROVED':
            if self.approved_by is None or self.approved_at is None:
                raise ValueError('Company cases require the KNL approver and approval timestamp')
            for value in (self.approved_by, self.input_reference, self.expected_reference):
                if value.upper() in {'TBD', 'UNKNOWN', 'PENDING', 'SYNTHETIC'}:
                    raise ValueError('Unconfirmed evidence cannot qualify as company approval')
        return self


class Snapshot(Input):
    source_snapshot_id: Key
    as_of: Timestamp
    usable_quantity: Quantity
    nonusable_excluded: Literal[True]
    reservations_excluded: Literal[True]

    @field_validator('nonusable_excluded', 'reservations_excluded', mode='before')
    @classmethod
    def explicit_exclusions(cls, value):
        if value is not True:
            raise ValueError('Usable-stock exclusions require explicit true values')
        return value


class StockExport(Input):
    export_id: Key
    generated_at: Timestamp
    snapshots: list[Snapshot] = Field(min_length=1, max_length=500)


class Demand(Input):
    plant: Key
    final_quantity: Quantity
    approval_reference: Key
    fulfilled_quantity: Quantity
    reserved_quantity: Quantity
    events: list[DemandEvent] | None


class Duration(ReorderLeadTime):
    # The replay creates a supplier fixture from the recorded supplier code.
    supplier_id: None = None


class ReorderInputs(Input):
    evaluated_at: Timestamp
    cutoff: Timestamp
    policy: TimingPolicy | None


class PurchaseInputs(Input):
    initiated_at: Timestamp
    receipt_at: Timestamp
    evidence_from: Timestamp
    evidence_until: Timestamp
    target: TargetStock | None
    constraints: SupplierConstraints


class GoldenCase(Input):
    case_id: Key
    description: Key
    evidence: Evidence
    material_code: Key = Field(max_length=64)
    unit_code: Key = Field(max_length=16)
    supplier_code: Key = Field(max_length=64)
    planning_period: str = Field(pattern=r'^\d{4}-(?:0[1-9]|1[0-2])$')
    stock_imports: list[StockExport] = Field(min_length=1, max_length=100)
    reconciled_as_of: Timestamp
    coverage_until: Timestamp
    reconciliation_reference: Key | None
    demand: list[Demand] = Field(min_length=1, max_length=500)
    incoming: list[IncomingSupply] | None
    msl_history: list[MslRevision]
    lead_time: Duration | None
    reorder: ReorderInputs
    purchase: PurchaseInputs
    expected: dict[str, dict]

    @model_validator(mode='after')
    def validate_case(self):
        if len({row.plant for row in self.demand}) != len(self.demand):
            raise ValueError('Record each plant final requirement exactly once')
        if set(self.expected) != set(REQUIRED):
            raise ValueError('Expected results must cover stock, projection, reorder and purchase')
        for scope, required in REQUIRED.items():
            if missing := required - self.expected[scope].keys():
                raise ValueError(f'Missing independent expectations for {scope}: {sorted(missing)}')
        validate_expectations(self.expected)
        # Validate the existing API contracts before creating a fixture database.
        for export in self.stock_imports:
            stock_payload(export, IDS)
        plants = {row.plant: uuid4() for row in self.demand}
        projection_payload(self, IDS, plants)
        reorder_payload(self, IDS)
        purchase_payload(self, IDS)
        return self


class CaseSet(Input):
    schema_version: Literal['M7.2_V1']
    suite: Literal['KNL_APPROVED', 'SYNTHETIC']
    cases: list[GoldenCase]

    @model_validator(mode='after')
    def unique_and_approved(self):
        if len({row.case_id for row in self.cases}) != len(self.cases):
            raise ValueError('Duplicate case identities')
        if any(row.evidence.kind != self.suite for row in self.cases):
            raise ValueError('Synthetic cases cannot be included in the company acceptance suite')
        return self


def stock_payload(export, ids):
    value = export.model_dump(mode='json')
    return SourceImport.model_validate({**value, 'import_reason': 'Isolated M7.2 replay',
        'snapshots': [{**row, 'consumable_id': ids['material'], 'unit_id': ids['unit']}
                      for row in value['snapshots']]})


def duration(case, ids):
    if case.lead_time is None:
        return None
    return {**case.lead_time.model_dump(mode='json'), 'supplier_id': ids['supplier']}


def projection_payload(case, ids, plants):
    return ProjectionInputs.model_validate({
        'source_set_id': case.case_id, 'source_reference': case.evidence.input_reference,
        'import_reason': 'Isolated M7.2 replay', 'planning_version_id': ids['version'],
        'stock_snapshot_id': ids['snapshot'], 'consumable_id': ids['material'], 'unit_id': ids['unit'],
        'reconciled_as_of': case.reconciled_as_of, 'coverage_until': case.coverage_until,
        'reconciliation_reference': case.reconciliation_reference,
        'demand': [{**row.model_dump(exclude={'plant', 'final_quantity', 'approval_reference'}),
                    'plant_id': plants[row.plant]} for row in case.demand],
        'incoming': case.incoming, 'msl_history': case.msl_history,
    })


def reorder_payload(case, ids):
    return ReorderRequest.model_validate({**case.reorder.model_dump(), 'consumable_id': ids['material'],
        'planning_version_id': ids['version'], 'source_set_id': case.case_id, 'lead_time': duration(case, ids)})


def purchase_payload(case, ids):
    return PurchaseRequest.model_validate({**case.purchase.model_dump(), 'consumable_id': ids['material'],
        'planning_version_id': ids['version'], 'source_set_id': case.case_id, 'supplier_id': ids['supplier'],
        'unit_id': ids['unit'], 'lead_time': duration(case, ids)})


@contextmanager
def isolated_session():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def configure(connection, record):
        connection.create_function('btrim', 1, lambda value: value.strip())
        connection.execute('PRAGMA foreign_keys=ON')

    try:
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()


def replay(case, session):
    """Seed supplied final demand, then call stock/projection/reorder/purchase services.

    Final demand is injected as an already-approved upstream fixture; this does
    not validate upstream requirement formulas or grant real approval authority.
    """
    actor = User(username='golden_replay', password_hash='unusable-fixture-hash', is_active=False)
    unit = Unit(code=case.unit_code.upper(), name=case.unit_code)
    supplier = Supplier(code=case.supplier_code.upper(), name=case.supplier_code)
    session.add_all([actor, unit, supplier])
    session.flush()
    material = Consumable(code=case.material_code.upper(), name=case.material_code, unit_id=unit.id)
    version = PlanningVersion(planning_period=case.planning_period, version_number=1,
        source_filename='M7.2 supplied final requirement', status='RELEASED_TO_PLANTS',
        created_by=actor.id, approved_by=actor.id, approved_at=case.reconciled_as_of)
    session.add_all([material, version])
    session.flush()
    session.add(SupplierConsumable(consumable_id=material.id, supplier_id=supplier.id))
    plants = {}
    for row in case.demand:
        plant = Plant(name=row.plant)
        session.add(plant)
        session.flush()
        plants[row.plant] = plant.id
        session.add(RequirementAdjustment(planning_version_id=version.id, plant_id=plant.id,
            consumable_id=material.id, category='SPECIAL', requested_qty=row.final_quantity, uom=unit.code,
            reason=row.approval_reference, requested_by=actor.id, status='APPROVED',
            reviewed_by=actor.id, reviewed_at=case.reconciled_as_of))
    session.commit()
    ids = dict(material=material.id, unit=unit.id, supplier=supplier.id, version=version.id)
    for export in case.stock_imports:
        inventory.import_source(session, stock_payload(export, ids), actor.id, enabled=True)
    # Select only the supplied reconciliation timestamp, never a computed expected balance.
    ids['snapshot'] = session.scalar(select(StockSnapshot.id).where(
        StockSnapshot.consumable_id == material.id, StockSnapshot.as_of == case.reconciled_as_of))
    if ids['snapshot'] is None:
        raise ValueError('Reconciliation timestamp has no supplied stock snapshot')
    projection.import_inputs(session, projection_payload(case, ids, plants), actor.id, enabled=True)
    results = {
        'stock': inventory.get_balance(session, material.id),
        'projection': projection.report(session, material.id, version.id, case.reorder.cutoff, case.case_id),
        'reorder': reorder.report(session, reorder_payload(case, ids)),
        'purchase': purchase_recommendation.report(session, purchase_payload(case, ids)),
    }
    # SQLite loses timezone markers on stored DateTime values. The fixture input
    # was validated/normalized to UTC; PostgreSQL does not need this adaptation.
    balance = results['stock']
    if balance.as_of is not None and balance.as_of.tzinfo is None:
        results['stock'] = balance.model_copy(update={'as_of': balance.as_of.replace(tzinfo=timezone.utc)})
    actual = {scope: value.model_dump(mode='json') for scope, value in results.items()}
    for scope in ('projection', 'reorder', 'purchase'):
        actual[scope]['limitation_codes'] = sorted(row['code'] for row in actual[scope]['limitations'])
    return actual


def compare(expected, actual):
    """Return every difference; absent fields never match an expected null."""
    differences = []

    def record(path, wanted, observed, present):
        differences.append({'field': path, 'expected': wanted, 'actual': observed,
                            'actual_field_present': present, 'investigation': 'OPEN'})

    def visit(wanted, observed, present, path, key=''):
        if isinstance(wanted, dict) and (not present or isinstance(observed, dict)):
            for name, value in wanted.items():
                exists = present and name in observed
                visit(value, observed[name] if exists else None, exists,
                      f'{path}.{name}' if path else name, name)
            return
        if isinstance(wanted, list) and isinstance(observed, list) and present:
            if len(wanted) != len(observed):
                record(path + '.length', len(wanted), len(observed), True)
            for index, value in enumerate(wanted):
                exists = index < len(observed)
                visit(value, observed[index] if exists else None, exists, f'{path}[{index}]')
            return
        match = present
        if present and wanted is not None and observed is not None and key in QUANTITIES:
            match = isinstance(observed, str) and Decimal(wanted) == Decimal(observed)
        elif present and wanted is not None and observed is not None and (key.endswith('_at') or key in {'as_of', 'at'}):
            adapter = TypeAdapter(Timestamp)
            match = adapter.validate_python(wanted) == adapter.validate_python(observed)
        elif present:
            match = type(wanted) is type(observed) and wanted == observed
        if not match:
            record(path, wanted, observed, present)

    visit(expected, actual, True, '')
    return differences


def load_cases(path):
    def reject_float(value):
        raise ValueError('Decimal quantities must be JSON strings; binary float is forbidden')

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    raw = json.loads(Path(path).read_text(encoding='utf-8'), parse_float=reject_float,
                     parse_constant=reject_float, object_pairs_hook=unique_keys)
    return CaseSet.model_validate(raw)


def evaluate(cases):
    results = []
    for case in cases.cases:
        entry = {'case_id': case.case_id, 'description': case.description,
                 'evidence': case.evidence.model_dump(mode='json'),
                 'inputs': case.model_dump(mode='json', exclude={'expected'}), 'expected': case.expected}
        try:
            with isolated_session() as session:
                entry['actual'] = replay(case, session)
            entry['differences'] = compare(case.expected, entry['actual'])
            entry['status'] = 'DIFFERENCE' if entry['differences'] else 'MATCH'
        except Exception as error:
            entry.update(status='REPLAY_ERROR', error=f'{type(error).__name__}: {error}', investigation='OPEN')
        results.append(entry)
    ready = bool(results)
    passed = ready and all(row['status'] == 'MATCH' for row in results)
    return {'schema_version': 'M7.2_V1', 'suite': cases.suite,
            'status': 'MATCH' if passed else ('DIFFERENCE' if ready else 'NOT_READY'),
            'company_acceptance': ('PASS' if passed else 'FAIL')
                if ready and cases.suite == 'KNL_APPROVED' else 'PENDING',
            'executed_at': datetime.now(timezone.utc).isoformat(),
            'engine_versions': sorted({result['engine_version'] for row in results
                for scope, result in row.get('actual', {}).items()
                if scope != 'stock' and 'engine_version' in result}),
            'database': 'ISOLATED_SQLITE', 'case_count': len(results),
            'difference_count': sum(len(row.get('differences', [])) for row in results),
            'replay_error_count': sum(row['status'] == 'REPLAY_ERROR' for row in results), 'cases': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DATA / 'company_cases.json')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.cases)
        result = evaluate(cases)
        result['case_file_sha256'] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    except (ValueError, OSError) as error:
        result = {'status': 'INVALID_CASES', 'company_acceptance': 'PENDING',
                  'error': str(error), 'case_count': 0}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{result['status']}: {result['case_count']} cases; company acceptance {result['company_acceptance']}")
    return 0 if result['status'] == 'MATCH' else (2 if result['status'] in {'NOT_READY', 'INVALID_CASES'} else 1)


if __name__ == '__main__':
    raise SystemExit(main())
