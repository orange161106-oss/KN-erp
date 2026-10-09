from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import re
from typing import Any, Sequence
from uuid import UUID

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.masters import Customer, Product
from app.models.prd import ImportBatch, ImportError, PlanningVersion, PRDOrderHeader, PRDOrderItem

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

HEADER_ALIASES = {
    "product_code": {"product code", "product_code", "part number", "part_number", "part no", "product", "item code"},
    "plant_code": {"plant code", "plant_code", "plant", "facility", "plant id"},
    "planned_quantity": {"planned quantity", "planned_quantity", "quantity", "qty", "planned qty", "plan qty"},
    "uom": {"uom", "unit", "unit of measure"},
    "target_period": {"target period", "target_period", "period", "month", "planning period"},
    "customer_code": {"customer code", "customer_code", "customer"},
}


class PRDValidationError(ApplicationError):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict[str, Any] | None = None):
        super().__init__(code=code, message=message, status_code=status_code, details=details)


def parse_headers(row_values: list[Any]) -> dict[str, int]:
    col_mapping: dict[str, int] = {}
    for idx, cell in enumerate(row_values):
        if cell is None:
            continue
        header_text = str(cell).strip().lower()
        for field, aliases in HEADER_ALIASES.items():
            if header_text in aliases and field not in col_mapping:
                col_mapping[field] = idx
                break
    return col_mapping


