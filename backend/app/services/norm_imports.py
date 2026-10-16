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
    "part_number": ("Part No", "Part Number", "Product Code", "Part No."),
    "part_name": ("Used for- Part Name", "Used for - Part Name", "Part Name", "Used for Part Name"),
    "used_part_number": ("Used Part no (prd order)", "Used Part No", "Used Part No.", "Used Part no"),
    "consumable_code": ("Cons. Item ID", "Consumable Item ID", "Cons Item ID", "Cons. Item Id", "Cons Item Id"),
    "consumable_name": ("Consumable Name", "Consumable"),
    "process_name": ("Process Name", "Process"),
    "thickness": ("Part Thickness in mm", "Part Thickness", "Thickness", "Part Thickness (mm)"),
    "process_count": ("No.of Process", "No of Process", "Process Count", "No. of Process"),
    "reference_production_qty": ("Prd. Order", "Prd Order", "Prd. Order.", "Prd Order."),
    "reference_schedule_qty": ("Sch", "Schedule"),
}
REQUIRED = {"part_number", "consumable_code", "process_name", "process_count"}
S_NO_ALIASES = {"sno", "slno", "serialno", "serialnumber"}


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
            norm_val = _normal(value)
            if norm_val in S_NO_ALIASES:
                continue
            key = aliases.get(norm_val)
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
    skipped_total_count = 0
    skipped_empty_count = 0
    for row_number, row in enumerate(rows[header + 1:], start=header + 2):
        values = {field: row[column] if column < len(row) else None for field, column in columns.items()}
        if not any(value is not None and str(value).strip() for value in values.values()):
            skipped_empty_count += 1
            continue
        
        # Check for sub-total / junk row with "Total"
        cons_name = str(values.get("consumable_name") or "").strip().upper()
        part_name = str(values.get("part_name") or "").strip().upper()
        part_no = str(values.get("part_number") or "").strip().upper()
        if cons_name == "TOTAL" or part_name == "TOTAL" or part_no == "TOTAL":
            skipped_total_count += 1
            continue

        converted = {field: str(value).strip() if value is not None else None for field, value in values.items()}
        for field in FIELDS:
            if field != "s_no":
                converted.setdefault(field, None)
        for field in ("part_number", "part_name", "used_part_number", "consumable_code", "consumable_name", "process_name"):
            converted[field] = converted.get(field) or ""
            
        if converted["part_number"] == " ":
            converted["part_number"] = ""

        try:
            parsed.append(NormImportRowInput(row_number=row_number, **converted))
        except ValueError:
            raise ApplicationError("INVALID_NORM_ROW", f"Row {row_number}: an identifier or description exceeds its allowed length.", 422) from None
    if not parsed:
        raise ApplicationError("EMPTY_NORM_FILE", "No consumption norm rows were found beneath the headers.", 422)
    if len(parsed) > 5000:
        raise ApplicationError("NORM_FILE_TOO_LARGE", "Use at most 5000 norm rows.", 422)
    return sheet, parsed, skipped_total_count, skipped_empty_count


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
    groups = defaultdict(list)
    exact_duplicates = defaultdict(list)

    for item in inputs:
        row = NormImportRow(**item.model_dump())
        part_no = (row.part_number or "").strip()
        used_part_no = (row.used_part_number or "").strip()
        proc_name = (row.process_name or "").strip()
        pc_raw = str(row.process_count).strip() if row.process_count is not None else ""

        # Determine if row is product-linked vs general
        has_part_linkage = bool(part_no or used_part_no or (proc_name and proc_name != "0") or (pc_raw and pc_raw != "0"))
        if not part_no and has_part_linkage:
            # Blank Part No on a product-linked row is a true error
            is_general = False
            row.is_general = False
            _error(row, "part_number", "BLANK_PART_NUMBER", f"Row {row.row_number}: Blank Part No on a product-linked row.")
        elif not part_no:
            is_general = True
            row.is_general = True
            row.part_number = ""
        else:
            is_general = False
            row.is_general = False

        # Consumable validation
        cons_code = (row.consumable_code or "").strip()
        if not cons_code:
            _error(row, "consumable_code", "CONSUMABLE_CODE_REQUIRED", f"Row {row.row_number}: Blank Cons. Item ID.")
        elif cons_code in {"1", "2"} or cons_code.isdigit():
            _error(row, "consumable_code", "INVALID_CONSUMABLE_CODE", f"Row {row.row_number}: Cons. Item ID '{cons_code}' is invalid. Numeric codes (1, 2) and category headers are not valid Cons. Item IDs.")
        else:
            matches = consumables.get(cons_code.casefold(), [])
            if len(matches) != 1:
                _error(row, "consumable_code", "MASTER_REFERENCE_REQUIRED", f"Row {row.row_number}: Cons. Item ID '{cons_code}' not found in Consumable Master ({len(matches)} matches).")
            else:
                c_mat = matches[0]
                row.consumable_id = str(c_mat.id)
                unit = units.get(str(c_mat.unit_id))
                if unit is None:
                    _error(row, "unit", "STOCK_UNIT_REQUIRED", f"Row {row.row_number}: Consumable '{cons_code}' needs an active canonical stock unit.")
                else:
                    row.unit_id = str(unit.id)
                    row.unit_code = unit.code
                if not row.consumable_name:
                    row.consumable_name = c_mat.name

        if not is_general:
            if not row.part_number:
                row.product_id = None
            else:
                prod = None
                if row.used_part_number:
                    prod, _ = match_product(products, part_number=row.used_part_number)
                if prod is None and row.part_number:
                    prod, _ = match_product(products, part_number=row.part_number)
                if prod is not None:
                    row.product_id = str(prod.id)
                else:
                    review_field = 'used_part_number' if row.used_part_number else 'part_number'
                    _error(row, review_field, "MASTER_REFERENCE_REQUIRED", f"Row {row.row_number}: {review_field} '{getattr(row, review_field)}' not found in Product Master.")
        else:
            row.product_id = None

        # Process validation
        if proc_name in {"0", ""}:
            row.process_name = ""
            row.process_id = None
        else:
            p_matches = processes.get(proc_name.casefold(), [])
            if len(p_matches) == 1:
                row.process_id = str(p_matches[0].id)
            else:
                _error(row, "process_name", "MASTER_REFERENCE_REQUIRED", f"Row {row.row_number}: Process '{proc_name}' not found in Process Master ({len(p_matches)} matches).")

        # Thickness: reference data only. Store as text (e.g. "OD22.23 x T 2"), never reject. Parse as number only when it looks numeric.
        if row.thickness is not None and str(row.thickness).strip() != "":
            raw_t = str(row.thickness).strip()
            try:
                t_val = _number(raw_t)
                row.thickness = str(t_val) if t_val is not None else raw_t
            except ValueError:
                row.thickness = raw_t
        else:
            row.thickness = None

        # Process count, Prd Order, Sch validation
        pc_raw = str(row.process_count).strip() if row.process_count is not None else ""
        sch_raw = str(row.reference_schedule_qty).strip() if row.reference_schedule_qty is not None else ""
        try:
            if not pc_raw or pc_raw == "0":
                pc_val = Decimal("0")
            else:
                pc_val = _number(pc_raw)
            if pc_val is None or pc_val < 0:
                raise ValueError
            # If Sch is specified and positive, No.of Process cannot be 0 unless Prd Order is 0
            if not is_general and sch_raw and sch_raw not in {"0", "0.0", "0.00"} and pc_val == 0:
                raise ValueError
            no_of_process = int(pc_val)
            row.process_count = str(no_of_process)
        except (ValueError, TypeError):
            _error(row, "process_count", "INVALID_NORM_NUMBER", f"Row {row.row_number}: No.of Process must be a whole number >= 0.")
            no_of_process = 0

        try:
            po_raw = str(row.reference_production_qty).strip() if row.reference_production_qty is not None else ""
            if not po_raw:
                po_val = Decimal("0") if is_general else Decimal("1")
            else:
                po_val = _number(po_raw)
            if po_val is None or po_val < 0:
                raise ValueError
            prd_order = int(po_val)
            row.reference_production_qty = str(prd_order)
        except (ValueError, TypeError):
            _error(row, "reference_production_qty", "INVALID_NORM_NUMBER", f"Row {row.row_number}: Prd. Order must be a whole number >= 0.")
            prd_order = 1

        try:
            sch_raw = str(row.reference_schedule_qty).strip() if row.reference_schedule_qty is not None else ""
            if not sch_raw:
                sch_val = Decimal(str(prd_order * no_of_process))
            else:
                sch_val = _number(sch_raw)
            if sch_val is None or sch_val < 0:
                raise ValueError
            sch = int(sch_val)
            row.reference_schedule_qty = str(sch)
        except (ValueError, TypeError):
            _error(row, "reference_schedule_qty", "INVALID_NORM_NUMBER", f"Row {row.row_number}: Sch must be a whole number >= 0.")
            sch = prd_order * no_of_process

        expected_sch = prd_order * no_of_process
        if sch != expected_sch:
            row.sch_differs = True
            row.warnings.append(f"Row {row.row_number}: Sch differs (file has {sch}, expected {expected_sch} = {prd_order} x {no_of_process}).")

        if sch == 0 and not is_general:
            row.sch_is_zero = True
            row.warnings.append(f"Row {row.row_number}: Sch is 0: no requirement will be calculated.")

        # Re-upload matching against DB
        key = (row.product_id, row.process_id, row.consumable_id)
        if not row.errors:
            existing = norms.get(key, [])
            if existing:
                identical = len(existing) == 1 and _same_norm(existing[0], row, review)
                row.action = "EXISTING" if identical else "CONFLICT"
                row.change_status = "unchanged" if identical else "changed"
                if not identical:
                    row.errors.append(NormImportError(field="reference_schedule_qty", code="EXISTING_NORM_CONFLICT", message="An active norm for this product/process/consumable differs. Explicit reviewed supersede mode and update permission are required."))
            else:
                row.action = "CREATE"
                row.change_status = "new"

        # Duplicate groups tracking
        if not is_general and row.part_number:
            grp_key = (
                row.part_number.strip().casefold(),
                row.consumable_code.strip().casefold(),
                (row.process_name or "").strip().casefold(),
            )
            groups[grp_key].append(row)

            exact_key = (
                row.part_number.strip().casefold(),
                row.consumable_code.strip().casefold(),
                (row.process_name or "").strip().casefold(),
                (row.used_part_number or "").strip().casefold(),
            )
            exact_duplicates[exact_key].append(row)

        rows.append(row)

    dup_groups_count = 0
    for grp_key, grp_rows in groups.items():
        if len(grp_rows) > 1:
            dup_groups_count += 1
            for r in grp_rows:
                r.is_possible_duplicate = True
                r.warnings.append(f"Possible duplicate: group of {len(grp_rows)} rows in source rows {', '.join(str(x.row_number) for x in grp_rows)}.")

    for exact_key, ex_rows in exact_duplicates.items():
        if len(ex_rows) > 1:
            for r in ex_rows:
                _error(r, "part_number", "DUPLICATE_NORM_ROW", f"This exact norm row occurs in source rows {', '.join(str(x.row_number) for x in ex_rows)}. Review distinct rows instead of silently merging them.")

    return rows, dup_groups_count


