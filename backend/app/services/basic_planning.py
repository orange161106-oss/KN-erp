"""Central, source-traced basic demand. Inventory arithmetic stays in M4.2/M5.1."""
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.core.errors import ApplicationError
from app.domain.rules import RuleCalculationInput, RuleDomainError, RuleType, RoundingPolicy, evaluate_rule
from app.models.audit import AuditLog
from app.models.masters import Product
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderItem, PRDRecord
from app.models.requirements import CalculatedRequirement, RequirementCalculationError
from app.services.basic_norms import applicable_norms, load_product_norms, match_product
from app.services import prd_source

WORKFLOW = 'BASIC_CENTRAL_V1'


def ensure_schema(db):
    if db.get_bind().dialect.name != 'postgresql':
        return
    nullable = db.scalar(text("SELECT is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='calculated_requirements' AND column_name='plant_id'"))
    checks = db.scalars(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='prd_order_items'::regclass AND contype='c'"))
    zero_allowed = any(re.search(r'planned_quantity\s*>=\s*\(?0', rule) for rule in checks)
    if nullable != 'YES' or not zero_allowed:
        raise ApplicationError('CENTRAL_DATABASE_SETUP_REQUIRED', 'Central planning needs its database update before records can be saved. Ask the administrator to apply the prepared update.', 503,
            details={'migration': 'c001_central_basic_planning'})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def is_central_version(db, version_id):
    batch = db.scalar(select(ImportBatch).where(ImportBatch.planning_version_id == version_id))
    return bool(batch and (batch.validation_summary or {}).get('workflow') == WORKFLOW)


def _production_unit(item, product, batch):
    """Recover only the proven old schedule parser's fabricated 'Nos' default.

    No unit conversion or PCS/NOS equivalence is assumed. Other import formats
    retain explicit unit checks and original production evidence.
    """
    metadata = (batch.validation_summary or {}) if batch else {}
    old_schedule = (metadata.get('workflow') == WORKFLOW
        and {'blocks_count', 'grand_total', 'planning_period', 'revision'} <= metadata.keys()
        and 'production_unit_source' not in metadata
        and 'as_of_date' not in metadata)
    if product and old_schedule and item.uom.strip().casefold() == 'nos':
        return product.uom, 'LEGACY_SCHEDULE_PRODUCT_MASTER'
    return item.uom, metadata.get('production_unit_source', 'REVIEWED_SOURCE')


def versions(db):
    other = aliased(PlanningVersion)
    latest = select(func.max(other.version_number)).where(
        other.planning_period == PlanningVersion.planning_period).scalar_subquery()
    central = select(ImportBatch.id).where(ImportBatch.planning_version_id == PlanningVersion.id,
        ImportBatch.validation_summary['workflow'].as_string() == WORKFLOW).exists()
    records = db.execute(select(PlanningVersion, latest).where(central)
        .order_by(PlanningVersion.planning_period.desc(), PlanningVersion.version_number.desc()))
    return [{'id': v.id, 'planning_period': v.planning_period, 'revision_label': v.revision_label,
        'status': v.status, 'source_filename': v.source_filename, 'approved_at': v.approved_at,
        'is_latest': v.version_number == latest_number} for v, latest_number in records]


def workspace(db, version_id=None):
    """Load available revisions and their selected saved results in one request."""
    from app.services.requirements import get_calculated_requirements, get_calculation_errors
    from app.services.plant_workflow import get_final_requirements
    available = versions(db)
    selected = next((row for row in available if row['id'] == version_id), None) if version_id else (
        next((row for row in available if row['is_latest']), available[0] if available else None))
    if version_id and selected is None:
        raise ApplicationError('CENTRAL_VERSION_REQUIRED', 'Choose a central production revision.', 404)
    return {'versions': available, 'selected_version_id': selected['id'] if selected else None,
        'results': {'calculations': get_calculated_requirements(db, selected['id']),
            'errors': get_calculation_errors(db, selected['id']),
            'summary': get_final_requirements(db, planning_version_id=selected['id'])} if selected else None}


def _source(content, filename, sheet_name):
    if not content or len(content) > 10 * 1024 * 1024:
        raise ApplicationError('INVALID_SOURCE_FILE', 'Choose a nonempty file of at most 10 MB.', 422)
    if filename.lower().endswith('.csv'):
        try:
            rows = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        except (UnicodeError, csv.Error):
            raise ApplicationError('INVALID_SOURCE_FILE', 'Use a UTF-8 CSV file.', 422) from None
        if len(rows) > 20000 or any(len(row) > 128 for row in rows):
            raise ApplicationError('SOURCE_TOO_LARGE', 'Use at most 20000 rows and 128 columns.', 422)
        return 'CSV', rows
    from app.services.product_source import source_rows
    return sheet_name, source_rows(content, filename, sheet_name)


def production_preview(db, content, filename, sheet_name, period, revision, as_of):
    """Reuse strict revision parser and the existing company-block reconciliation."""
    sheet, rows = _source(content, filename, sheet_name)
    source = prd_source.parse(rows, period, revision)
    period, revision = source[0]['period'], source[0]['revision']
    customers, errors, blocks = {}, [], []
    # Flat exports have no company banners. Hierarchical schedules retain exact aliases and totals.
    from app.services.product_source import identity_headers
    header, columns = identity_headers(rows)
    identity_columns = [columns[key] for key in ('part_number', 'item_id', 'code') if key in columns]
    grouped = any(not any(index < len(row) and str(row[index] or '').strip() for index in identity_columns)
        and any('TOTAL' in str(cell or '').upper() for cell in row[:4]) for row in rows[header + 1:])
    if grouped:
        from app.services.sales_schedule_parser import parse_sales_schedule_data
        parsed = parse_sales_schedule_data(rows, db, period, revision, seed_defaults=False)
        errors.extend(parsed['errors'])
        blocks = parsed['blocks']
        for block in blocks:
            for key, reported in block['sheet_totals'].items():
                if Decimal(reported) != Decimal(block['quantities'].get(key, '0')):
                    errors.append(f"Company subtotal does not reconcile: {block['heading_text']} ({key}).")
        grand = parsed['grand_total']
        for key, reported in grand['sheet_grand_total'].items():
            if Decimal(reported) != Decimal(grand['parts_sum'].get(key, '0')):
                errors.append(f'Grand total does not reconcile ({key}).')
        customers = {row['source_row']: row for row in parsed['_all_flat_rows']}
        if set(customers) != {row['source_row_number'] for row in source}:
            errors.append('Company sections do not account for every source product row exactly once.')
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))))
    norms = load_product_norms(db, [p.id for p in products])
    result, seen = [], defaultdict(list)
    for row in source:
        product, issue = match_product(products, part_number=row['part_number'], item_id=row['item_id'], code=row['code'])
        row_errors, norm_errors, matched = [], [], []
        if issue:
            row_errors.append({'code': issue, 'message': 'Choose one exact active Product Master matching all source identifiers.'})
        if product:
            if row['uom'] and row['uom'].casefold() != product.uom.casefold():
                row_errors.append({'code': 'PRD_UNIT_MISMATCH', 'message': 'Source production unit differs from Product Master.'})
            matched, norm_errors = applicable_norms(norms, product.id, as_of)
            seen[product.id].append(row['source_row_number'])
        customer = customers.get(row['source_row_number'], {})
        result.append({'source_row_number': row['source_row_number'], 'part_number': row['part_number'],
            'item_id': row['item_id'], 'product_id': str(product.id) if product else None,
            'product_code': product.code if product else row['code'], 'product_name': product.name if product else '',
            'quantity': str(row['quantity']), 'unit': product.uom if product else row['uom'],
            'customer': customer.get('customer'), 'customer_id': customer.get('customer_id'),
            'customer_code': customer.get('customer_code'), 'customer_group': customer.get('customer_group'),
            'section_type': customer.get('section_type', 'STANDARD'), 'schedule_given_on': customer.get('schedule_given_on'),
            'norm_count': len(matched), 'errors': row_errors, 'norm_errors': norm_errors})
    for row in result:
        duplicates = seen.get(UUID(row['product_id']), []) if row['product_id'] else []
        if len(duplicates) > 1:
            row['errors'].append({'code': 'DUPLICATE_PRD_ITEM', 'message': 'Product repeats in source rows ' + ', '.join(map(str, duplicates)) + '. Review instead of silently summing.'})
    response = {'workflow': WORKFLOW, 'filename': filename[:255], 'sheet_name': sheet,
        'planning_period': period, 'revision_label': revision, 'as_of_date': str(as_of),
        'source_sha256': hashlib.sha256(content).hexdigest(), 'rows': result, 'blocks': blocks,
        'errors': errors, 'can_confirm': bool(result) and not errors and not any(row['errors'] for row in result),
        'norm_ready': bool(result) and not any(row['norm_errors'] for row in result)}
    response['review_token'] = digest(response)
    return response


