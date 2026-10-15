"""Read-only workbook review and atomic, audited imports of approved rate norms."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
import csv
import json
import re
import zipfile
from uuid import NAMESPACE_URL, UUID, uuid5, uuid4

from openpyxl import Workbook, load_workbook
from sqlalchemy import select, text, update
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Process
from app.models.rules import ConsumptionNorm
from app.schemas.norm_imports import NormImportCorrections, NormImportPreview, NormImportRow, NormImportRowInput, NormImportError
from app.schemas.rules import ConsumptionNormCreate
from app.services import rules
from app.domain.rules.types import RuleType, RoundingPolicy
from app.services.basic_norms import match_product

FORMULA_CHOICE = "PRODUCTION_RATE_FROM_PROCESS_COUNT"
MAX_BYTES = 10 * 1024 * 1024
FIELDS = {
    "part_number": ("Part No", "Part Number", "Product Code"),
    "part_name": ("Used for- Part Name", "Part Name"),
    "used_part_number": ("Used Part no (prd order)", "Used Part No"),
    "consumable_code": ("Cons. Item ID", "Consumable Item ID", "Cons Item ID"),
    "consumable_name": ("Consumable Name",),
    "process_name": ("Process Name", "Process"),
    "thickness": ("Part Thickness in mm", "Thickness"),
    "process_count": ("No.of Process", "No of Process", "Process Count"),
    "reference_production_qty": ("Prd. Order", "Prd Order"),
    "reference_schedule_qty": ("Sch", "Schedule"),
}
REQUIRED = {"part_number", "consumable_code", "process_name", "process_count"}


def _normal(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _read(filename, content):
    if not content or len(content) > MAX_BYTES:
        raise ApplicationError("INVALID_NORM_FILE", "Choose a nonempty file no larger than 10 MB.", 422)
    try:
        if filename.lower().endswith(".csv"):
            rows = list(csv.reader(StringIO(content.decode("utf-8-sig"))))
            sheet = "CSV"
        elif filename.lower().endswith(".xlsx"):
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 200 * 1024 * 1024:
                    raise ApplicationError("NORM_FILE_TOO_LARGE", "The expanded workbook exceeds 200 MB.", 422)
            book = load_workbook(BytesIO(content), read_only=True, data_only=False)
            try:
                ws = book["Plan"] if "Plan" in book.sheetnames else book[book.sheetnames[0]]
                if ws.max_row > 5050 or ws.max_column > 100:
                    raise ApplicationError("NORM_FILE_TOO_LARGE", "Use at most 5000 norm rows and 100 columns.", 422)
                rows = [list(row) for row in ws.iter_rows(values_only=True)]
                sheet = ws.title
            finally:
                book.close()
        else:
            raise ApplicationError("INVALID_NORM_FILE", "Choose an .xlsx or UTF-8 .csv file.", 422)
    except ApplicationError:
        raise
    except Exception:
        raise ApplicationError("INVALID_NORM_FILE", "The file could not be read. Save it as .xlsx or UTF-8 CSV.", 422) from None
    if len(rows) > 5050:
        raise ApplicationError("NORM_FILE_TOO_LARGE", "Use at most 5000 norm rows.", 422)
    aliases = {_normal(alias): field for field, values in FIELDS.items() for alias in values}
    header = None
    for index, row in enumerate(rows[:30]):
        columns = {}
        for column, value in enumerate(row):
            key = aliases.get(_normal(value))
            if key:
                if key in columns:
                    raise ApplicationError("DUPLICATE_NORM_HEADER", f"The header repeats {key}.", 422)
                columns[key] = column
        if REQUIRED <= columns.keys():
            header = index
            break
    if header is None:
        raise ApplicationError("MISSING_NORM_COLUMNS", "Required columns: Part No, Cons. Item ID, Process Name, No.of Process.", 422)
    parsed = []
    for row_number, row in enumerate(rows[header + 1:], start=header + 2):
        values = {field: row[column] if column < len(row) else None for field, column in columns.items()}
        if not any(value is not None and str(value).strip() for value in values.values()):
            continue
        converted = {field: str(value).strip() if value is not None else None for field, value in values.items()}
        for field in FIELDS:
            converted.setdefault(field, None)
        for field in ("part_number", "part_name", "used_part_number", "consumable_code", "consumable_name", "process_name"):
            converted[field] = converted[field] or ""
        try:
            parsed.append(NormImportRowInput(row_number=row_number, **converted))
        except ValueError:
            raise ApplicationError("INVALID_NORM_ROW", f"Row {row_number}: an identifier or description exceeds its allowed length.", 422) from None
    if not parsed:
        raise ApplicationError("EMPTY_NORM_FILE", "No consumption norm rows were found beneath the headers.", 422)
    if len(parsed) > 5000:
        raise ApplicationError("NORM_FILE_TOO_LARGE", "Use at most 5000 norm rows.", 422)
    return sheet, parsed


def _corrected(rows, content, corrections):
    if corrections is None:
        return rows
    if corrections.source_sha256 != sha256(content).hexdigest():
        raise ApplicationError("STALE_NORM_FILE", "The selected file differs from the reviewed workbook. Preview it again.", 409)
    expected = {row.row_number for row in rows}
    actual = [row.row_number for row in corrections.rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ApplicationError("NORM_ROW_SET_CHANGED", "Review every source row exactly once; rows cannot be silently omitted or added.", 422)
    return sorted(corrections.rows, key=lambda row: row.row_number)


def _number(raw, *, positive=False):
    if raw is None or not str(raw).strip():
        if positive:
            raise ValueError
        return None
    try:
        result = Decimal(str(raw).strip())
        if not result.is_finite() or result < 0 or (positive and result <= 0) or result > Decimal("9999999999.9999") or result != result.quantize(Decimal("0.0001")):
            raise ValueError
        return result
    except (InvalidOperation, ArithmeticError):
        raise ValueError from None


def _error(row, field, code, message):
    row.errors.append(NormImportError(field=field, code=code, message=message))
    row.action = "INVALID"


def _index(records, keys):
    result = defaultdict(list)
    for record in records:
        for key in set(str(getattr(record, field) or "").strip().casefold() for field in keys):
            if key:
                result[key].append(record)
    return result


def load_catalog(db, *, lock=False):
    values = {}
    for model in (Product, Consumable, Process, Unit, ConsumptionNorm):
        query = select(model).order_by(model.id).execution_options(populate_existing=True)
        values[model] = list(db.scalars(query.with_for_update() if lock else query))
    return values


def validate_rows(db, inputs, review=None, catalog=None):
    catalog = catalog or load_catalog(db)
    products = [row for row in catalog[Product] if row.is_active]
    consumables = _index((row for row in catalog[Consumable] if row.is_active), ("code",))
    processes = _index((row for row in catalog[Process] if row.is_active), ("name",))
    units = {str(unit.id): unit for unit in catalog[Unit] if unit.is_active}
    norms = defaultdict(list)
    for norm in catalog[ConsumptionNorm]:
        if norm.is_active and norm.plant_id is None:
            norms[(str(norm.product_id), str(norm.process_id), str(norm.consumable_id))].append(norm)
    rows = []
    seen = defaultdict(list)
    for item in inputs:
        row = NormImportRow(**item.model_dump())
        for field, lookup, id_field in (("part_number", None, "product_id"), ("consumable_code", consumables, "consumable_id"), ("process_name", processes, "process_id")):
            if field == "part_number":
                # The workbook explicitly identifies the production part separately from its component reference.
                product, _ = match_product(products, part_number=row.used_part_number or row.part_number)
                matches = [product] if product is not None else []
            else:
                matches = lookup.get(getattr(row, field).strip().casefold(), [])
            if len(matches) != 1:
                review_field = 'used_part_number' if field == 'part_number' and row.used_part_number else field
                _error(row, review_field, "MASTER_REFERENCE_REQUIRED", f"{review_field}: choose one unambiguous active master record ({len(matches)} matches).")
            else:
                setattr(row, id_field, str(matches[0].id))
                if field == "consumable_code":
                    unit = units.get(str(matches[0].unit_id))
                    if unit is None:
                        _error(row, "unit", "STOCK_UNIT_REQUIRED", "The consumable needs an active canonical stock unit.")
                    else:
                        row.unit_id, row.unit_code = str(unit.id), unit.code
        for field in ("thickness", "process_count", "reference_production_qty", "reference_schedule_qty"):
            try:
                _number(getattr(row, field), positive=field == "process_count")
            except ValueError:
                _error(row, field, "INVALID_NORM_NUMBER", f"{field}: enter {'a positive' if field == 'process_count' else 'a nonnegative'} quantity with at most four decimal places; formulas and Excel errors require review.")
        if not row.errors:
            key = (row.product_id, row.process_id, row.consumable_id)
            seen[key].append(row)
            existing = norms.get(key, [])
            if existing:
                identical = len(existing) == 1 and _same_norm(existing[0], row, review)
                row.action = "EXISTING" if identical else "CONFLICT"
                if not identical:
                    row.errors.append(NormImportError(field="process_count", code="EXISTING_NORM_CONFLICT", message="An active norm for this product/process/consumable differs. Explicit reviewed supersede mode and update permission are required."))
        rows.append(row)
    for matches in seen.values():
        if len(matches) > 1:
            rates = {str(_number(row.process_count, positive=True).normalize()) for row in matches}
            code = "DUPLICATE_NORM_ROW" if len(rates) == 1 else "CONFLICTING_NORM_ROWS"
            for row in matches:
                _error(row, "part_number", code, "This product/process/consumable occurs in source rows " + ", ".join(str(r.row_number) for r in matches) + ". Review distinct rows instead of silently merging them.")
    return rows


def _same_norm(norm, row, review):
    try:
        identical = norm.rule_type == "PRODUCTION_RATE" and Decimal(str(norm.parameters.get("rate"))) == _number(row.process_count, positive=True) and Decimal(str(norm.parameters.get("scrap_factor", "0"))) == 0 and str(norm.unit_id) == row.unit_id
        if review is not None:
            identical = identical and norm.effective_from == review.effective_from and norm.effective_to is None and RoundingPolicy.parse(norm.rounding_policy) == review.rounding_policy and norm.rounding_precision == review.rounding_precision
        return identical
    except (ValueError, ArithmeticError, TypeError):
        return False


def preview(db, filename, content, corrections=None):
    sheet, inputs = _read(filename, content)
    inputs = _corrected(inputs, content, corrections)
    catalog = load_catalog(db)
    rows = validate_rows(db, inputs, catalog=catalog)
    return NormImportPreview(filename=filename[:255], source_sha256=sha256(content).hexdigest(), review_token=state_token(db, catalog), sheet_name=sheet,
        row_count=len(rows), valid_count=sum(row.action in {"CREATE", "EXISTING"} for row in rows),
        invalid_count=sum(row.action == "INVALID" for row in rows),
        duplicate_count=sum(any(error.code in {"DUPLICATE_NORM_ROW", "CONFLICTING_NORM_ROWS"} for error in row.errors) for row in rows),
        existing_count=sum(row.action == "EXISTING" for row in rows), conflict_count=sum(row.action == "CONFLICT" for row in rows), rows=rows)


def _reference(row, filename, content_hash, sheet):
    return {field: getattr(row, field) for field in ("part_number", "part_name", "used_part_number", "thickness", "process_count", "reference_production_qty", "reference_schedule_qty")} | {
        "source_filename": filename[:255], "source_sha256": content_hash, "source_row": row.row_number,
        "sheet_name": sheet, "formula_choice": FORMULA_CHOICE}


def state_token(db, catalog=None):
    """A reviewed supersede must never replace a version created after preview."""
    evidence = []
    catalog = catalog or load_catalog(db)
    for model, fields in ((Product, ("id", "code", "part_number", "item_id", "is_active")),
        (Consumable, ("id", "code", "name", "unit_id", "is_active")), (Process, ("id", "name", "is_active")),
        (Unit, ("id", "code", "is_active")), (ConsumptionNorm, ("id", "product_id", "process_id", "consumable_id", "plant_id",
            "rule_type", "version", "parameters", "unit_id", "effective_from", "effective_to", "rounding_policy", "rounding_precision", "is_active"))):
        evidence.append([model.__tablename__, [[getattr(row, field) for field in fields]
            for row in catalog[model]]])
    return sha256(json.dumps(evidence, default=str, sort_keys=True).encode()).hexdigest()


def confirm(db, filename, content, review, actor_id):
    if not review.reason.strip():
        raise ApplicationError("REASON_REQUIRED", "Enter a reason for this norm import.", 422)
    sheet, source = _read(filename, content)
    inputs = _corrected(source, content, review)
    identity = uuid5(NAMESPACE_URL, "knl/norm-import/" + sha256(json.dumps(review.model_dump(mode="json"), sort_keys=True).encode()).hexdigest())
    try:
        # Transaction advisory lock serializes repeat submissions across workers without a new table.
        if db.bind.dialect.name == "postgresql":
            key = int.from_bytes(identity.bytes[:8], "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        prior = db.get(AuditLog, identity)
        if prior:
            result = prior.new_values
            ids = result.get("norm_ids", [])
            records = [rules.get_consumption_norm(db, UUID(norm_id)) for norm_id in ids]
            db.rollback()
            return {"created_count": result["created_count"], "skipped_count": result["skipped_count"],
                "superseded_count": result["superseded_count"], "replayed": True, "records": records,
                "message": "This exact reviewed import was already saved; no duplicate norms were created."}
        # Lock canonical products consistently before checking current versions; same-scope imports serialize.
        rules.lock_norm_catalog(db)
        catalog = load_catalog(db, lock=True)
        if state_token(db, catalog) != review.review_token:
            raise ApplicationError("STALE_NORM_REVIEW", "Master data or norms changed after preview. Revalidate and review the new state before saving.", 409)
        rows = validate_rows(db, inputs, review, catalog)
        blocked = [row for row in rows if row.action == "INVALID" or (row.action == "CONFLICT" and review.mode != "SUPERSEDE")]
        if blocked:
            raise ApplicationError("NORM_IMPORT_VALIDATION_FAILED", "No norms saved. Correct the row errors or explicitly review supersede mode.", 422,
                details={"rows": [row.model_dump(mode="json") for row in rows]})
        records, skipped, superseded = [], 0, 0
        # The full batch was revalidated under the catalog lock. Prepare versions in
        # memory and fetch responses once, avoiding a master/version query per row.
        current = defaultdict(list)
        product_ids = {UUID(row.product_id) for row in rows if row.product_id}
        for norm in catalog[ConsumptionNorm]:
            if norm.product_id in product_ids and norm.plant_id is None:
                current[(str(norm.product_id), str(norm.process_id), str(norm.consumable_id))].append(norm)
        replaced_ids, references, audits = [], {}, []
        for row in rows:
            if row.action == "EXISTING":
                skipped += 1
                continue
            if row.action == "CONFLICT":
                superseded += 1
            prior_versions = current.get((row.product_id, row.process_id, row.consumable_id), [])
            params = rules.validate_rule_parameters(RuleType.PRODUCTION_RATE,
                {'rate': str(_number(row.process_count, positive=True)), 'scrap_factor': '0'}).model_dump(mode='json')
            norm = ConsumptionNorm(id=uuid4(), rule_type=RuleType.PRODUCTION_RATE.value, product_id=UUID(row.product_id),
                process_id=UUID(row.process_id), consumable_id=UUID(row.consumable_id), unit_id=UUID(row.unit_id),
                plant_id=None, parameters=params, version=max((item.version for item in prior_versions), default=0) + 1,
                effective_from=review.effective_from, rounding_policy=review.rounding_policy.value,
                rounding_precision=review.rounding_precision, is_active=True)
            records.append(norm)
            replaced_ids.extend(item.id for item in prior_versions if item.is_active)
            references[norm.id] = _reference(row, filename, review.source_sha256, sheet)
            audits.append(AuditLog(actor_id=actor_id, action='CREATE_VERSION', entity_type='ConsumptionNorm', entity_id=norm.id,
                old_values={'superseded_ids': [str(item.id) for item in prior_versions]},
                new_values={'version': norm.version, 'parameters': params, 'is_active': True, 'reference_data': references[norm.id]}, reason=review.reason))
        if replaced_ids:
            db.execute(update(ConsumptionNorm).where(ConsumptionNorm.id.in_(replaced_ids)).values(is_active=False))
        db.add_all(records); db.add_all(audits); db.flush()
        result = {"created_count": len(records) - superseded, "skipped_count": skipped, "superseded_count": superseded,
            "norm_ids": [str(row.id) for row in records], "source_sha256": review.source_sha256,
            "filename": filename[:255], "formula_choice": review.formula_choice, "row_count": len(rows)}
        db.add(AuditLog(id=identity, actor_id=actor_id, action="IMPORT_NORMS", entity_type="ConsumptionNormImport",
            entity_id=identity, new_values=result, reason=review.reason))
        ids = [item.id for item in records]
        response_rows = list(db.scalars(select(ConsumptionNorm).options(joinedload(ConsumptionNorm.product), joinedload(ConsumptionNorm.process),
            joinedload(ConsumptionNorm.consumable), joinedload(ConsumptionNorm.unit), joinedload(ConsumptionNorm.plant)).where(ConsumptionNorm.id.in_(ids)))) if ids else []
        responses = [rules._to_norm_response(norm, references[norm.id]) for norm in response_rows]
        db.commit()
        return {key: result[key] for key in ("created_count", "skipped_count", "superseded_count")} | {
            "records": responses, "replayed": False, "message": "Reviewed consumption norms saved atomically."}
    except IntegrityError:
        db.rollback()
        raise ApplicationError("NORM_IMPORT_CONFLICT", "Another save changed these norms. Preview the file again before confirming.", 409) from None
    except Exception:
        db.rollback()
        raise


def export_file(db=None, format="xlsx", *, template=False):
    if format not in {"xlsx", "csv"}:
        raise ApplicationError("INVALID_EXPORT_FORMAT", "Choose xlsx or csv.", 422)
    headers = [values[0] for values in FIELDS.values()]
    data = [headers]
    if not template:
        records = rules.list_consumption_norms(db)
        for norm in records:
            ref = norm.reference_data or {}
            data.append([ref.get("part_number") or norm.product_part_number or norm.product_code or "",
                ref.get("part_name") or norm.product_name or "", ref.get("used_part_number") or "",
                norm.consumable_code or "", norm.consumable_name or "", norm.process_name or "",
                ref.get("thickness"), ref.get("process_count"), ref.get("reference_production_qty"), ref.get("reference_schedule_qty")])
        # Additional verified formula/version columns make exports unambiguous; import ignores these references.
        data[0] += ["Rule Type", "Parameters", "Output Unit", "Version", "Effective From", "Effective Until", "Active"]
        for row, norm in zip(data[1:], records):
            row.extend([norm.rule_type.value, json.dumps(norm.parameters, sort_keys=True), norm.unit_code, norm.version,
                str(norm.effective_from), str(norm.effective_to or ""), str(norm.is_active)])
    if format == "csv":
        output = StringIO()
        writer = csv.writer(output)
        # Neutralize spreadsheet-formula injection in text fields on export.
        for row in data:
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value for value in row])
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    book = Workbook()
    book.active.title = "Plan"
    for row in data:
        book.active.append(row)
    for row in book.active.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    output = BytesIO()
    book.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
