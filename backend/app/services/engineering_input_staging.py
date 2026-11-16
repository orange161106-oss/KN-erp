"""Retain engineering collection workbook rows without applying them to live masters."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from typing import Any
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.prd import ImportBatch
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Plant, Process
from app.models.rules import ConsumptionNorm

MAX_BYTES = 10 * 1024 * 1024
WORKFLOW = "ENGINEERING_INPUT_COLLECTION_V1"

SHEETS: dict[str, tuple[str, ...]] = {
    "Process Verification": (
        "Product Code", "Product Description", "Consumable Code", "Consumable Description",
        "Proposed Process", "Engineering Decision", "Correct Process (if different)",
        "Remarks / Reason", "Approver Name & Designation", "Approval Date",
        "Approval Ref. / Document No.",
    ),
    "Tool Life Details": (
        "Product Code", "Product Description", "Tool / Consumable Code", "Tool / Consumable Description",
        "Operations Required per Product", "Rated Tool Life", "Tool-Life Measurement Basis",
        "Engineering Rule Decision", "Remarks / Conditions", "Approver Name & Designation",
        "Approval Date", "Approval Ref. / Document No.",
    ),
    "Product Consumable BOM": (
        "Product Code", "Product Description", "Plant", "Scheduled Production Qty (reference)",
        "Consumable Code", "Consumable Description", "Standard Consumption per 1 Product", "UOM",
        "Rule Type (Engineering to confirm)", "Process Name", "Valid From", "Valid Until",
        "Remarks / Conditions", "Approver Name & Designation", "Approval Date", "Approval Ref. / BOM Document No.",
    ),
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "Process Verification": (
        "Product Code", "Consumable Code", "Proposed Process", "Engineering Decision", "Approver Name & Designation",
        "Approval Date", "Approval Ref. / Document No.",
    ),
    "Tool Life Details": (
        "Product Code", "Tool / Consumable Code", "Engineering Rule Decision", "Approver Name & Designation",
        "Approval Date", "Approval Ref. / Document No.",
    ),
    "Product Consumable BOM": (
        "Product Code", "Plant", "Consumable Code", "Standard Consumption per 1 Product", "UOM",
        "Rule Type (Engineering to confirm)", "Process Name", "Valid From",
        "Approver Name & Designation", "Approval Date", "Approval Ref. / BOM Document No.",
    ),
}


def _cell(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _has_value(value: Any) -> bool:
    return value is not None and bool(str(value).strip())


def _positive_number(value: Any) -> bool:
    try:
        parsed = Decimal(str(value).strip())
        return parsed.is_finite() and parsed > 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _valid_date(value: Any) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    raw = str(value or "").strip()
    if not raw:
        return False
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            datetime.strptime(raw, pattern)
            return True
        except ValueError:
            continue
    return False


def _parsed_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def _preview(filename: str, content: bytes) -> dict[str, Any]:
    if not filename.lower().endswith(".xlsx") or not content or len(content) > MAX_BYTES:
        raise ApplicationError("INVALID_ENGINEERING_INPUT_FILE", "Choose a nonempty .xlsx workbook no larger than 10 MB.", 422)
    try:
        # Preserve formulas as their original expressions rather than losing them
        # when a workbook has no cached formula result.
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
    except Exception:
        raise ApplicationError("INVALID_ENGINEERING_INPUT_FILE", "The engineering input workbook could not be read.", 422) from None
    try:
        missing_sheets = [name for name in SHEETS if name not in workbook.sheetnames]
        if missing_sheets:
            raise ApplicationError("ENGINEERING_INPUT_SHEETS_MISSING", "The workbook is missing a required engineering sheet.", 422,
                details={"missing_sheets": missing_sheets})
        sheets: dict[str, dict[str, Any]] = {}
        total_rows = ready_rows = pending_rows = not_approved_rows = 0
        for name in SHEETS:
            worksheet = workbook[name]
            header = next(worksheet.iter_rows(min_row=4, max_row=4, values_only=True), ())
            columns = {str(value).strip(): idx for idx, value in enumerate(header) if value is not None and str(value).strip()}
            if "Ref. No." not in columns:
                raise ApplicationError("ENGINEERING_INPUT_HEADER_INVALID", f"The '{name}' sheet is missing its Ref. No. header.", 422)
            required = REQUIRED_FIELDS[name]
            records = []
            for excel_row, values in enumerate(worksheet.iter_rows(min_row=5, values_only=True), start=5):
                if not any(value is not None and str(value).strip() for value in values):
                    continue
                source = {str(header[idx]).strip(): _cell(value) for idx, value in enumerate(values)
                    if idx < len(header) and header[idx] is not None and str(header[idx]).strip()}
                absent = [field for field in required if not _has_value(source.get(field))]
                decision_field = "Engineering Decision" if name == "Process Verification" else "Engineering Rule Decision" if name == "Tool Life Details" else None
                decision = str(source.get(decision_field, "")).strip().upper() if decision_field else ""
                issues: list[str] = []
                warnings: list[str] = []
                if decision in {"REJECTED", "NOT APPROVED"}:
                    status = "NOT_APPROVED"
                else:
                    status = "PENDING"
                if name == "Process Verification":
                    if decision == "APPROVED":
                        pass
                    elif decision == "REJECTED":
                        status = "NOT_APPROVED"
                    else:
                        issues.append("Engineering Decision must be APPROVED or REJECTED; clarification is still pending.")
                    if _has_value(source.get("Correct Process (if different)")) and not _has_value(source.get("Remarks / Reason")):
                        absent.append("Remarks / Reason (required when proposing a different process)")
                elif name == "Tool Life Details":
                    if decision not in {"TOOL_LIFE", "PRODUCTION_RATE", "NOT_APPLICABLE"}:
                        issues.append("Engineering Rule Decision must be TOOL_LIFE, PRODUCTION_RATE or NOT_APPLICABLE.")
                    if decision == "TOOL_LIFE":
                        for field in ("Operations Required per Product", "Rated Tool Life"):
                            value = source.get(field)
                            if not _has_value(value):
                                absent.append(field)
                            elif not _positive_number(value):
                                issues.append(f"{field} must be a number greater than zero.")
                        if not _has_value(source.get("Tool-Life Measurement Basis")):
                            absent.append("Tool-Life Measurement Basis")
                    elif decision in {"PRODUCTION_RATE", "NOT_APPLICABLE"} and not _has_value(source.get("Remarks / Conditions")):
                        absent.append("Remarks / Conditions (required when tool life is not the selected rule)")
                else:
                    rule_type = str(source.get("Rule Type (Engineering to confirm)", "")).strip().upper()
                    allowed_rules = {"DIRECT", "PRODUCTION_RATE", "TOOL_LIFE", "AREA_COVERAGE", "PACKING_RATIO", "OTHER", "NEEDS_CLARIFICATION"}
                    if rule_type not in allowed_rules:
                        issues.append("Select an Engineering-confirmed rule type from the workbook list.")
                    elif rule_type == "NEEDS_CLARIFICATION":
                        issues.append("Engineering rule selection needs clarification.")
                    if _has_value(source.get("Standard Consumption per 1 Product")) and not _positive_number(source.get("Standard Consumption per 1 Product")):
                        issues.append("Standard Consumption per 1 Product must be a number greater than zero.")
                    if rule_type == "OTHER" and not _has_value(source.get("Remarks / Conditions")):
                        absent.append("Remarks / Conditions (required for OTHER rule type)")

                for field in ("Approval Date",):
                    if _has_value(source.get(field)) and not _valid_date(source[field]):
                        issues.append(f"{field} is not a recognizable date.")
                if name == "Product Consumable BOM":
                    for field in ("Valid From", "Valid Until"):
                        value = source.get(field)
                        if _has_value(value) and not _valid_date(value):
                            issues.append(f"{field} is not a recognizable date.")
                    start, end = source.get("Valid From"), source.get("Valid Until")
                    if _has_value(start) and _has_value(end) and _valid_date(start) and _valid_date(end):
                        start_date, end_date = _parsed_date(start), _parsed_date(end)
                        if start_date > end_date:
                            issues.append("Valid Until cannot be earlier than Valid From.")

                if status != "NOT_APPROVED" and not absent and not issues:
                    status = "READY_FOR_REVIEW"
                elif status != "NOT_APPROVED":
                    status = "PENDING"
                records.append({"source_row": excel_row, "reference": source.get("Ref. No."),
                    "status": status, "missing_fields": absent, "validation_issues": issues,
                    "warnings": warnings, "source_values": source})
                total_rows += 1
                ready_rows += status == "READY_FOR_REVIEW"
                pending_rows += status == "PENDING"
                not_approved_rows += status == "NOT_APPROVED"
            sheets[name] = {"row_count": len(records), "rows": records}
        return {"workflow": WORKFLOW, "filename": filename[:255],
            "source_sha256": sha256(content).hexdigest(), "total_rows": total_rows,
            "ready_rows": ready_rows, "pending_rows": pending_rows,
            "not_approved_rows": not_approved_rows, "sheets": sheets}
    finally:
        workbook.close()


def _add_master_checks(db, data: dict[str, Any]) -> dict[str, Any]:
    rows = [row for sheet in data["sheets"].values() for row in sheet["rows"]]
    product_codes = {str(row["source_values"].get("Product Code")).strip().upper() for row in rows
        if _has_value(row["source_values"].get("Product Code"))}
    consumable_codes = {str(row["source_values"].get(field)).strip().upper() for row in rows
        for field in ("Consumable Code", "Tool / Consumable Code") if _has_value(row["source_values"].get(field))}
    process_names = {str(row["source_values"].get(field)).strip().upper() for row in rows
        for field in ("Proposed Process", "Correct Process (if different)", "Process Name")
        if _has_value(row["source_values"].get(field))}
    plant_names = {str(row["source_values"].get("Plant")).strip().upper() for row in rows
        if _has_value(row["source_values"].get("Plant"))}
    unit_codes = {str(row["source_values"].get("UOM")).strip().upper() for row in rows
        if _has_value(row["source_values"].get("UOM"))}

    products: dict[str, list[Product]] = {}
    materials: dict[str, list[Consumable]] = {}
    processes: dict[str, list[Process]] = {}
    plants: dict[str, list[Plant]] = {}
    units: dict[str, list[Unit]] = {}
    if product_codes:
        for record in db.scalars(select(Product).where(func.upper(Product.code).in_(product_codes))).all():
            products.setdefault(record.code.strip().upper(), []).append(record)
    if consumable_codes:
        for record in db.scalars(select(Consumable).where(func.upper(Consumable.item_id).in_(consumable_codes))).all():
            materials.setdefault(record.item_id.strip().upper(), []).append(record)
    if process_names:
        for record in db.scalars(select(Process).where(func.upper(Process.name).in_(process_names))).all():
            processes.setdefault(record.name.strip().upper(), []).append(record)
    if plant_names:
        for record in db.scalars(select(Plant).where(func.upper(Plant.name).in_(plant_names))).all():
            plants.setdefault(record.name.strip().upper(), []).append(record)
    if unit_codes:
        for record in db.scalars(select(Unit).where(func.upper(Unit.code).in_(unit_codes))).all():
            units.setdefault(record.code.strip().upper(), []).append(record)
    product_ids = {record.id for matches in products.values() for record in matches}
    consumable_ids = {record.id for matches in materials.values() for record in matches}
    master_unit_ids = {record.unit_id for matches in materials.values() for record in matches if record.unit_id}
    master_units_by_id = {unit.id: unit for unit in db.scalars(select(Unit).where(Unit.id.in_(master_unit_ids))).all()} if master_unit_ids else {}
    norm_pairs: set[tuple[Any, Any]] = set()
    if product_ids and consumable_ids:
        norm_pairs = {(product_id, consumable_id) for product_id, consumable_id in db.execute(select(
            ConsumptionNorm.product_id, ConsumptionNorm.consumable_id
        ).where(
            ConsumptionNorm.is_active.is_(True), ConsumptionNorm.product_id.in_(product_ids),
            ConsumptionNorm.consumable_id.in_(consumable_ids)
        )).all()}

    def check_master(row: dict[str, Any], field: str, index: dict[str, list[Any]], label: str) -> None:
        value = row["source_values"].get(field)
        if not _has_value(value):
            return
        key = str(value).strip().upper()
        found = index.get(key, [])
        if not found:
            row["validation_issues"].append(f"{label} '{value}' is not in the current master data.")
        elif len(found) > 1:
            row["validation_issues"].append(f"{label} '{value}' matches multiple master records; resolve the duplicate.")
        elif not found[0].is_active:
            row["validation_issues"].append(f"{label} '{value}' is inactive in master data.")

    for name, sheet in data["sheets"].items():
        for row in sheet["rows"]:
            check_master(row, "Product Code", products, "Product code")
            check_master(row, "Consumable Code", materials, "Consumable code")
            check_master(row, "Tool / Consumable Code", materials, "Consumable code")
            check_master(row, "UOM", units, "Unit")
            if name == "Process Verification":
                process_field = "Correct Process (if different)" if _has_value(row["source_values"].get("Correct Process (if different)")) else "Proposed Process"
                check_master(row, process_field, processes, "Process")
            elif name == "Product Consumable BOM":
                check_master(row, "Process Name", processes, "Process")
                check_master(row, "Plant", plants, "Plant")
            product_value = row["source_values"].get("Product Code")
            consumable_field = "Tool / Consumable Code" if _has_value(row["source_values"].get("Tool / Consumable Code")) else "Consumable Code"
            consumable_value = row["source_values"].get(consumable_field)
            product_matches = products.get(str(product_value).strip().upper(), []) if _has_value(product_value) else []
            consumable_matches = materials.get(str(consumable_value).strip().upper(), []) if _has_value(consumable_value) else []
            if len(product_matches) == 1 and len(consumable_matches) == 1 and (product_matches[0].id, consumable_matches[0].id) in norm_pairs:
                row["warnings"].append("An active norm already exists for this product and consumable; review it before any correction.")
            uom_value = row["source_values"].get("UOM")
            if name == "Product Consumable BOM" and len(consumable_matches) == 1 and _has_value(uom_value):
                consumable = consumable_matches[0]
                master_unit = consumable.purchasing_unit or (
                    master_units_by_id[consumable.unit_id].code if consumable.unit_id in master_units_by_id else None
                )
                if master_unit and str(master_unit).strip().upper() != str(uom_value).strip().upper():
                    row["validation_issues"].append(f"Engineering UOM '{uom_value}' differs from the master purchasing unit '{master_unit}'; confirm compatibility before use.")
            if row["status"] == "READY_FOR_REVIEW" and row["validation_issues"]:
                row["status"] = "PENDING"

        # Keep duplicate source rows visible, but require review before either row can be used.
        duplicate_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in sheet["rows"]:
            source = row["source_values"]
            if name == "Process Verification":
                process = source.get("Correct Process (if different)") or source.get("Proposed Process")
                values = (source.get("Product Code"), source.get("Consumable Code"), process)
            elif name == "Tool Life Details":
                values = (source.get("Product Code"), source.get("Tool / Consumable Code"))
            else:
                values = (source.get("Product Code"), source.get("Consumable Code"), source.get("Plant"),
                    source.get("Process Name"), source.get("Valid From"))
            if all(_has_value(value) for value in values):
                key = tuple(str(value).strip().upper() for value in values)
                duplicate_groups.setdefault(key, []).append(row)
        for group in duplicate_groups.values():
            if len(group) > 1:
                for row in group:
                    row["validation_issues"].append("Duplicate engineering scope appears more than once in this workbook; review both source rows.")
                    if row["status"] == "READY_FOR_REVIEW":
                        row["status"] = "PENDING"

    data["ready_rows"] = sum(row["status"] == "READY_FOR_REVIEW" for row in rows)
    data["pending_rows"] = sum(row["status"] == "PENDING" for row in rows)
    data["not_approved_rows"] = sum(row["status"] == "NOT_APPROVED" for row in rows)
    return data


def preview(filename: str, content: bytes, db=None) -> dict[str, Any]:
    data = _preview(filename, content)
    return _add_master_checks(db, data) if db is not None else data


def save_staging(db, filename: str, content: bytes, actor_id: UUID) -> dict[str, Any]:
    data = preview(filename, content, db)
    existing = db.scalar(select(ImportBatch).where(ImportBatch.file_hash == data["source_sha256"],
        ImportBatch.validation_summary["workflow"].as_string() == WORKFLOW)
        .order_by(ImportBatch.uploaded_at.desc()).limit(1))
    if existing:
        return {"batch_id": str(existing.id), "filename": existing.filename,
            "uploaded_at": existing.uploaded_at.isoformat(), "status": existing.status,
            "replayed": True, "batch": existing.staged_data,
            "message": "This exact workbook is already retained in Engineering Inputs."}
    batch = ImportBatch(filename=filename[:255], file_size_bytes=len(content), row_count=data["total_rows"],
        valid_row_count=data["ready_rows"], error_row_count=data["total_rows"] - data["ready_rows"], status="STAGING",
        staged_data=data, file_hash=data["source_sha256"],
        validation_summary={"workflow": data["workflow"], "ready_rows": data["ready_rows"],
            "pending_rows": data["pending_rows"], "not_approved_rows": data["not_approved_rows"],
            "total_rows": data["total_rows"]}, uploaded_by=actor_id)
    db.add(batch)
    db.flush()
    db.add(AuditLog(actor_id=actor_id, action="STAGE_ENGINEERING_INPUTS", entity_type="ImportBatch",
        entity_id=batch.id, old_values=None, new_values={"filename": batch.filename, "row_count": batch.row_count,
            "ready_rows": data["ready_rows"], "pending_rows": data["pending_rows"],
            "not_approved_rows": data["not_approved_rows"], "source_sha256": data["source_sha256"]},
        reason="Retained engineering collection input rows; no masters or norms were changed."))
    db.commit()
    return {"batch_id": str(batch.id), "filename": batch.filename,
        "uploaded_at": batch.uploaded_at.isoformat(), "status": batch.status,
        "replayed": False, "batch": data,
        "message": f"Retained {data['total_rows']} source rows. Pending rows remain unused until completed and reviewed."}


def latest_staging(db) -> dict[str, Any] | None:
    batch = db.scalar(select(ImportBatch).where(
        ImportBatch.validation_summary["workflow"].as_string() == WORKFLOW
    ).order_by(ImportBatch.uploaded_at.desc()).limit(1))
    if not batch:
        return None
    return {"batch_id": str(batch.id), "filename": batch.filename, "uploaded_at": batch.uploaded_at.isoformat(),
        "status": batch.status, "batch": batch.staged_data}