def _same_norm(norm, row, review):
    try:
        req_sch = _number(row.reference_schedule_qty)
        if req_sch is None:
            req_sch = _number(row.process_count)
        rate = Decimal(str(norm.parameters.get("rate") or norm.parameters.get("sch") or "0"))
        identical = (
            norm.rule_type == "PRODUCTION_RATE"
            and (rate == req_sch or (norm.parameters.get("rate") == str(row.process_count)))
            and Decimal(str(norm.parameters.get("scrap_factor", "0"))) == 0
            and str(norm.unit_id) == str(row.unit_id)
        )
        if review is not None:
            identical = (
                identical
                and norm.effective_from == review.effective_from
                and norm.effective_to is None
                and RoundingPolicy.parse(norm.rounding_policy) == review.rounding_policy
                and norm.rounding_precision == review.rounding_precision
            )
        return identical
    except (ValueError, ArithmeticError, TypeError):
        return False


def preview(db, filename, content, corrections=None):
    sheet, inputs, skipped_total_count, skipped_empty_count = _read(filename, content)
    inputs = _corrected(inputs, content, corrections)
    catalog = load_catalog(db)
    rows, dup_groups_count = validate_rows(db, inputs, catalog=catalog)
    general_count = sum(1 for r in rows if r.is_general)
    return NormImportPreview(
        filename=filename[:255],
        source_sha256=sha256(content).hexdigest(),
        review_token=state_token(db, catalog),
        sheet_name=sheet,
        row_count=len(rows),
        valid_count=sum(row.action in {"CREATE", "EXISTING"} for row in rows),
        invalid_count=sum(row.action == "INVALID" for row in rows),
        duplicate_count=sum(row.is_possible_duplicate or any(error.code in {"DUPLICATE_NORM_ROW", "CONFLICTING_NORM_ROWS"} for error in row.errors) for row in rows),
        existing_count=sum(row.action == "EXISTING" for row in rows),
        conflict_count=sum(row.action == "CONFLICT" for row in rows),
        general_count=general_count,
        skipped_total_count=skipped_total_count,
        skipped_empty_count=skipped_empty_count,
        duplicate_groups_count=dup_groups_count,
        rows=rows,
    )


