"""Monthly Product Master intake, corrections, export and retained deletion history."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
from uuid import UUID, uuid4

from openpyxl import Workbook
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, Unit
from app.models.mappings import ProductProcessConsumable
from app.models.masters import Product
from app.models.master_uploads import MasterUploadBatch
from app.models.production import Process
from app.schemas.master_uploads import ExistingMasterView, ExistingMasterDelete, MasterPeriodView, MasterPeriodSave, MasterPeriodDelete
from app.services import product_master_service as legacy

FIELDS = {
    "consumables": {
        "supplier_id": ["supplier_id", "supplier id", "supplier code", "suppliercode", "vendor_id", "vendor id", "vendor code", "supp id", "supplier"],
        "supplier_name": ["supplier_name", "supplier name", "vendor", "vendor name"],
        "item_id": ["item_id", "itemid", "item no", "item code", "code"],
        "description": ["description", "part description", "name", "item description"],
        "category": ["category", "item category"],
        "type_of_material": ["type_of_material", "type of material", "material type", "type"],
        "output_unit": ["stock_unit", "stock unit", "unit", "uom", "output_unit", "output/unit"],
        "rate": ["rate", "price", "unit rate", "cost"],
    },
    "sales_parts": {
        "part_no": ["part_no", "partno", "part number", "part_number"],
        "item_id": ["item_id", "itemid", "item no", "item code"],
        "part_description": ["part_description", "description", "name", "part name"],
        "uom": ["uom", "unit", "output_unit"],
    },
    "assemble": {
        "consumable_item": ["consumable_item", "consumable item", "consumable", "item id", "item_id"],
        "part_no_saleable_item": ["part_no_saleable_item", "saleable part no", "part no", "finished part no", "part_no"],
        "used_for_name_of_saleable_part": ["used_for_name_of_saleable_part", "saleable part name", "part name"],
        "used_part_no_prd_order": ["used_part_no_prd_order", "prd part no"],
        "process_name": ["process_name", "process"],
        "material_thickness_in_mm_gsm": ["material_thickness_in_mm_gsm", "thickness"],
        "no_of_process_per_part": ["no_of_process_per_part", "qty", "process count", "quantity"],
        "output_unit": ["output_unit", "unit", "uom"],
        "rate": ["rate", "cost", "unit rate", "price"],
    },
}
MODELS = {"consumables": Consumable, "sales_parts": Product, "assemble": ProductProcessConsumable}
ALIASES = {"sales_parts": {"part_no": "part_number", "part_description": "description"}}
EDITABLE = {
    "consumables": {"supplier_name": 255, "description": 2000, "category": 128, "type_of_material": 128, "rate": None},
    "sales_parts": {"part_description": 2000},
    "assemble": {"used_for_name_of_saleable_part": 255, "used_part_no_prd_order": 128,
                 "material_thickness_in_mm_gsm": 64, "no_of_process_per_part": None, "rate": None},
}
NUMERIC = {"rate", "no_of_process_per_part"}
LENGTHS = {"item_id": 128, "part_no": 128, "category": 128, "type_of_material": 128,
           "consumable_item": 128, "part_no_saleable_item": 128, "process_name": 128,
           "used_part_no_prd_order": 128, "material_thickness_in_mm_gsm": 64}


def number(value, field):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
        if not result.is_finite() or result < 0 or result >= Decimal("10000000000"):
            raise ValueError()
        if result != result.quantize(Decimal("0.0001")):
            raise ValueError()
        return result
    except (ValueError, InvalidOperation):
        raise ApplicationError("INVALID_MASTER_VALUE", f"{field}: enter a nonnegative number with at most four decimal places.", 422) from None


def snapshot(category, row):
    values = {"id": str(row.id)}
    for field in FIELDS[category]:
        value = getattr(row, ALIASES.get(category, {}).get(field, field))
        values[field] = str(value) if value is not None else None
    return values


def view(batch, category, month, year):
    if batch is None:
        return MasterPeriodView(category=category, month=month, year=year)
    return MasterPeriodView(batch_id=batch.id, version=batch.version, category=category,
                            month=month, year=year, filename=batch.filename,
                            updated_at=batch.updated_at, records=batch.records)


def active_batch(session, category, month, year, *, lock=False):
    query = select(MasterUploadBatch).where(
        MasterUploadBatch.category == category, MasterUploadBatch.month == month,
        MasterUploadBatch.year == year, MasterUploadBatch.status == "active")
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return session.scalar(query)


def get_period(session, category, month, year):
    return view(active_batch(session, category, month, year), category, month, year)


def lock_category(session, category):
    if session.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(sha256(f"master-category:{category}".encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def tracked_ids(session, category, *, active_only=False, exclude_batch=None):
    query = select(MasterUploadBatch.records).where(MasterUploadBatch.category == category)
    if active_only:
        query = query.where(MasterUploadBatch.status == "active")
    if exclude_batch:
        query = query.where(MasterUploadBatch.id != exclude_batch)
    return {record["id"] for records in session.scalars(query) for record in records}


def existing_rows(session, category, *, lock=False):
    model = MODELS[category]
    query = select(model).where(model.is_active.is_(True)).order_by(model.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    recorded = tracked_ids(session, category)
    return [row for row in session.scalars(query) if str(row.id) not in recorded]


def existing_view(category, rows):
    records = [snapshot(category, row) for row in rows]
    evidence = [(record, str(row.updated_at)) for record, row in zip(records, rows)]
    token = sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    return ExistingMasterView(category=category, row_count=len(records), review_token=token, records=records)


def get_existing(session, category):
    return existing_view(category, existing_rows(session, category))


def deactivate_rows(session, category, rows, actor, reason):
    for row in rows:
        before = {**snapshot(category, row), "is_active": row.is_active}
        row.is_active = False
        session.add(AuditLog(actor_id=actor.id, action="DEACTIVATE", entity_type=MODELS[category].__tablename__,
            entity_id=row.id, old_values=before, new_values={**before, "is_active": False}, reason=reason))


def delete_existing(session, category, payload: ExistingMasterDelete, actor):
    try:
        lock_category(session, category)
        rows = existing_rows(session, category, lock=True)
        reviewed = existing_view(category, rows)
        if not rows:
            return {"deleted": True, "deactivated_count": 0, "replayed": True}
        if reviewed.review_token != payload.review_token:
            raise ApplicationError("MASTER_CHANGED", "Existing data changed after review. Refresh and review it before deleting.", 409)
        deactivate_rows(session, category, rows, actor, payload.reason)
        session.commit()
        return {"deleted": True, "deactivated_count": len(rows), "replayed": False}
    except Exception:
        session.rollback()
        raise


def audit(session, batch, actor, action, old, new, reason):
    session.add(AuditLog(actor_id=actor.id, action=action, entity_type="MasterUploadBatch", entity_id=batch.id,
        old_values=old, new_values={"category": batch.category, "month": batch.month, "year": batch.year, **new}, reason=reason))


def parse(category, content, *, report=None):
    if len(content) > 15 * 1024 * 1024:
        raise ApplicationError("SOURCE_TOO_LARGE", "Use an Excel workbook of at most 15 MB.", 422)
    frame = legacy.header_hunter(content, [alias for aliases in FIELDS[category].values() for alias in aliases])
    explicit_unit_columns = [column for column in frame.columns
                             if legacy._normalize_col_name(column) in {"stockunit", "unit", "uom"}]
    rows = {}
    source_rows = {}
    missing = []
    duplicates = []
    for index, source in frame.iterrows():
        row = {field: legacy._extract_field(source, aliases) for field, aliases in FIELDS[category].items()}
        if category == "consumables":
            if not row["item_id"]:
                missing.append(int(index) + 1)
                continue
            row["item_id"] = row["item_id"].upper()
            key = row["item_id"]
        elif category == "sales_parts":
            if not row["part_no"] and not row["item_id"]:
                missing.append(int(index) + 1)
                continue
            row["part_no"] = row["part_no"] or row["item_id"]
            row["item_id"] = row["item_id"] or row["part_no"]
            row["part_description"] = row["part_description"] or f"Part {row['part_no']}"
            key = (row["part_no"], row["item_id"])
        else:
            if not row["consumable_item"] or not row["part_no_saleable_item"]:
                missing.append(int(index) + 1)
                continue
            row["consumable_item"] = row["consumable_item"].upper()
            row["process_name"] = row["process_name"] or "ASSEMBLY"
            key = (row["consumable_item"], row["part_no_saleable_item"], row["process_name"].upper())
        for field in NUMERIC & row.keys():
            # Retain the existing bulk-import default for a blank process count.
            raw = row[field] or ("1" if field == "no_of_process_per_part" else None)
            row[field] = number(raw, f"Row {index + 1} {field}")
        unit_field = "uom" if category == "sales_parts" else "output_unit"
        if explicit_unit_columns:
            # A separate Unit/UOM column is authoritative even if the row is blank.
            # Do not fall back to numeric Output/Unit productivity values.
            row[unit_field] = legacy._extract_field(source, explicit_unit_columns).upper()[:16]
        else:
            row[unit_field] = (row[unit_field] or "PCS").upper()[:16]
        for field, value in row.items():
            if isinstance(value, str) and len(value) > LENGTHS.get(field, 2000 if "description" in field else 255):
                raise ApplicationError("INVALID_MASTER_VALUE", f"Row {index + 1}: {field} is too long.", 422)
        if key in rows:
            duplicates.append({"identifier": str(key), "first_row": source_rows[key], "last_row": int(index) + 1})
        source_rows[key] = int(index) + 1
        rows[key] = row  # Existing importer behavior: the last duplicate identifier wins.
        if len(rows) > 10000:
            raise ApplicationError("SOURCE_TOO_LARGE", "Use at most 10,000 distinct master rows per upload.", 422)
    if not rows:
        raise ApplicationError("EMPTY_MASTER_UPLOAD", "No valid master rows found. Check the selected category and workbook headers.", 422)
    if report is not None:
        report.update(data_rows=len(frame), identified_rows=len(frame) - len(missing), unique_rows=len(rows),
                      missing_identifier_rows=missing, duplicate_rows=duplicates)
    return list(rows.values())


def upsert_rows(session, category, parsed, actor, reason):
    units = {unit.code: unit for unit in session.scalars(select(Unit))}
    suppliers = list(session.scalars(select(Supplier))) if category == "consumables" else []
    by_supplier_id = {str(item.id): item for item in suppliers}
    by_supplier_code = {item.code: item for item in suppliers}
    by_supplier_name = {item.name: item for item in suppliers}
    supplier_cache = {}
    def unit_for(code):
        if code not in units:
            units[code] = legacy.ensure_unit(session, code)
        return units[code]
    def supplier_for(ref, name):
        key = (ref, name)
        if key not in supplier_cache:
            found = by_supplier_id.get(ref) or by_supplier_code.get(ref.upper()[:64]) if ref else None
            if not ref and name:
                found = by_supplier_name.get(name)
            supplier_cache[key] = found or legacy.ensure_supplier(session, ref, name)
        return supplier_cache[key]
    model = MODELS[category]
    existing = list(session.scalars(select(model).order_by(model.id).with_for_update()))
    if category == "consumables":
        lookup = {row.item_id: row for row in existing}
    elif category == "sales_parts":
        lookup = {(row.part_number, row.item_id): row for row in existing}
    else:
        lookup = {(row.product_id, row.process_id, row.consumable_id): row for row in existing}
    products, materials, processes = {}, {}, {}
    if category == "assemble":
        for row in session.scalars(select(Product)):
            products.setdefault(row.part_number, row)
            products.setdefault(row.code, row)
        for row in session.scalars(select(Consumable)):
            materials.setdefault(row.item_id, row)
            materials.setdefault(row.name, row)
        processes = {row.name.upper(): row for row in session.scalars(select(Process))}
    touched = {}
    for data in parsed:
        data = dict(data)
        if category == "consumables":
            key = data["item_id"]
            unit = unit_for(data["output_unit"])
            supplier = supplier_for(data["supplier_id"], data["supplier_name"])
            data.update(unit_id=unit.id, supplier_id=supplier.id if supplier else None,
                supplier_name=data["supplier_name"] or (supplier.name if supplier else None),
                name=(data["description"] or key)[:255])
        elif category == "sales_parts":
            key = (data["part_no"], data["item_id"])
            unit_for(data["uom"])
            data["part_number"] = data.pop("part_no")
            data["description"] = data.pop("part_description")
            data["name"] = data["description"][:255]
            data["code"] = f"{key[0]}_{key[1]}"[:128]
        else:
            part, material, process = data["part_no_saleable_item"], data["consumable_item"], data["process_name"].upper()
            if part not in products:
                products[part] = legacy._resolve_or_create_product(session, part, data["used_for_name_of_saleable_part"], data["output_unit"])
            if material not in materials:
                materials[material] = legacy._resolve_or_create_consumable(session, material, data["output_unit"])
            if process not in processes:
                processes[process] = legacy._resolve_or_create_process(session, process)
            key = (products[part].id, processes[process].id, materials[material].id)
            data.update(product_id=key[0], process_id=key[1], consumable_id=key[2], process_name=processes[process].name)
        row = lookup.get(key)
        old = snapshot(category, row) if row else None
        if row is None:
            row = model(id=uuid4())
            lookup[key] = row
            session.add(row)
        for field, value in data.items():
            setattr(row, field, value if value != "" else None)
        row.is_active = True
        touched[row.id] = row
        session.add(AuditLog(actor_id=actor.id, action="UPSERT", entity_type=model.__tablename__, entity_id=row.id,
            old_values=old, new_values=snapshot(category, row), reason=reason))
    return list(touched.values())


def import_period(session: Session, category, month, year, filename, content, actor):
    if not filename.lower().endswith(".xlsx"):
        raise ApplicationError("INVALID_EXCEL", "Choose an .xlsx workbook.", 422)
    parsed = parse(category, content)
    try:
        # Serialize cleanup and all period mutations before taking row locks.
        lock_category(session, category)
        previous = active_batch(session, category, month, year, lock=True)
        if previous:
            raise ApplicationError("MASTER_PERIOD_EXISTS", "Delete the existing data for this month and year before uploading a new workbook.", 409)
        if existing_rows(session, category):
            raise ApplicationError("EXISTING_MASTER_DATA", "Review and delete the existing data without a month/year before uploading the new workbook.", 409)
        changed = upsert_rows(session, category, parsed, actor, f"Reviewed master upload for {month}/{year}.")
        batch = MasterUploadBatch(id=uuid4(), category=category, month=month, year=year, status="active", version=1,
            filename=filename[:255], records=[snapshot(category, row) for row in changed],
            created_by=actor.id, updated_by=actor.id)
        session.add(batch)
        audit(session, batch, actor, "BULK_IMPORT", {"replaced_batch": str(previous.id)} if previous else None,
              {"rows": len(batch.records), "file_sha256": sha256(content).hexdigest()}, "Product Master period upload.")
        session.commit()
        return view(batch, category, month, year)
    except IntegrityError:
        session.rollback()
        raise ApplicationError("MASTER_UPLOAD_CONFLICT", "Master identifiers conflict or another upload changed this period. Refresh before retrying.", 409) from None
    except Exception:
        session.rollback()
        raise


def locked_batch(session, category, month, year, payload):
    batch = session.scalar(select(MasterUploadBatch).where(MasterUploadBatch.id == payload.batch_id,
        MasterUploadBatch.category == category, MasterUploadBatch.month == month, MasterUploadBatch.year == year)
        .with_for_update().execution_options(populate_existing=True))
    if batch is None:
        raise ApplicationError("MASTER_UPLOAD_NOT_FOUND", "This upload does not belong to the selected month, year and category.", 404)
    return batch


def save_period(session, category, month, year, payload: MasterPeriodSave, actor):
    try:
        lock_category(session, category)
        batch = locked_batch(session, category, month, year, payload)
        if batch.status != "active" or batch.version != payload.version:
            raise ApplicationError("MASTER_UPLOAD_CHANGED", "This upload has changed. Refresh before saving.", 409)
        original = {row["id"]: row for row in batch.records}
        model = MODELS[category]
        canonical = {str(row.id): row for row in session.scalars(select(model).where(
            model.id.in_([update.id for update in payload.updates])).order_by(model.id)
            .with_for_update().execution_options(populate_existing=True))}
        replacements = {}
        for update in payload.updates:
            key = str(update.id)
            if key not in original or key not in canonical or set(update.changes) - EDITABLE[category].keys():
                raise ApplicationError("INVALID_MASTER_EDIT", "Choose an editable field from a row in this upload.", 422)
            row, before = canonical[key], original[key]
            if not row.is_active:
                raise ApplicationError("MASTER_CHANGED", "This master was removed from the active catalog. Refresh before saving.", 409)
            current = snapshot(category, row)
            for field in EDITABLE[category]:
                current_value = number(current[field], field) if field in NUMERIC else current[field] or None
                previous_value = number(before[field], field) if field in NUMERIC else before[field] or None
                if current_value != previous_value:
                    raise ApplicationError("MASTER_CHANGED", "This shared master was changed after this upload. Re-upload the current data before editing this period.", 409)
            for field, raw in update.changes.items():
                value = number(raw, field) if field in NUMERIC else (raw or "").strip() or None
                limit = EDITABLE[category][field]
                if limit and value and len(value) > limit:
                    raise ApplicationError("INVALID_MASTER_VALUE", f"{field}: use at most {limit} characters.", 422)
                if value is None and field in {"part_description", "no_of_process_per_part"}:
                    raise ApplicationError("INVALID_MASTER_VALUE", f"{field} is required.", 422)
                setattr(row, ALIASES.get(category, {}).get(field, field), value)
                if field in {"description", "part_description"} and value:
                    row.name = value[:255]
            replacements[key] = snapshot(category, row)
            session.add(AuditLog(actor_id=actor.id, action="UPDATE", entity_type=model.__tablename__, entity_id=row.id,
                old_values=current, new_values=replacements[key], reason=f"Master upload correction for {month}/{year}."))
        batch.records = [replacements.get(row["id"], row) for row in batch.records]
        batch.version += 1
        batch.updated_by, batch.updated_at = actor.id, datetime.now(timezone.utc)
        audit(session, batch, actor, "UPDATE", {"version": payload.version},
              {"version": batch.version, "updated_ids": list(replacements)}, "Saved reviewed Product Master changes.")
        session.commit()
        return view(batch, category, month, year)
    except Exception:
        session.rollback()
        raise


def delete_period(session, category, month, year, payload: MasterPeriodDelete, actor):
    try:
        lock_category(session, category)
        batch = locked_batch(session, category, month, year, payload)
        if batch.status == "deleted":
            return {"deleted": True, "replayed": True}
        if batch.status != "active" or batch.version != payload.version:
            raise ApplicationError("MASTER_UPLOAD_CHANGED", "This upload has changed. Refresh before deleting.", 409)
        # Only rows exclusive to the selected period leave the active catalog.
        # Other active periods still own their shared IDs; all FKs/history remain.
        shared = tracked_ids(session, category, active_only=True, exclude_batch=batch.id)
        ids = [record["id"] for record in batch.records if record["id"] not in shared]
        model = MODELS[category]
        rows = list(session.scalars(select(model).where(model.id.in_([UUID(value) for value in ids]),
            model.is_active.is_(True)).order_by(model.id).with_for_update().execution_options(populate_existing=True)))
        deactivate_rows(session, category, rows, actor, payload.reason)
        batch.status, batch.updated_by, batch.updated_at = "deleted", actor.id, datetime.now(timezone.utc)
        batch.version += 1
        audit(session, batch, actor, "DELETE", {"status": "active"},
              {"status": "deleted", "rows": len(batch.records), "deactivated_count": len(rows)}, payload.reason)
        session.commit()
        return {"deleted": True, "deactivated_count": len(rows), "replayed": False}
    except Exception:
        session.rollback()
        raise


def export_period(session, category, month, year):
    batch = active_batch(session, category, month, year)
    if batch is None:
        raise ApplicationError("MASTER_UPLOAD_NOT_FOUND", "No uploaded data for this period.", 404)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Product Master"
    fields = list(FIELDS[category])
    sheet.append(fields)
    for record in batch.records:
        values = []
        for field in fields:
            value = record.get(field)
            if field in NUMERIC:
                value = number(value, field)
            values.append(value)
        sheet.append(values)
        # Store identifiers/text literally, retaining round-trip values without
        # allowing a description beginning '=' to become an Excel formula.
        for cell, value in zip(sheet[sheet.max_row], values):
            if isinstance(value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