def production_confirm(db, content, filename, sheet, period, revision, as_of, review_token, actor):
    preview = production_preview(db, content, filename, sheet, period, revision, as_of)
    try:
        ensure_schema(db)
        if db.get_bind().dialect.name == 'postgresql':
            key = int.from_bytes(hashlib.sha256(preview['planning_period'].encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
        existing = db.scalar(select(PlanningVersion).where(PlanningVersion.planning_period == preview['planning_period'],
            PlanningVersion.version_number == prd_source.revision(preview['revision_label'])))
        if existing:
            batch = db.scalar(select(ImportBatch).where(ImportBatch.planning_version_id == existing.id))
            if (batch and batch.file_hash == preview['source_sha256']
                and (batch.validation_summary or {}).get('review_token') == review_token
                and (batch.validation_summary or {}).get('as_of_date') == str(as_of)):
                return {'planning_version_id': existing.id, 'imported_count': batch.row_count, 'replayed': True}
            raise ApplicationError('PRD_REVISION_EXISTS', 'This month/revision already exists. Preserve it and import a new revision for changes.', 409)
        if review_token != preview['review_token']:
            raise ApplicationError('STALE_PRODUCTION_PREVIEW', 'The source, masters or norms changed. Preview and review again.', 409)
        if not preview['can_confirm']:
            raise ApplicationError('PRODUCTION_REVIEW_REQUIRED', 'Resolve every source error before confirming. No rows were saved.', 422)
        staged, workspace = [], []
        for row in preview['rows']:
            staged.append({'product_code': row['product_code'], 'product_id': row['product_id'], 'plant_code': '',
                'planned_quantity': row['quantity'], 'uom': row['unit'], 'target_period': preview['planning_period'],
                'source_row_number': row['source_row_number'], 'customer_id': row['customer_id']})
            workspace.append(PRDRecord(id=uuid4(), row_index=row['source_row_number'], plant='', product_code=row['product_code'],
                description=row['product_name'], planned_quantity=Decimal(row['quantity']), uom=row['unit'],
                target_period=preview['planning_period'], planning_version=preview['revision_label'], revision=preview['revision_label'],
                customer=row['customer'], customer_id=UUID(row['customer_id']) if row['customer_id'] else None,
                customer_code=row['customer_code'], customer_group=row['customer_group'], section_type=row['section_type'],
                schedule_given_on=datetime.fromisoformat(row['schedule_given_on']) if row['schedule_given_on'] else None,
                source_row=row['source_row_number'], status='VALIDATED', created_by=actor))
        batch = ImportBatch(filename=filename[:255], file_size_bytes=len(content), uploaded_by=actor, status='VALIDATED',
            row_count=len(staged), valid_row_count=len(staged), error_row_count=0, staged_data=staged, file_hash=preview['source_sha256'],
            validation_summary={'workflow': WORKFLOW, 'review_token': review_token, 'as_of_date': str(as_of), 'sheet_name': sheet, 'source_rows': preview['rows']})
        db.add(batch); db.add_all(workspace); db.flush()
        from app.services.prd import promote_batch_to_planning_version
        version, _, _ = promote_batch_to_planning_version(db, batch.id, actor, preview['planning_period'], preview['revision_label'], commit=False)
        db.add(AuditLog(actor_id=actor, action='IMPORT_CENTRAL_PRODUCTION', entity_type='planning_version', entity_id=version.id,
            new_values={'workflow': WORKFLOW, 'source_sha256': preview['source_sha256'], 'row_count': len(staged)},
            reason='Explicitly confirmed production preview; central Super Admin review'))
        db.commit()
        return {'planning_version_id': version.id, 'imported_count': len(staged), 'replayed': False}
    except IntegrityError:
        db.rollback()
        raise ApplicationError('PRODUCTION_IMPORT_CONFLICT', 'A concurrent import saved this revision. Reload before retrying.', 409) from None
    except Exception:
        db.rollback()
        raise


def preview(db, version_id, as_of):
    version = db.get(PlanningVersion, version_id)
    batch = db.scalar(select(ImportBatch).where(ImportBatch.planning_version_id == version_id))
    if not version or not batch or (batch.validation_summary or {}).get('workflow') != WORKFLOW:
        raise ApplicationError('CENTRAL_VERSION_REQUIRED', 'Choose a central production revision.', 404)
    items = list(db.scalars(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == version_id).order_by(PRDOrderItem.source_row_number)))
    products = list(db.scalars(select(Product).where(Product.id.in_({row.product_id for row in items if row.product_id}))))
    norms = load_product_norms(db, [p.id for p in products])
    
    seen_norm_keys = defaultdict(list)
    for n in norms:
        if n.is_active and not (n.parameters or {}).get('is_general'):
            seen_norm_keys[(n.product_id, n.process_id, n.consumable_id)].append(n)
    duplicate_groups_count = sum(1 for choices in seen_norm_keys.values() if len(choices) > 1)

    calculations, errors, sources = [], [], []
    no_consumption_norms = []

    for item in items:
        # For each product row where R0 == 0 or blank: skip (requirement = 0, no error)
        if item.planned_quantity == 0 or item.planned_quantity is None:
            sources.append({
                'id': item.id, 'source_row_number': item.source_row_number, 'product_code': item.product_code,
                'production_quantity': item.planned_quantity or Decimal('0'), 'unit': item.uom, 'norm_count': 0, 'matched': True
            })
            continue

        product, issue = match_product(products, product_id=item.product_id, code=item.product_code)
        production_unit, unit_source = _production_unit(item, product, batch)
        if issue:
            selected, issues = [], [{'code': issue, 'message': 'The source product is missing, inactive or its code changed.'}]
        else:
            selected, issues = applicable_norms(norms, product.id, as_of, ignore_dates=True, allow_duplicates=True, allow_missing=True)
            if not selected and not issues:
                no_consumption_norms.append({
                    'prd_order_item_id': str(item.id),
                    'source_row_number': item.source_row_number,
                    'product_id': str(product.id) if product else None,
                    'product_code': product.code,
                    'part_number': product.part_number or item.product_code,
                    'item_id': product.item_id,
                    'part_description': product.name,
                    'planned_quantity': item.planned_quantity,
                    'unit': item.uom,
                })
        if product and production_unit.strip().casefold() != product.uom.strip().casefold():
            issues.append({'code': 'PRODUCTION_UNIT_CHANGED', 'message': 'Production unit differs from the reviewed master. Reconcile a new production revision.'})
        for issue in issues:
            errors.append({'prd_order_item_id': item.id, 'source_row_number': item.source_row_number, 'product_id': item.product_id,
                'product_code': item.product_code, **issue})
        sources.append({'id': item.id, 'source_row_number': item.source_row_number, 'product_code': item.product_code,
            'production_quantity': item.planned_quantity, 'unit': production_unit, 'norm_count': len(selected), 'matched': not issues and bool(selected)})
        for norm in selected:
            sch_val = Decimal(str(norm.parameters.get('sch') if norm.parameters.get('sch') is not None else norm.parameters.get('rate', '0')))
            params = {**norm.parameters, 'rate': str(sch_val)}
            try:
                result = evaluate_rule(RuleCalculationInput(rule_type=RuleType(norm.rule_type), rule_version=norm.version,
                    parameters=params, production_quantity=item.planned_quantity, unit=norm.unit.code,
                    rounding_policy=RoundingPolicy.parse(norm.rounding_policy), rounding_precision=norm.rounding_precision))
                if result.final_calculated_requirement > Decimal('9999999999.9999') or result.raw_requirement > Decimal('9999999999.9999'):
                    raise ApplicationError('REQUIREMENT_TOO_LARGE', 'Calculated requirement exceeds the supported stored quantity.', 422)
                if result.final_calculated_requirement != result.final_calculated_requirement.quantize(Decimal('0.0001')):
                    raise ApplicationError('APPROVED_ROUNDING_REQUIRED', 'The final result has more than four decimal places. Choose an approved rounding policy on the norm before saving demand.', 422)
            except (RuleDomainError, ApplicationError) as failure:
                errors.append({'prd_order_item_id': item.id, 'source_row_number': item.source_row_number, 'product_id': item.product_id,
                    'product_code': item.product_code, 'consumable_id': norm.consumable_id, 'code': failure.code, 'message': failure.message})
                continue
            except (ValueError, ArithmeticError) as failure:
                errors.append({'prd_order_item_id': item.id, 'source_row_number': item.source_row_number, 'product_id': item.product_id,
                    'product_code': item.product_code, 'consumable_id': norm.consumable_id, 'code': 'INVALID_NORM_PARAMETERS',
                    'message': 'The stored formula parameters are invalid. Review the norm before calculating.'})
                continue
            calculations.append({'prd_order_item_id': item.id, 'source_row_number': item.source_row_number, 'product_id': product.id,
                'product_code': product.code, 'product_name': product.name, 'process_id': norm.process_id, 'process_name': norm.process.name if norm.process else '',
                'consumable_id': norm.consumable_id, 'consumable_code': norm.consumable.code, 'consumable_name': norm.consumable.name,
                'rule_id': norm.id, 'rule_type': norm.rule_type, 'rule_version': norm.version, 'parameters': norm.parameters,
                'sch': sch_val, 'source_production_qty': item.planned_quantity, 'raw_requirement': result.raw_requirement,
                'rounding_policy': result.rounding_policy.value, 'rounding_precision': result.rounding_precision,
                'calculated_qty': result.final_calculated_requirement, 'unit_id': norm.unit_id, 'uom': norm.unit.code,
                'calculation_steps': [step.model_dump(mode='json') for step in result.calculation_steps]})
            calculations[-1]['production_unit_source'] = unit_source
            calculations[-1]['source_production_unit'] = item.uom
            calculations[-1]['production_unit'] = production_unit
    totals = {}
    for row in calculations:
        key = row['consumable_id']
        if key not in totals:
            totals[key] = {name: row[name] for name in ('consumable_id', 'consumable_code', 'consumable_name', 'uom')}
            totals[key].update(
                total_raw_requirement=Decimal('0'),
                total_calculated_qty=Decimal('0'),
                total_basic_requirement=Decimal('0'),
                line_items_count=0,
                parts_breakdown=[]
            )
        totals[key]['total_raw_requirement'] += row['raw_requirement']
        totals[key]['total_calculated_qty'] += row['calculated_qty']
        totals[key]['total_basic_requirement'] += row['calculated_qty']
        totals[key]['line_items_count'] += 1
        totals[key]['parts_breakdown'].append({
            'source_row_number': row['source_row_number'],
            'product_code': row['product_code'],
            'product_name': row['product_name'],
            'production_quantity': row['source_production_qty'],
            'sch': row['sch'],
            'line_requirement': row['calculated_qty'],
            'process_name': row['process_name']
        })
    duplicate_groups_warning = (
        f"{duplicate_groups_count} norm groups in Consumption Norms share the same Part No, Process and Consumable. "
        "Both were included in the calculation. If this is unexpected, review duplicate norms in Consumption Norms."
        if duplicate_groups_count > 0 else None
    )
    missing_parts_qty = sum((row['planned_quantity'] for row in no_consumption_norms), Decimal('0'))
    value = {
        'planning_version_id': version.id,
        'planning_period': version.planning_period,
        'revision_label': version.revision_label,
        'status': version.status,
        'as_of_date': as_of,
        'complete': bool(items) and not errors and not no_consumption_norms,
        'has_missing_norms': bool(no_consumption_norms),
        'missing_parts_count': len(no_consumption_norms),
        'missing_parts_qty': missing_parts_qty,
        'no_consumption_norms': no_consumption_norms,
        'duplicate_norm_groups_count': duplicate_groups_count,
        'duplicate_groups_warning': duplicate_groups_warning,
        'sources': sources,
        'calculations': calculations,
        'summary_by_consumable': sorted(totals.values(), key=lambda r: r['consumable_code']),
        'errors': errors
    }
    value['review_token'] = digest(value)
    return value


def calculate(db, req, actor):
    """Persist the same preview evidence in the existing authoritative tables."""
    from app.services.requirements import get_calculation_errors
    from app.schemas.requirements import RequirementCalculationRunResponse
    try:
        ensure_schema(db)
        version = db.scalar(select(PlanningVersion).where(PlanningVersion.id == req.planning_version_id).with_for_update())
        latest = db.scalar(select(PlanningVersion).where(PlanningVersion.planning_period == version.planning_period)
            .order_by(PlanningVersion.version_number.desc()).limit(1))
        if version.id != latest.id:
            raise ApplicationError('LATEST_REVISION_REQUIRED', 'Calculate the latest production revision; older revisions remain history.', 409)
        if version.status not in {'VALIDATED', 'CALCULATED', 'CALCULATED_WITH_ERRORS'} or version.approved_at:
            raise ApplicationError('CALCULATION_HISTORY_PROTECTED', 'Approved calculations cannot be replaced. Import a new production revision.', 409)
        batch = db.scalar(select(ImportBatch).where(ImportBatch.planning_version_id == version.id))
        recorded_date = (batch.validation_summary or {}).get('as_of_date')
        effective_date = req.as_of_date or (date.fromisoformat(recorded_date) if recorded_date else date.today())
        data = preview(db, version.id, effective_date)
        db.execute(delete(CalculatedRequirement).where(CalculatedRequirement.planning_version_id == version.id))
        db.execute(delete(RequirementCalculationError).where(RequirementCalculationError.planning_version_id == version.id))
        consolidated = {}
        for row in data['calculations']:
            key = (str(row['prd_order_item_id']), str(row['process_id']), str(row['consumable_id']))
            if key not in consolidated:
                consolidated[key] = {
                    'planning_version_id': version.id,
                    'plant_id': None,
                    'prd_order_item_id': UUID(str(row['prd_order_item_id'])),
                    'product_id': UUID(str(row['product_id'])),
                    'process_id': UUID(str(row['process_id'])),
                    'consumable_id': UUID(str(row['consumable_id'])),
                    'rule_id': UUID(str(row['rule_id'])),
                    'rule_type': row['rule_type'],
                    'rule_version': row['rule_version'],
                    'parameters': row['parameters'],
                    'source_production_qty': row['source_production_qty'],
                    'raw_requirement': row['raw_requirement'],
                    'rounding_policy': row['rounding_policy'],
                    'rounding_precision': row['rounding_precision'],
                    'calculated_qty': row['calculated_qty'],
                    'unit_id': UUID(str(row['unit_id'])),
                    'uom': row['uom'],
                    'calculation_steps': list(row['calculation_steps']),
                    'norms_included': [{
                        'rule_id': str(row['rule_id']),
                        'parameters': row['parameters'],
                        'raw_requirement': str(row['raw_requirement']),
                        'calculated_qty': str(row['calculated_qty']),
                        'steps': row['calculation_steps']
                    }],
                    'source_row_number': row['source_row_number'],
                    'production_unit_source': row['production_unit_source'],
                    'source_production_unit': row['source_production_unit'],
                    'production_unit': row['production_unit'],
                }
            else:
                existing = consolidated[key]
                existing['raw_requirement'] += row['raw_requirement']
                existing['calculated_qty'] += row['calculated_qty']
                existing['calculation_steps'].extend(row['calculation_steps'])
                existing['norms_included'].append({
                    'rule_id': str(row['rule_id']),
                    'parameters': row['parameters'],
                    'raw_requirement': str(row['raw_requirement']),
                    'calculated_qty': str(row['calculated_qty']),
                    'steps': row['calculation_steps']
                })

        for row in consolidated.values():
            db.add(CalculatedRequirement(
                planning_version_id=version.id,
                plant_id=None,
                prd_order_item_id=row['prd_order_item_id'],
                product_id=row['product_id'],
                process_id=row['process_id'],
                consumable_id=row['consumable_id'],
                rule_id=row['rule_id'],
                rule_type=row['rule_type'],
                rule_version=row['rule_version'],
                parameters=row['parameters'],
                source_production_qty=row['source_production_qty'],
                raw_requirement=row['raw_requirement'],
                rounding_policy=row['rounding_policy'],
                rounding_precision=row['rounding_precision'],
                calculated_qty=row['calculated_qty'],
                unit_id=row['unit_id'],
                uom=row['uom'],
                calculation_steps=row['calculation_steps'],
                explanation_payload={
                    'workflow': WORKFLOW,
                    'as_of_date': str(data['as_of_date']),
                    'production_source': {
                        'prd_order_item_id': str(row['prd_order_item_id']),
                        'source_row_number': row['source_row_number'],
                        'planned_quantity': str(row['source_production_qty']),
                        'unit': row['production_unit'],
                        'source_unit': row['source_production_unit'],
                        'unit_source': row['production_unit_source'],
                    },
                    'rule_id': str(row['rule_id']),
                    'rule_version': row['rule_version'],
                    'parameters': row['parameters'],
                    'raw_requirement': str(row['raw_requirement']),
                    'steps': row['calculation_steps'],
                    'norms_included': row['norms_included'],
                    'total_calculated_qty': str(row['calculated_qty'])
                }
            ))
        for missing in data['no_consumption_norms']:
            db.add(RequirementCalculationError(
                planning_version_id=version.id,
                prd_order_item_id=UUID(str(missing['prd_order_item_id'])),
                product_id=UUID(str(missing['product_id'])) if missing.get('product_id') else None,
                consumable_id=None,
                error_code='NO_CONSUMPTION_NORM',
                error_message=f"Part {missing['part_number']} has planned production of {missing['planned_quantity']} but no consumption norms defined.",
                context_data={
                    'source_row_number': missing['source_row_number'],
                    'part_number': missing['part_number'],
                    'item_id': missing['item_id'],
                    'planned_quantity': str(missing['planned_quantity'])
                }
            ))
        for issue in data['errors']:
            db.add(RequirementCalculationError(
                planning_version_id=version.id,
                prd_order_item_id=UUID(str(issue['prd_order_item_id'])),
                product_id=UUID(str(issue['product_id'])) if issue.get('product_id') else None,
                consumable_id=UUID(str(issue['consumable_id'])) if issue.get('consumable_id') else None,
                error_code=issue['code'],
                error_message=issue['message'],
                context_data={name: str(issue[name]) for name in ('source_row_number', 'norm_id', 'process_id') if issue.get(name) is not None}
            ))
        version.status = 'CALCULATED' if data['complete'] else 'CALCULATED_WITH_ERRORS'
        version.calculated_at = datetime.now(timezone.utc)
        total_errs = len(data['errors']) + len(data['no_consumption_norms'])
        db.add(AuditLog(actor_id=actor, action='CALCULATE', entity_type='planning_version', entity_id=version.id,
            new_values={'workflow': WORKFLOW, 'review_token': data['review_token'], 'status': version.status,
                'calculation_count': len(data['calculations']), 'error_count': total_errs,
                'missing_norms_count': len(data['no_consumption_norms'])}, reason='Central basic requirements; stock is applied downstream after consolidation'))
        db.commit()
        return RequirementCalculationRunResponse(
            planning_version_id=version.id,
            planning_period=version.planning_period,
            revision_label=version.revision_label,
            status=version.status,
            total_items_processed=len(data['sources']),
            successful_requirements_count=len(data['calculations']),
            error_count=total_errs,
            summary_by_consumable=data['summary_by_consumable'],
            errors=get_calculation_errors(db, version.id),
            has_missing_norms=data['has_missing_norms'],
            missing_parts_count=data['missing_parts_count'],
            missing_parts_qty=data['missing_parts_qty'],
            no_consumption_norms=data['no_consumption_norms'],
            duplicate_norm_groups_count=data['duplicate_norm_groups_count'],
            duplicate_groups_warning=data['duplicate_groups_warning'],
        )
    except Exception:
        db.rollback()
        raise