def stage_and_validate_prd_file(
    db: Session,
    file_bytes: bytes,
    filename: str,
    planning_period: str,
    user_id: UUID,
) -> ImportBatch:
    # 1. File checks
    if len(file_bytes) == 0:
        raise PRDValidationError("EMPTY_FILE", "Uploaded file is empty (0 bytes)")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise PRDValidationError("FILE_TOO_LARGE", f"File size exceeds maximum allowed of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB")

    if not filename.lower().endswith(".xlsx"):
        raise PRDValidationError("INVALID_FILE_TYPE", "Only .xlsx files are supported")

    # Normalize planning_period
    period_clean = planning_period.strip()
    if not re.match(r"^\d{4}-\d{2}$", period_clean):
        raise PRDValidationError("INVALID_PERIOD", "Planning period must follow format YYYY-MM (e.g. 2026-10)")

    # 2. Open with openpyxl
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        raise PRDValidationError("CORRUPTED_FILE", f"Unable to parse Excel file: {str(e)}")

    sheet = workbook.active
    if sheet is None:
        raise PRDValidationError("EMPTY_FILE", "Excel workbook contains no sheets")

    # Read rows
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        first_row = next(rows_iter, None)
    except Exception as e:
        raise PRDValidationError("UNREADABLE_SHEET", f"Error reading sheet: {str(e)}")

    if not first_row:
        raise PRDValidationError("EMPTY_FILE", "Worksheet is completely empty")

    # Parse headers
    header_map = parse_headers(list(first_row))
    missing_required = []
    for req in ("product_code", "plant_code", "planned_quantity"):
        if req not in header_map:
            missing_required.append(req.replace("_", " ").title())

    batch = ImportBatch(
        filename=filename,
        file_size_bytes=len(file_bytes),
        status="STAGING",
        uploaded_by=user_id,
    )
    db.add(batch)
    db.flush()

    if missing_required:
        batch.status = "FAILED"
        batch.row_count = 0
        batch.error_row_count = 1
        batch.completed_at = datetime.now(timezone.utc)
        error = ImportError(
            import_batch_id=batch.id,
            row_number=1,
            column_name="Headers",
            error_code="MISSING_HEADERS",
            error_message=f"Missing required columns: {', '.join(missing_required)}",
            raw_value=str(first_row),
        )
        db.add(error)
        db.commit()
        db.refresh(batch)
        return batch

    # Load active products for validation
    active_products = {p.code: p.id for p in db.scalars(select(Product).where(Product.is_active.is_(True))).all()}
    active_customers = {c.code: c.id for c in db.scalars(select(Customer).where(Customer.is_active.is_(True))).all()}

    total_data_rows = 0
    errors: list[ImportError] = []
    valid_staged_items: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    row_num = 1
    for row in rows_iter:
        row_num += 1
        # Skip empty rows
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        total_data_rows += 1
        row_has_error = False

        # 1. Product Code
        prod_val = row[header_map["product_code"]] if header_map["product_code"] < len(row) else None
        prod_code = str(prod_val).strip() if prod_val is not None else ""
        if not prod_code:
            errors.append(ImportError(
                import_batch_id=batch.id,
                row_number=row_num,
                column_name="Product Code",
                error_code="MISSING_FIELD",
                error_message="Product code is required",
                raw_value=str(prod_val),
            ))
            row_has_error = True
        elif prod_code not in active_products:
            errors.append(ImportError(
                import_batch_id=batch.id,
                row_number=row_num,
                column_name="Product Code",
                error_code="UNKNOWN_PRODUCT",
                error_message=f"Product code '{prod_code}' is not registered in Product Master",
                raw_value=prod_code,
            ))
            row_has_error = True

        # 2. Plant Code
        plant_val = row[header_map["plant_code"]] if header_map["plant_code"] < len(row) else None
        plant_code = str(plant_val).strip() if plant_val is not None else ""
        if not plant_code:
            errors.append(ImportError(
                import_batch_id=batch.id,
                row_number=row_num,
                column_name="Plant Code",
                error_code="MISSING_FIELD",
                error_message="Plant code is required",
                raw_value=str(plant_val),
            ))
            row_has_error = True

        # 3. Planned Quantity
        qty_dec = Decimal("0")
        qty_val = row[header_map["planned_quantity"]] if header_map["planned_quantity"] < len(row) else None
        if qty_val is None or str(qty_val).strip() == "":
            errors.append(ImportError(
                import_batch_id=batch.id,
                row_number=row_num,
                column_name="Planned Quantity",
                error_code="MISSING_FIELD",
                error_message="Planned quantity is required",
                raw_value=None,
            ))
            row_has_error = True
        else:
            try:
                qty_dec = Decimal(str(qty_val).strip())
                if qty_dec <= Decimal("0"):
                    errors.append(ImportError(
                        import_batch_id=batch.id,
                        row_number=row_num,
                        column_name="Planned Quantity",
                        error_code="INVALID_QUANTITY",
                        error_message="Planned quantity must be strictly greater than 0",
                        raw_value=str(qty_val),
                    ))
                    row_has_error = True
            except (InvalidOperation, ValueError):
                errors.append(ImportError(
                    import_batch_id=batch.id,
                    row_number=row_num,
                    column_name="Planned Quantity",
                    error_code="INVALID_QUANTITY",
                    error_message=f"Invalid numeric quantity: '{qty_val}'",
                    raw_value=str(qty_val),
                ))
                row_has_error = True

        # 4. Target Period
        row_period = period_clean
        if "target_period" in header_map and header_map["target_period"] < len(row):
            t_val = row[header_map["target_period"]]
            if t_val is not None and str(t_val).strip():
                row_period = str(t_val).strip()
                if not re.match(r"^\d{4}-\d{2}$", row_period):
                    errors.append(ImportError(
                        import_batch_id=batch.id,
                        row_number=row_num,
                        column_name="Target Period",
                        error_code="INVALID_PERIOD",
                        error_message=f"Target period '{row_period}' must follow YYYY-MM format",
                        raw_value=str(t_val),
                    ))
                    row_has_error = True

        # 5. UOM (optional, default PCS)
        uom_str = "PCS"
        if "uom" in header_map and header_map["uom"] < len(row):
            u_val = row[header_map["uom"]]
            if u_val is not None and str(u_val).strip():
                uom_str = str(u_val).strip().upper()

        # 6. Customer (optional)
        customer_id_str = None
        if "customer_code" in header_map and header_map["customer_code"] < len(row):
            c_val = row[header_map["customer_code"]]
            if c_val is not None and str(c_val).strip():
                c_code = str(c_val).strip()
                if c_code in active_customers:
                    customer_id_str = str(active_customers[c_code])

        # 7. Duplicate Check within sheet
        if prod_code and plant_code and not row_has_error:
            key = (prod_code, plant_code, row_period)
            if key in seen_keys:
                errors.append(ImportError(
                    import_batch_id=batch.id,
                    row_number=row_num,
                    column_name="Row",
                    error_code="DUPLICATE_ROW",
                    error_message=f"Duplicate entry for Product '{prod_code}' at Plant '{plant_code}' for period '{row_period}'",
                    raw_value=f"{prod_code}|{plant_code}|{row_period}",
                ))
                row_has_error = True
            else:
                seen_keys.add(key)

        if not row_has_error:
            valid_staged_items.append({
                "source_row_number": row_num,
                "product_code": prod_code,
                "product_id": str(active_products[prod_code]),
                "plant_code": plant_code,
                "planned_quantity": str(qty_dec),
                "uom": uom_str,
                "target_period": row_period,
                "customer_id": customer_id_str,
            })

    if total_data_rows == 0:
        batch.status = "FAILED"
        batch.row_count = 0
        batch.error_row_count = 1
        batch.completed_at = datetime.now(timezone.utc)
        error = ImportError(
            import_batch_id=batch.id,
            row_number=1,
            column_name="Data",
            error_code="NO_DATA_ROWS",
            error_message="Sheet contains header row but zero data rows",
        )
        db.add(error)
        db.commit()
        db.refresh(batch)
        return batch

    batch.row_count = total_data_rows
    if errors:
        batch.status = "FAILED"
        batch.error_row_count = len(errors)
        batch.valid_row_count = max(0, total_data_rows - len({e.row_number for e in errors}))
        for err in errors:
            db.add(err)
    else:
        batch.status = "VALIDATED"
        batch.valid_row_count = total_data_rows
        batch.error_row_count = 0
        batch.staged_data = valid_staged_items

    batch.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(batch)
    return batch