def _reference(row, filename, content_hash, sheet):
    return {
        field: getattr(row, field, None)
        for field in (
            "part_number", "part_name", "used_part_number", "thickness",
            "process_count", "reference_production_qty", "reference_schedule_qty",
        )
    } | {
        "sch": getattr(row, "reference_schedule_qty", None) or getattr(row, "sch", None),
        "prd_order": getattr(row, "reference_production_qty", None) or getattr(row, "prd_order", None),
        "is_general": bool(getattr(row, "is_general", False)),
        "source_filename": filename[:255],
        "source_sha256": content_hash,
        "source_row": row.row_number,
        "sheet_name": sheet,
        "formula_choice": FORMULA_CHOICE,
    }


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
    sheet, source, skipped_total_count, skipped_empty_count = _read(filename, content)
    inputs = _corrected(source, content, review)
    identity = uuid5(NAMESPACE_URL, "knl/norm-import/" + sha256(json.dumps(review.model_dump(mode="json"), sort_keys=True).encode()).hexdigest())
    try:
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
                "superseded_count": result["superseded_count"], "skipped_invalid_count": result.get("skipped_invalid_count", 0),
                "replayed": True, "records": records,
                "message": "This exact reviewed import was already saved; no duplicate norms were created."}
        rules.lock_norm_catalog(db)
        catalog = load_catalog(db, lock=True)
        if state_token(db, catalog) != review.review_token:
            raise ApplicationError("STALE_NORM_REVIEW", "Master data or norms changed after preview. Revalidate and review the new state before saving.", 409)
        rows, dup_groups_count = validate_rows(db, inputs, review, catalog)
        invalid_rows = [row for row in rows if row.action == "INVALID"]
        conflict_rows = [row for row in rows if row.action == "CONFLICT" and review.mode != "SUPERSEDE"]
        if conflict_rows:
            raise ApplicationError("NORM_IMPORT_CONFLICT", f"{len(conflict_rows)} rows conflict with existing norms. Review supersede mode to overwrite.", 422)
        if invalid_rows and not review.skip_invalid:
            raise ApplicationError("NORM_IMPORT_VALIDATION_FAILED", "No norms saved. Correct the row errors or explicitly review supersede mode.", 422,
                details={"rows": [row.model_dump(mode="json") for row in rows]})
        records, skipped, superseded = [], 0, 0
        current = defaultdict(list)
        product_ids = {UUID(row.product_id) for row in rows if row.product_id and row.action != "INVALID"}
        for norm in catalog[ConsumptionNorm]:
            if (norm.product_id in product_ids or norm.product_id is None) and norm.plant_id is None:
                current[(str(norm.product_id), str(norm.process_id), str(norm.consumable_id))].append(norm)
        replaced_ids, references, audits = [], {}, []
        for row in rows:
            if row.action == "INVALID":
                continue
            if row.action == "EXISTING":
                skipped += 1
                continue
            if row.action == "CONFLICT":
                superseded += 1
            key = (row.product_id, row.process_id, row.consumable_id)
            prior_versions = current.get(key, [])
            rate_val = str(row.process_count if (row.reference_schedule_qty is not None and row.reference_production_qty is not None and Decimal(row.reference_production_qty) > 1) else (row.reference_schedule_qty or row.process_count or "0"))
            params = rules.validate_rule_parameters(RuleType.PRODUCTION_RATE,
                {'rate': rate_val, 'scrap_factor': '0'}).model_dump(mode='json')
            params['prd_order'] = str(row.reference_production_qty or "1")
            params['process_count'] = str(row.process_count or "0")
            params['sch'] = str(row.reference_schedule_qty or rate_val)
            params['is_general'] = bool(row.is_general)
            params['sch_overridden'] = False

            norm = ConsumptionNorm(
                id=uuid4(),
                rule_type=RuleType.PRODUCTION_RATE.value,
                product_id=UUID(row.product_id) if row.product_id else None,
                process_id=UUID(row.process_id) if row.process_id else None,
                consumable_id=UUID(row.consumable_id),
                unit_id=UUID(row.unit_id),
                plant_id=None,
                parameters=params,
                version=max((item.version for item in prior_versions), default=0) + 1,
                effective_from=review.effective_from,
                rounding_policy=review.rounding_policy.value,
                rounding_precision=review.rounding_precision,
                is_active=True,
            )
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
            "skipped_invalid_count": len(invalid_rows),
            "norm_ids": [str(row.id) for row in records], "source_sha256": review.source_sha256,
            "filename": filename[:255], "formula_choice": review.formula_choice, "row_count": len(rows)}
        db.add(AuditLog(id=identity, actor_id=actor_id, action="IMPORT_NORMS", entity_type="ConsumptionNormImport",
            entity_id=identity, new_values=result, reason=review.reason))
        ids = [item.id for item in records]
        response_rows = list(db.scalars(select(ConsumptionNorm).options(joinedload(ConsumptionNorm.product), joinedload(ConsumptionNorm.process),
            joinedload(ConsumptionNorm.consumable), joinedload(ConsumptionNorm.unit), joinedload(ConsumptionNorm.plant)).where(ConsumptionNorm.id.in_(ids)))) if ids else []
        responses = [rules._to_norm_response(norm, references[norm.id]) for norm in response_rows]
        db.commit()
        msg = f"{len(records) - superseded} norms created, {superseded} superseded and {skipped} existing rows skipped."
        if invalid_rows:
            msg += f" {len(invalid_rows)} invalid rows skipped."
        return {key: result[key] for key in ("created_count", "skipped_count", "superseded_count", "skipped_invalid_count")} | {
            "records": responses, "replayed": False, "message": msg}
    except IntegrityError:
        db.rollback()
        raise ApplicationError("NORM_IMPORT_CONFLICT", "Another save changed these norms. Preview the file again before confirming.", 409) from None
    except Exception:
        db.rollback()
        raise


