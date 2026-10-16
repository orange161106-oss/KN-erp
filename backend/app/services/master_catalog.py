"""Undated master catalog with read-only upload preview and explicit atomic save."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.master_uploads import MasterUploadBatch
from app.models.inventory_masters import Consumable, Unit
from app.repositories.inventory import has_stock_records
from app.repositories.inventory_masters import has_supplier_mapping
from app.schemas.master_uploads import MasterCatalogSave, MasterCatalogView
from app.services import master_uploads as shared

OPTIONAL_UNIT_CATEGORIES = {"consumables", "assemble"}


def catalog_id(category):
    return uuid5(NAMESPACE_URL, f"knl/master-catalog/{category}")


def rows_for(session, category, *, lock=False):
    model = shared.MODELS[category]
    query = select(model).where(model.is_active.is_(True)).order_by(model.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return list(session.scalars(query))


def token_for(category, rows):
    evidence = []
    for row in rows:
        values = shared.snapshot(category, row)
        # DB NUMERIC reads have four places; newly saved Decimal values may not.
        # Equivalent values must keep the same review token across sessions.
        for field in shared.NUMERIC & values.keys():
            if values[field] is not None:
                values[field] = format(Decimal(values[field]), ".4f")
        evidence.append((values, str(row.updated_at)))
    return sha256(json.dumps([category, evidence], sort_keys=True).encode()).hexdigest()


def get_catalog(session, category):
    rows = rows_for(session, category)
    latest = session.scalar(select(AuditLog).where(AuditLog.entity_type == "MasterCatalog",
        AuditLog.entity_id == catalog_id(category), AuditLog.action == "BULK_IMPORT")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1))
    filename = latest.new_values.get("filename") if latest else None
    report = latest.new_values.get("report", {}) if latest else {}
    if latest is None:
        previous = session.scalar(select(MasterUploadBatch).where(MasterUploadBatch.category == category,
            MasterUploadBatch.status == "active").order_by(MasterUploadBatch.updated_at.desc()).limit(1))
        filename = previous.filename if previous else None
    return MasterCatalogView(category=category, review_token=token_for(category, rows), row_count=len(rows),
        records=[shared.snapshot(category, row) for row in rows], filename=filename if rows else None, report=report if rows else {})


def draft_id(category, row):
    keys = {"consumables": ["item_id"], "sales_parts": ["part_no", "item_id"],
            "assemble": ["consumable_item", "part_no_saleable_item", "process_name"]}[category]
    return str(uuid5(catalog_id(category), json.dumps([row[key] for key in keys])))


def unit_field(category):
    return "uom" if category == "sales_parts" else "output_unit"


def valid_unit(value):
    if not value or len(value) > 16 or not re.search(r"[A-Za-z]", value):
        return False
    try:
        Decimal(value.replace(",", ""))
    except InvalidOperation:
        return True
    return False


def unit_errors(category, records):
    field = unit_field(category)
    return [{"id": row["id"], "field": field,
             "message": f"{row.get('item_id') or row.get('consumable_item')}: enter a stock unit such as PCS or KG; {row[field] or 'blank'} is not a unit label."}
            for row in records if not valid_unit(row[field])
            and not (category in OPTIONAL_UNIT_CATEGORIES and not row[field])]


def prepared(category, content):
    report = {}
    parsed = shared.parse(category, content, report=report, optional_stock_units=True)
    if category in OPTIONAL_UNIT_CATEGORIES:
        deferred = []
        for row in parsed:
            value = row["output_unit"]
            if not valid_unit(value):
                if value:
                    deferred.append({"identifier": row.get("item_id") or row.get("consumable_item"),
                        "part_no": row.get("part_no_saleable_item"), "process": row.get("process_name"),
                        "source_value": value})
                row["output_unit"] = None
        if deferred:
            report["deferred_stock_units"] = deferred
    records = [{"id": draft_id(category, row), **{key: str(value) if value is not None else None for key, value in row.items()}}
               for row in parsed]
    return parsed, records, report


def preview(session, category, filename, content):
    if not filename.lower().endswith(".xlsx"):
        raise ApplicationError("INVALID_EXCEL", "Choose an .xlsx workbook.", 422)
    _, records, report = prepared(category, content)
    return MasterCatalogView(category=category, review_token=token_for(category, rows_for(session, category)),
        row_count=len(records), records=records, filename=filename[:255], report=report,
        validation_errors=unit_errors(category, records))


def apply_edits(category, row, changes, *, staged=False):
    allowed = {**shared.EDITABLE[category]}
    if staged or category in OPTIONAL_UNIT_CATEGORIES:
        allowed[unit_field(category)] = 16
    if set(changes) - allowed.keys():
        raise ApplicationError("INVALID_MASTER_EDIT", "Choose an editable field. Master identifiers and references are protected.", 422)
    for field, raw in changes.items():
        value = shared.number(raw, field) if field in shared.NUMERIC else (raw or "").strip() or None
        limit = allowed[field]
        if limit and value and len(value) > limit:
            raise ApplicationError("INVALID_MASTER_VALUE", f"{field}: use at most {limit} characters.", 422)
        if field == unit_field(category) and value:
            value = value.upper()
            if not valid_unit(value):
                raise ApplicationError("INVALID_MASTER_UNIT", "Enter a stock unit such as PCS or KG, or leave it blank to add later.", 422)
        if value is None and field in {"part_description", "no_of_process_per_part"}:
            raise ApplicationError("INVALID_MASTER_VALUE", f"{field} is required.", 422)
        row[field] = value


def archive_periods(session, category, actor, reason, *, deleted=False):
    # Preserve every former monthly snapshot as historical evidence. New catalog
    # operations never create or choose an artificial month/year.
    batches = session.scalars(select(MasterUploadBatch).where(MasterUploadBatch.category == category,
        MasterUploadBatch.status == "active").order_by(MasterUploadBatch.id).with_for_update())
    for batch in batches:
        before = {"status": batch.status, "version": batch.version}
        batch.status = "deleted" if deleted else "superseded"
        batch.version += 1
        batch.updated_by, batch.updated_at = actor.id, datetime.now(timezone.utc)
        shared.audit(session, batch, actor, "DELETE" if deleted else "SUPERSEDE", before,
                     {"status": batch.status, "version": batch.version}, reason)


def record_audit(session, category, actor, action, values, reason):
    session.add(AuditLog(actor_id=actor.id, action=action, entity_type="MasterCatalog", entity_id=catalog_id(category),
                        new_values={"category": category, **values}, reason=reason))


def save_upload(session, category, filename, content, payload: MasterCatalogSave, actor):
    if not filename.lower().endswith(".xlsx"):
        raise ApplicationError("INVALID_EXCEL", "Choose an .xlsx workbook.", 422)
    parsed, records, report = prepared(category, content)
    updates = {str(update.id): update.changes for update in payload.updates}
    if updates.keys() - {record["id"] for record in records}:
        raise ApplicationError("INVALID_MASTER_EDIT", "An edited row does not belong to this workbook. Upload it again.", 422)
    for row, record in zip(parsed, records):
        apply_edits(category, row, updates.get(record["id"], {}), staged=True)
        record.update({key: str(value) if value is not None else None for key, value in row.items()})
    errors = unit_errors(category, records)
    if errors:
        raise ApplicationError("INVALID_MASTER_UNIT", f"{len(errors)} rows need a valid stock unit. Review the Unit column before saving.", 422,
                               {"errors": errors[:20]})
    try:
        shared.lock_category(session, category)
        existing = rows_for(session, category, lock=True)
        if token_for(category, existing) != payload.review_token:
            raise ApplicationError("MASTER_CHANGED", "The catalog changed after preview. Refresh before saving.", 409)
        if existing:
            raise ApplicationError("MASTER_CATALOG_EXISTS", "Delete the existing data before saving a replacement workbook.", 409)
        reason = "Reviewed Product Master workbook saved."
        changed = shared.upsert_rows(session, category, parsed, actor, reason, optional_stock_units=True)
        archive_periods(session, category, actor, reason)
        session.flush()
        record_audit(session, category, actor, "BULK_IMPORT", {"filename": filename[:255], "rows": len(changed),
            "file_sha256": sha256(content).hexdigest(), "report": report}, reason)
        session.commit()
        return get_catalog(session, category)
    except IntegrityError:
        session.rollback()
        raise ApplicationError("MASTER_UPLOAD_CONFLICT", "Master identifiers conflict. Refresh and review before saving.", 409) from None
    except Exception:
        session.rollback()
        raise


def save_changes(session, category, payload: MasterCatalogSave, actor):
    try:
        shared.lock_category(session, category)
        rows = rows_for(session, category, lock=True)
        if token_for(category, rows) != payload.review_token:
            raise ApplicationError("MASTER_CHANGED", "The catalog changed. Refresh before saving.", 409)
        by_id = {str(row.id): row for row in rows}
        for update in payload.updates:
            row = by_id.get(str(update.id))
            if row is None:
                raise ApplicationError("INVALID_MASTER_EDIT", "Choose a row in the active catalog.", 422)
            before = shared.snapshot(category, row)
            values = dict(before)
            apply_edits(category, values, update.changes)
            if category in OPTIONAL_UNIT_CATEGORIES and "output_unit" in update.changes:
                update_stock_unit(session, category, row, values["output_unit"], actor)
            for field in update.changes:
                setattr(row, shared.ALIASES.get(category, {}).get(field, field), values[field])
                if field in {"description", "part_description"} and values[field]:
                    row.name = values[field][:255]
            session.add(AuditLog(actor_id=actor.id, action="UPDATE", entity_type=shared.MODELS[category].__tablename__,
                entity_id=row.id, old_values=before, new_values=shared.snapshot(category, row), reason="Reviewed master catalog correction."))
        if payload.updates:
            archive_periods(session, category, actor, "Master catalog correction replaced the former dated view.")
            session.flush()
            record_audit(session, category, actor, "UPDATE", {"updated_ids": [str(update.id) for update in payload.updates]},
                         "Saved Product Master changes.")
            session.commit()
        return get_catalog(session, category)
    except Exception:
        session.rollback()
        raise


def update_stock_unit(session, category, row, code, actor):
    material = row if category == "consumables" else session.scalar(select(Consumable).where(
        Consumable.id == row.consumable_id).with_for_update())
    # Assembly units may be left blank independently of an existing material's
    # reviewed canonical unit; adding a unit can resolve an unassigned material.
    if category == "assemble" and not code:
        return
    unit = session.scalar(select(Unit).where(Unit.code == code).with_for_update()) if code else None
    if unit is not None and not unit.is_active:
        raise ApplicationError("INACTIVE_REFERENCE", "Choose an active stock unit.", 409)
    if category == "assemble" and material.unit_id and (unit is None or material.unit_id != unit.id):
        raise ApplicationError("UNIT_CHANGE_CONFLICT", "This material already has a different stock unit. Review it in List of Consumables first.", 409)
    new_id = unit.id if unit else None
    if material.unit_id != new_id or code and unit is None:
        if has_stock_records(session, material.id) or has_supplier_mapping(session, material.id):
            raise ApplicationError("UNIT_CHANGE_CONFLICT", "Stock unit cannot change after stock history or a supplier mapping exists.", 409)
    before = shared.snapshot("consumables", material)
    if code and unit is None:
        unit = shared.legacy.ensure_unit(session, code)
    material.unit_id, material.output_unit = (unit.id, unit.code) if unit else (None, None)
    if category == "assemble" and shared.snapshot("consumables", material) != before:
        session.add(AuditLog(actor_id=actor.id, action="UPDATE", entity_type="consumables", entity_id=material.id,
            old_values=before, new_values=shared.snapshot("consumables", material), reason="Reviewed assembly stock unit supplied."))


def delete_catalog(session, category, payload, actor):
    try:
        shared.lock_category(session, category)
        rows = rows_for(session, category, lock=True)
        if token_for(category, rows) != payload.review_token:
            raise ApplicationError("MASTER_CHANGED", "The catalog changed after review. Refresh before deleting.", 409)
        if rows:
            shared.deactivate_rows(session, category, rows, actor, payload.reason)
            archive_periods(session, category, actor, payload.reason, deleted=True)
            record_audit(session, category, actor, "DELETE", {"rows": len(rows)}, payload.reason)
            session.commit()
        return get_catalog(session, category)
    except Exception:
        session.rollback()
        raise


def export_catalog(session, category):
    catalog = get_catalog(session, category)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Product Master"
    fields = list(shared.FIELDS[category])
    sheet.append(fields)
    for row in catalog.records:
        values = [Decimal(row[key]) if key in shared.NUMERIC and row[key] is not None else row[key] for key in fields]
        sheet.append(values)
        for cell, value in zip(sheet[sheet.max_row], values):
            if isinstance(value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