def promote_batch_to_planning_version(
    db: Session,
    batch_id: UUID,
    user_id: UUID,
    planning_period: str = "2026-10",
    revision_label: str = "R0",
) -> tuple[PlanningVersion, PRDOrderHeader, int]:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise PRDValidationError("NOT_FOUND", "Import batch not found", status_code=404)

    if batch.status != "VALIDATED":
        raise PRDValidationError("BATCH_NOT_VALIDATED", f"Only VALIDATED batches can be promoted (current status: {batch.status})")

    if not batch.staged_data:
        raise PRDValidationError("NO_STAGED_DATA", "Batch contains no staged valid items to promote")

    # Revision identity comes from the source, not upload arrival order.
    if not re.fullmatch(r"R(?:0|[1-9][0-9]*)", revision_label.strip().upper()):
        raise PRDValidationError("INVALID_REVISION", "Use a numeric revision such as R0 or R3", 422)
    revision_label = revision_label.strip().upper()
    existing_versions = db.scalars(
        select(PlanningVersion).where(PlanningVersion.planning_period == planning_period).order_by(PlanningVersion.version_number.desc())
    ).all()

    next_version_num = int(revision_label[1:])
    if any(v.version_number == next_version_num for v in existing_versions):
        raise PRDValidationError("PRD_REVISION_EXISTS", "This period/revision already exists; use a new revision for changes", 409)
    label = revision_label

    version = PlanningVersion(
        planning_period=planning_period,
        version_number=next_version_num,
        revision_label=label,
        source_filename=batch.filename,
        status="VALIDATED",
        created_by=user_id,
    )
    db.add(version)
    db.flush()

    batch.planning_version_id = version.id
    batch.status = "PROMOTED"

    total_qty = Decimal("0.0000")
    header = PRDOrderHeader(
        planning_version_id=version.id,
        import_batch_id=batch.id,
        planning_period=planning_period,
        total_planned_qty=Decimal("0.0000"),
        total_line_items=len(batch.staged_data),
    )
    db.add(header)
    db.flush()

    for item_data in batch.staged_data:
        qty_dec = Decimal(item_data["planned_quantity"])
        total_qty += qty_dec
        prd_item = PRDOrderItem(
            planning_version_id=version.id,
            header_id=header.id,
            source_row_number=item_data["source_row_number"],
            product_code=item_data["product_code"],
            product_id=UUID(item_data["product_id"]),
            plant_code=item_data["plant_code"],
            planned_quantity=qty_dec,
            uom=item_data["uom"],
            target_period=item_data["target_period"],
            customer_id=UUID(item_data["customer_id"]) if item_data.get("customer_id") else None,
        )
        db.add(prd_item)

    header.total_planned_qty = total_qty
    db.commit()
    db.refresh(version)
    db.refresh(header)
    return version, header, len(batch.staged_data)


def get_import_batch(db: Session, batch_id: UUID) -> ImportBatch | None:
    return db.get(ImportBatch, batch_id)


def list_import_batches(db: Session) -> Sequence[ImportBatch]:
    return db.scalars(select(ImportBatch).order_by(ImportBatch.uploaded_at.desc())).all()


def list_import_errors(db: Session, batch_id: UUID) -> Sequence[ImportError]:
    return db.scalars(select(ImportError).where(ImportError.import_batch_id == batch_id).order_by(ImportError.row_number)).all()


def list_planning_versions(db: Session) -> Sequence[PlanningVersion]:
    return db.scalars(select(PlanningVersion).order_by(PlanningVersion.created_at.desc())).all()


def get_planning_version_items(db: Session, version_id: UUID) -> Sequence[PRDOrderItem]:
    return db.scalars(select(PRDOrderItem).where(PRDOrderItem.planning_version_id == version_id).order_by(PRDOrderItem.source_row_number)).all()