def export_file(db=None, format="xlsx", *, template=False):
    if format not in {"xlsx", "csv"}:
        raise ApplicationError("INVALID_EXPORT_FORMAT", "Choose xlsx or csv.", 422)
    headers = [
        "S. No.", "Part No", "Used for- Part Name", "Used Part no (prd order)",
        "Cons. Item ID", "Consumable Name", "Process Name", "Part Thickness in mm",
        "No.of Process", "Prd. Order", "Sch"
    ]
    data = [headers]
    if not template:
        records = rules.list_consumption_norms(db)
        for idx, norm in enumerate(records, start=1):
            ref = norm.reference_data or {}
            params = norm.parameters or {}
            part_no = ref.get("part_number") or norm.product_part_number or norm.product_code or ""
            part_name = ref.get("part_name") or norm.product_name or ""
            used_part_no = ref.get("used_part_number") or ""
            cons_id = norm.consumable_code or ""
            cons_name = norm.consumable_name or ""
            proc_name = norm.process_name or ""
            thickness = ref.get("thickness") or ""
            no_of_process = ref.get("process_count") or params.get("process_count") or ""
            prd_order = ref.get("reference_production_qty") or params.get("prd_order") or "1"
            sch = ref.get("reference_schedule_qty") or params.get("sch") or params.get("rate") or ""
            data.append([
                str(idx), part_no, part_name, used_part_no, cons_id, cons_name,
                proc_name, thickness, str(no_of_process), str(prd_order), str(sch)
            ])
    if format == "csv":
        output = StringIO()
        writer = csv.writer(output)
        for row in data:
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value for value in row])
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    book = Workbook()
    book.active.title = "Plan"
    book.active.append(["KNL Consumable Plan Sheet", "", "", "", "", "", "", "", "", "For Component", "For Consumables"])
    book.active.append(["", "", "", "", "", "", "", "", "", "Prd. Order", "Sch"])
    for row in data:
        book.active.append(row)
    for row in book.active.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    output = BytesIO()
    book.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

