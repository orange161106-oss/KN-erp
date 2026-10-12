from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re
from typing import Any, Optional
import uuid

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable
from app.models.stock_statements import StockParameter, StockParameterBatch
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import (
    ComparisonSummary,
    RowIssue,
    StockManagementMetadata,
    StockManagementResponse,
    StockManagementSummary,
    StockParameterBatchUpdateRequest,
    StockParameterConfirmRequest,
    StockParameterHistoryItem,
    StockParameterPreviewResponse,
    StockParameterRecord,
)
from app.services.audit import log_audit_event


_PARAM_PREVIEW_STORE: dict[str, dict[str, Any]] = {}

EXPECTED_PARAMETER_COLUMNS = [
    "Item Id",
    "Category",
    "Type of material",
    "Description",
    "Min stock level",
    "Max stock level",
    "Minimum order qty.",
    "Lead time to supply in days",
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def normalize_header(text: Any) -> str:
    if not text:
        return ""
    clean = re.sub(r"\s+", " ", str(text)).strip().lower()
    return clean.replace(".", "")


def parse_raw_decimal(value: Any, row_num: int, col_name: str, issues: list[RowIssue]) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and (value != value or value == float("inf") or value == float("-inf")):
            issues.append(RowIssue(row=row_num, column=col_name, description="Invalid float or NaN/Inf", severity="ERROR"))
            return None
        return Decimal(str(value))

    val_str = str(value).strip()
    if not val_str:
        return None

    if val_str.startswith("#") or val_str in ("#REF!", "#VALUE!", "#DIV/0!", "#N/A"):
        issues.append(RowIssue(row=row_num, column=col_name, description=f"Excel calculation error: {val_str}", severity="ERROR"))
        return None

    if val_str in ("-", "--", "—", "NIL", "nil", "Nil"):
        return Decimal("0.0000")

    clean_val = val_str.replace(",", "").replace(" ", "")
    try:
        dec = Decimal(clean_val)
        if dec < Decimal("0"):
            issues.append(RowIssue(row=row_num, column=col_name, description=f"Negative value ({dec}) not allowed in {col_name}.", severity="ERROR"))
            return None
        return dec
    except InvalidOperation:
        issues.append(RowIssue(row=row_num, column=col_name, description=f"Non-numeric value '{value}' in {col_name}.", severity="ERROR"))
        return None


def parse_raw_int(value: Any, row_num: int, col_name: str, issues: list[RowIssue]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        if value < 0:
            issues.append(RowIssue(row=row_num, column=col_name, description=f"Negative lead time ({value}) not allowed.", severity="ERROR"))
            return None
        return value
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            issues.append(RowIssue(row=row_num, column=col_name, description=f"Lead time must be a non-negative whole number of days, got {value}.", severity="ERROR"))
            return None
        return int(value)

    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("-", "–", "—"):
        return 0
    try:
        val_f = float(val_str)
        if val_f < 0 or not val_f.is_integer():
            issues.append(RowIssue(row=row_num, column=col_name, description=f"Lead time must be a non-negative whole number of days, got '{value}'.", severity="ERROR"))
            return None
        return int(val_f)
    except ValueError:
        issues.append(RowIssue(row=row_num, column=col_name, description=f"Invalid lead time days '{value}'.", severity="ERROR"))
        return None


SHORT_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def detect_month_in_text(text: str) -> Optional[tuple[int, Optional[int]]]:
    if not text:
        return None
    for idx, name in enumerate(MONTH_NAMES, start=1):
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            year_match = re.search(r"\b(20\d\d)\b", text)
            if not year_match:
                year_match = re.search(r"['’](\d{2})\b", text)
                if year_match:
                    return (idx, 2000 + int(year_match.group(1)))
            year = int(year_match.group(1)) if year_match else None
            return (idx, year)

    for idx, short_name in enumerate(SHORT_MONTHS, start=1):
        if re.search(r"\b" + re.escape(short_name) + r"(?:['’\s\d_-]|$)", text, re.IGNORECASE):
            year_match = re.search(r"\b(20\d\d)\b", text)
            if not year_match:
                year_match = re.search(r"['’](\d{2})\b", text)
                if year_match:
                    return (idx, 2000 + int(year_match.group(1)))
            year = int(year_match.group(1)) if year_match else None
            return (idx, year)

    return None


def get_previous_month(month: int, year: int) -> tuple[int, int]:
    if month == 1:
        return (12, year - 1)
    return (month - 1, year)


def parse_and_preview_stock_parameters(
    session: Session,
    file_bytes: bytes = b"",
    filename: str = "",
    selected_month: int = 1,
    selected_year: int = 2026,
    content: Optional[bytes] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> StockParameterPreviewResponse:
    """Validate stock parameters workbook and compare against previous month."""
    if content is not None:
        file_bytes = content
    if month is not None:
        selected_month = month
    if year is not None:
        selected_year = year
    effective_date = date(selected_year, selected_month, 1)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Failed to parse Excel workbook: {str(e)}", 400)

    sheet = wb.active
    if not sheet:
        raise ApplicationError("INVALID_EXCEL_FILE", "The workbook contains no active sheets.", 400)

    header_row_idx = -1
    col_mapping: dict[str, int] = {}
    title_text: Optional[str] = None

    expected_normalized = {
        "item id": "item_id",
        "category": "category",
        "type of material": "type_of_material",
        "material type": "type_of_material",
        "description": "description",
        "item description": "description",
        "min stock level": "min_stock_level",
        "minimum stock level": "min_stock_level",
        "msl": "min_stock_level",
        "max stock level": "max_stock_level",
        "maximum stock level": "max_stock_level",
        "minimum order qty": "min_order_qty",
        "min order qty": "min_order_qty",
        "minimum order quantity": "min_order_qty",
        "minimum order quanity": "min_order_qty",
        "min order quantity": "min_order_qty",
        "min order quanity": "min_order_qty",
        "moq": "min_order_qty",
        "lead time to supply in days": "lead_time_days",
        "lead time in days": "lead_time_days",
        "lead time to supply": "lead_time_days",
        "lead time": "lead_time_days",
    }

    errors: list[RowIssue] = []
    warnings: list[RowIssue] = []

    for r in range(1, min(25, sheet.max_row + 1)):
        row_vals = [sheet.cell(row=r, column=c).value for c in range(1, sheet.max_column + 1)]
        row_normalized = [normalize_header(v) for v in row_vals]

        first_non_empty = next((str(v) for v in row_vals if v is not None and str(v).strip()), "")
        if first_non_empty and ("consumables requirement" in first_non_empty.lower() or "stock management" in first_non_empty.lower()):
            title_text = first_non_empty

        matches = {col_idx + 1: expected_normalized[val] for col_idx, val in enumerate(row_normalized) if val in expected_normalized}
        if "item_id" in matches.values() and ("min_stock_level" in matches.values() or "max_stock_level" in matches.values()):
            header_row_idx = r
            for c_idx, canon in matches.items():
                if canon not in col_mapping:
                    col_mapping[canon] = c_idx
            break

    if header_row_idx == -1:
        errors.append(RowIssue(
            row=1,
            column="Header",
            description="Could not locate valid header row with required columns ('Item Id', 'Min stock level', etc.).",
            severity="ERROR",
        ))
        return StockParameterPreviewResponse(
            month=selected_month,
            year=selected_year,
            effective_date=effective_date.isoformat(),
            detected_title=title_text,
            source_filename=filename,
            file_token="",
            errors=errors,
            warnings=warnings,
            comparison=ComparisonSummary(),
            can_confirm=False,
        )

    # Check required columns
    if "item_id" not in col_mapping:
        errors.append(RowIssue(row=header_row_idx, column="Item Id", description="Required column 'Item Id' is missing.", severity="ERROR"))
    if "min_stock_level" not in col_mapping:
        errors.append(RowIssue(row=header_row_idx, column="Min stock level", description="Required column 'Min stock level' is missing.", severity="ERROR"))
    if "max_stock_level" not in col_mapping:
        errors.append(RowIssue(row=header_row_idx, column="Max stock level", description="Required column 'Max stock level' is missing.", severity="ERROR"))

    # Title Date Mismatch Check
    if title_text:
        detected_month_year = detect_month_in_text(title_text)
        if detected_month_year:
            det_month, det_year = detected_month_year
            if det_month != selected_month or (det_year and det_year != selected_year):
                det_label = f"{MONTH_NAMES[det_month - 1]} {det_year or ''}".strip()
                sel_label = f"{MONTH_NAMES[selected_month - 1]} {selected_year}"
                errors.append(RowIssue(
                    row=1,
                    column="Title",
                    description=f"File title specifies '{det_label}', but selected period is '{sel_label}'. Upload blocked due to month mismatch.",
                    severity="ERROR",
                ))

    # Pre-fetch Consumables master
    consumables = session.execute(
        select(Consumable.id, Consumable.code, Consumable.name, Consumable.category, Consumable.type_of_material)
    ).all()
    consumable_by_code = {c.code.strip().upper(): c for c in consumables}

    # Fetch previous month parameters for comparison
    prev_month, prev_year = get_previous_month(selected_month, selected_year)
    prev_batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == prev_month,
            StockParameterBatch.year == prev_year,
            StockParameterBatch.status == "active",
        )
    )
    prev_params_by_item: dict[str, StockParameter] = {}
    if prev_batch:
        prev_lines = session.scalars(
            select(StockParameter).where(StockParameter.batch_id == prev_batch.id)
        ).all()
        prev_params_by_item = {p.item_id.strip().upper(): p for p in prev_lines}

    seen_item_ids: set[str] = set()
    unknown_items: set[str] = set()
    parsed_lines: list[dict[str, Any]] = []

    for r in range(header_row_idx + 1, sheet.max_row + 1):
        item_id_raw = sheet.cell(row=r, column=col_mapping.get("item_id", 1)).value
        if item_id_raw is None or not str(item_id_raw).strip():
            row_has_data = any(
                sheet.cell(row=r, column=c).value is not None
                and str(sheet.cell(row=r, column=c).value).strip() != ""
                for c in range(1, sheet.max_column + 1)
            )
            if row_has_data:
                errors.append(RowIssue(row=r, column="Item Id", description="Row has data but Item Id is empty.", severity="ERROR"))
            continue

        item_id_str = str(item_id_raw).strip()
        item_id_upper = item_id_str.upper()

        if "TOTAL" in item_id_upper or "GRAND TOTAL" in item_id_upper:
            continue

        if item_id_upper in seen_item_ids:
            errors.append(RowIssue(row=r, column="Item Id", description=f"Duplicate Item Id '{item_id_str}' in upload file.", severity="ERROR"))
        seen_item_ids.add(item_id_upper)

        master_c = consumable_by_code.get(item_id_upper)
        if not master_c:
            unknown_items.add(item_id_str)
            errors.append(RowIssue(
                row=r,
                column="Item Id",
                description=f"Item Id '{item_id_str}' was not found in Consumable Master.",
                severity="ERROR",
            ))

        cat_val = sheet.cell(row=r, column=col_mapping["category"]).value if "category" in col_mapping else None
        type_val = sheet.cell(row=r, column=col_mapping["type_of_material"]).value if "type_of_material" in col_mapping else None
        desc_val = sheet.cell(row=r, column=col_mapping["description"]).value if "description" in col_mapping else None

        min_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["min_stock_level"]).value if "min_stock_level" in col_mapping else None, r, "Min stock level", errors)
        max_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["max_stock_level"]).value if "max_stock_level" in col_mapping else None, r, "Max stock level", errors)
        moq_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["min_order_qty"]).value if "min_order_qty" in col_mapping else None, r, "Minimum order qty.", errors)
        lt_val = parse_raw_int(sheet.cell(row=r, column=col_mapping["lead_time_days"]).value if "lead_time_days" in col_mapping else None, r, "Lead time to supply in days", errors)

        # Min > Max check (blocking error)
        if min_val is not None and max_val is not None:
            if min_val > max_val:
                errors.append(RowIssue(
                    row=r,
                    column="Min stock level",
                    description=f"Min stock level ({min_val}) cannot be greater than Max stock level ({max_val}).",
                    severity="ERROR",
                ))

        # Empty limit warnings
        if min_val is None:
            warnings.append(RowIssue(row=r, column="Min stock level", description="Min stock level is empty (stored as null).", severity="WARNING"))
        if max_val is None:
            warnings.append(RowIssue(row=r, column="Max stock level", description="Max stock level is empty (stored as null).", severity="WARNING"))
        if moq_val is None:
            warnings.append(RowIssue(row=r, column="Minimum order qty.", description="Minimum order qty. is empty (stored as null).", severity="WARNING"))
        if lt_val is None:
            warnings.append(RowIssue(row=r, column="Lead time to supply in days", description="Lead time is empty (stored as null).", severity="WARNING"))

        # Master discrepancy warnings
        if master_c:
            if cat_val and master_c.category and str(cat_val).strip().upper() != master_c.category.strip().upper():
                warnings.append(RowIssue(row=r, column="Category", description=f"Category '{cat_val}' differs from Master '{master_c.category}'.", severity="WARNING"))
            if type_val and master_c.type_of_material and str(type_val).strip().upper() != master_c.type_of_material.strip().upper():
                warnings.append(RowIssue(row=r, column="Type of material", description=f"Type of material '{type_val}' differs from Master '{master_c.type_of_material}'.", severity="WARNING"))

        # Previous month comparison warnings (e.g. unusually larger max or moq)
        if item_id_upper in prev_params_by_item:
            prev_p = prev_params_by_item[item_id_upper]
            if max_val is not None and prev_p.max_stock_level is not None and prev_p.max_stock_level > Decimal("0"):
                ratio = max_val / prev_p.max_stock_level
                if ratio >= Decimal("2.0"):  # doubled
                    warnings.append(RowIssue(
                        row=r,
                        column="Max stock level",
                        description=f"Max stock level ({max_val}) is over 100% higher than last month ({prev_p.max_stock_level}).",
                        severity="WARNING",
                    ))
            if moq_val is not None and prev_p.min_order_qty is not None and prev_p.min_order_qty > Decimal("0"):
                ratio_moq = moq_val / prev_p.min_order_qty
                if ratio_moq >= Decimal("2.0"):
                    warnings.append(RowIssue(
                        row=r,
                        column="Minimum order qty.",
                        description=f"MOQ ({moq_val}) is over 100% higher than last month ({prev_p.min_order_qty}).",
                        severity="WARNING",
                    ))

        parsed_lines.append({
            "source_row": r,
            "item_id": item_id_str,
            "consumable_id": str(master_c.id) if master_c else None,
            "category": str(cat_val).strip() if cat_val else (master_c.category if master_c else None),
            "type_of_material": str(type_val).strip() if type_val else (master_c.type_of_material if master_c else None),
            "description": str(desc_val).strip() if desc_val else (master_c.name if master_c else None),
            "min_stock_level": min_val,
            "max_stock_level": max_val,
            "min_order_qty": moq_val,
            "lead_time_days": lt_val,
        })

    # Build comparison summary against previous month
    current_item_set = {p["item_id"].strip().upper() for p in parsed_lines}
    prev_item_set = set(prev_params_by_item.keys())

    new_items_count = len(current_item_set - prev_item_set) if prev_batch else 0
    removed_items_count = len(prev_item_set - current_item_set) if prev_batch else 0
    changed_items_count = 0
    changes_sample: list[dict[str, Any]] = []

    if prev_batch:
        for p in parsed_lines:
            k = p["item_id"].strip().upper()
            if k in prev_params_by_item:
                old = prev_params_by_item[k]
                has_diff = (
                    p["min_stock_level"] != old.min_stock_level
                    or p["max_stock_level"] != old.max_stock_level
                    or p["min_order_qty"] != old.min_order_qty
                    or p["lead_time_days"] != old.lead_time_days
                )
                if has_diff:
                    changed_items_count += 1
                    if len(changes_sample) < 10:
                        changes_sample.append({
                            "item_id": p["item_id"],
                            "min_old": str(old.min_stock_level) if old.min_stock_level is not None else None,
                            "min_new": str(p["min_stock_level"]) if p["min_stock_level"] is not None else None,
                            "max_old": str(old.max_stock_level) if old.max_stock_level is not None else None,
                            "max_new": str(p["max_stock_level"]) if p["max_stock_level"] is not None else None,
                        })

    comp_summary = ComparisonSummary(
        has_previous_month=prev_batch is not None,
        previous_month_label=f"{MONTH_NAMES[prev_month - 1]} {prev_year}" if prev_batch else None,
        new_items_count=new_items_count,
        removed_items_count=removed_items_count,
        changed_items_count=changed_items_count,
        changes_sample=changes_sample,
    )

    # Check for existing active batch
    existing = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == selected_month,
            StockParameterBatch.year == selected_year,
            StockParameterBatch.status == "active",
        )
    )

    can_confirm = len(errors) == 0 and len(parsed_lines) > 0

    token = str(uuid.uuid4())
    if can_confirm:
        _PARAM_PREVIEW_STORE[token] = {
            "month": selected_month,
            "year": selected_year,
            "date": effective_date,
            "filename": filename,
            "file_hash": file_hash,
            "lines": parsed_lines,
        }

    preview_lines = [
        StockParameterRecord(
            id=f"param-prev-{p['source_row']}",
            item_id=p["item_id"],
            consumable_id=p["consumable_id"],
            category=p["category"],
            type_of_material=p["type_of_material"],
            description=p["description"],
            min_stock_level=p["min_stock_level"],
            max_stock_level=p["max_stock_level"],
            min_order_qty=p["min_order_qty"],
            lead_time_days=p["lead_time_days"],
            edited_after_import=False,
            source_row=p["source_row"],
        )
        for p in parsed_lines[:50]
    ]

    return StockParameterPreviewResponse(
        month=selected_month,
        year=selected_year,
        effective_date=effective_date.isoformat(),
        detected_title=title_text,
        source_filename=filename,
        file_token=token,
        is_existing_batch=existing is not None,
        existing_batch_filename=existing.source_filename if existing else None,
        errors=errors,
        warnings=warnings,
        unknown_items=sorted(list(unknown_items)),
        comparison=comp_summary,
        total_rows=len(parsed_lines),
        lines_preview=preview_lines,
        can_confirm=can_confirm,
    )


def confirm_stock_parameters_import(
    session: Session,
    request: StockParameterConfirmRequest,
    current_user: CurrentUser,
) -> StockManagementResponse:
    """Commit stock parameters in one transaction, marking existing batches superseded."""
    token_data = _PARAM_PREVIEW_STORE.get(request.file_token)
    if not token_data:
        raise ApplicationError("EXPIRED_TOKEN", "Import session expired or invalid. Please re-upload the file.", 400)

    if token_data["month"] != request.month or token_data["year"] != request.year:
        raise ApplicationError("PERIOD_MISMATCH", "Token period does not match confirmed month/year.", 400)

    existing_batches = session.scalars(
        select(StockParameterBatch).where(
            StockParameterBatch.month == request.month,
            StockParameterBatch.year == request.year,
            StockParameterBatch.status == "active",
        )
    ).all()

    if existing_batches and not request.replace_confirmed:
        raise ApplicationError(
            "REPLACE_CONFIRMATION_REQUIRED",
            f"Active stock management parameters already exist for {MONTH_NAMES[request.month - 1]} {request.year}. Confirmation required to replace.",
            409,
        )

    now_utc = datetime.now(timezone.utc)
    for old_batch in existing_batches:
        old_batch.status = "superseded"
        old_batch.updated_at = now_utc
        old_batch.updated_by = current_user.id
        log_audit_event(
            session=session,
            entity_type="StockParameterBatch",
            entity_id=old_batch.id,
            action="UPDATE",
            actor_id=current_user.id,
            before_state={"status": "active"},
            after_state={"status": "superseded"},
            reason=f"Superseded by replacement upload '{token_data['filename']}' for {request.month}/{request.year}.",
        )

    new_batch = StockParameterBatch(
        month=request.month,
        year=request.year,
        effective_date=token_data["date"],
        source_filename=token_data["filename"],
        file_hash=token_data["file_hash"],
        status="active",
        row_count=len(token_data["lines"]),
        uploaded_by=current_user.id,
        uploaded_at=now_utc,
        created_by=current_user.id,
        created_at=now_utc,
        updated_by=current_user.id,
        updated_at=now_utc,
    )
    session.add(new_batch)
    session.flush()

    param_objects: list[StockParameter] = []
    for line in token_data["lines"]:
        param_obj = StockParameter(
            batch_id=new_batch.id,
            item_id=line["item_id"],
            consumable_id=uuid.UUID(line["consumable_id"]) if line["consumable_id"] else None,
            category=line["category"],
            type_of_material=line["type_of_material"],
            description=line["description"],
            min_stock_level=line["min_stock_level"],
            max_stock_level=line["max_stock_level"],
            min_order_qty=line["min_order_qty"],
            lead_time_days=line["lead_time_days"],
            edited_after_import=False,
            source_row=line["source_row"],
            created_at=now_utc,
            updated_at=now_utc,
            updated_by=current_user.id,
        )
        param_objects.append(param_obj)

    session.add_all(param_objects)

    log_audit_event(
        session=session,
        entity_type="StockParameterBatch",
        entity_id=new_batch.id,
        action="CREATE",
        actor_id=current_user.id,
        before_state={},
        after_state={
            "period": f"{request.month}/{request.year}",
            "filename": token_data["filename"],
            "row_count": len(param_objects),
        },
        reason=f"Uploaded stock control parameters for {MONTH_NAMES[request.month - 1]} {request.year}.",
    )

    session.commit()
    _PARAM_PREVIEW_STORE.pop(request.file_token, None)

    return get_stock_management(session, request.month, request.year)


def get_stock_management(
    session: Session,
    month: int,
    year: int,
    search: Optional[str] = None,
    category_filter: Optional[str] = None,
) -> StockManagementResponse:
    """Retrieve active stock management parameters for the specified month and year."""
    effective_date = date(year, month, 1)

    batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == month,
            StockParameterBatch.year == year,
            StockParameterBatch.status == "active",
        )
    )

    if not batch:
        meta = StockManagementMetadata(
            has_parameters=False,
            month=month,
            year=year,
            effective_date=effective_date.isoformat(),
            row_count=0,
        )
        summary = StockManagementSummary()
        return StockManagementResponse(metadata=meta, summary=summary, records=[])

    creator = session.get(User, batch.created_by) if batch.created_by else None
    updater = session.get(User, batch.updated_by) if batch.updated_by else None

    stmt = select(StockParameter).where(StockParameter.batch_id == batch.id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            (StockParameter.item_id.ilike(term))
            | (StockParameter.description.ilike(term))
            | (StockParameter.category.ilike(term))
        )
    if category_filter and category_filter.strip():
        stmt = stmt.where(StockParameter.category == category_filter.strip())

    stmt = stmt.order_by(StockParameter.source_row)
    params = session.scalars(stmt).all()

    missing_limits = session.scalar(
        select(func.count(StockParameter.id)).where(
            StockParameter.batch_id == batch.id,
            (StockParameter.min_stock_level.is_(None))
            | (StockParameter.max_stock_level.is_(None))
            | (StockParameter.min_order_qty.is_(None))
            | (StockParameter.lead_time_days.is_(None)),
        )
    ) or 0

    min_gt_max = session.scalar(
        select(func.count(StockParameter.id)).where(
            StockParameter.batch_id == batch.id,
            StockParameter.min_stock_level > StockParameter.max_stock_level,
        )
    ) or 0

    records = [
        StockParameterRecord(
            id=str(p.id),
            item_id=p.item_id,
            consumable_id=str(p.consumable_id) if p.consumable_id else None,
            category=p.category,
            type_of_material=p.type_of_material,
            description=p.description,
            min_stock_level=p.min_stock_level,
            max_stock_level=p.max_stock_level,
            min_order_qty=p.min_order_qty,
            lead_time_days=p.lead_time_days,
            edited_after_import=p.edited_after_import,
            source_row=p.source_row,
        )
        for p in params
    ]

    meta = StockManagementMetadata(
        has_parameters=True,
        batch_id=str(batch.id),
        month=month,
        year=year,
        effective_date=batch.effective_date.isoformat(),
        source_filename=batch.source_filename,
        status=batch.status,
        created_at=batch.created_at,
        created_by_name=creator.full_name or creator.username if creator else None,
        updated_at=batch.updated_at,
        updated_by_name=updater.full_name or updater.username if updater else None,
        row_count=batch.row_count,
    )

    summary = StockManagementSummary(
        item_count=len(params),
        missing_limits_count=missing_limits,
        min_exceeds_max_count=min_gt_max,
    )

    return StockManagementResponse(metadata=meta, summary=summary, records=records)


def batch_update_stock_parameters(
    session: Session,
    request: StockParameterBatchUpdateRequest,
    current_user: CurrentUser,
) -> StockManagementResponse:
    """Batch-update stock control parameters in one atomic transaction with audit trail."""
    batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == request.month,
            StockParameterBatch.year == request.year,
            StockParameterBatch.status == "active",
        )
    )
    if not batch:
        raise ApplicationError("NOT_FOUND", f"No active stock management batch found for {MONTH_NAMES[request.month - 1]} {request.year}.", 404)

    now_utc = datetime.now(timezone.utc)
    for update_item in request.updates:
        param = session.get(StockParameter, uuid.UUID(update_item.id))
        if not param or param.batch_id != batch.id:
            continue

        # Validation: Min <= Max if both set
        min_val = update_item.min_stock_level if update_item.min_stock_level is not None else param.min_stock_level
        max_val = update_item.max_stock_level if update_item.max_stock_level is not None else param.max_stock_level
        if min_val is not None and max_val is not None and min_val > max_val:
            raise ApplicationError(
                "VALIDATION_ERROR",
                f"Min stock level ({min_val}) cannot be greater than Max stock level ({max_val}) for {param.item_id}.",
                400,
            )

        if update_item.lead_time_days is not None and update_item.lead_time_days < 0:
            raise ApplicationError("VALIDATION_ERROR", f"Lead time cannot be negative for {param.item_id}.", 400)

        before = {
            "min_stock_level": str(param.min_stock_level) if param.min_stock_level is not None else None,
            "max_stock_level": str(param.max_stock_level) if param.max_stock_level is not None else None,
            "min_order_qty": str(param.min_order_qty) if param.min_order_qty is not None else None,
            "lead_time_days": param.lead_time_days,
        }

        # Apply edits
        param.min_stock_level = update_item.min_stock_level
        param.max_stock_level = update_item.max_stock_level
        param.min_order_qty = update_item.min_order_qty
        param.lead_time_days = update_item.lead_time_days
        param.edited_after_import = True
        param.updated_at = now_utc
        param.updated_by = current_user.id

        after = {
            "min_stock_level": str(param.min_stock_level) if param.min_stock_level is not None else None,
            "max_stock_level": str(param.max_stock_level) if param.max_stock_level is not None else None,
            "min_order_qty": str(param.min_order_qty) if param.min_order_qty is not None else None,
            "lead_time_days": param.lead_time_days,
        }

        log_audit_event(
            session=session,
            entity_type="StockParameter",
            entity_id=param.id,
            action="UPDATE",
            actor_id=current_user.id,
            before_state=before,
            after_state=after,
            reason=f"Edited stock control limits for {param.item_id} in {request.month}/{request.year}.",
        )

    batch.updated_at = now_utc
    batch.updated_by = current_user.id

    session.commit()
    return get_stock_management(session, request.month, request.year)


def list_stock_parameter_history(
    session: Session,
    month: int,
    year: int,
) -> list[StockParameterHistoryItem]:
    """List historical upload batches for stock management."""
    batches = session.scalars(
        select(StockParameterBatch)
        .where(
            StockParameterBatch.month == month,
            StockParameterBatch.year == year,
        )
        .order_by(StockParameterBatch.created_at.desc())
    ).all()

    items: list[StockParameterHistoryItem] = []
    for b in batches:
        uploader = session.get(User, b.uploaded_by) if b.uploaded_by else None
        items.append(
            StockParameterHistoryItem(
                batch_id=str(b.id),
                month=b.month,
                year=b.year,
                effective_date=b.effective_date.isoformat(),
                source_filename=b.source_filename,
                status=b.status,
                row_count=b.row_count,
                uploaded_at=b.uploaded_at,
                uploaded_by_name=uploader.full_name or uploader.username if uploader else None,
            )
        )
    return items


def export_stock_management_excel(
    session: Session,
    month: int,
    year: int,
) -> tuple[bytes, str]:
    """Export active stock management parameters to an Excel workbook matching KNL columns."""
    res = get_stock_management(session, month, year)
    if not res.metadata.has_parameters:
        raise ApplicationError("NOT_FOUND", f"No stock parameters found for {MONTH_NAMES[month - 1]} {year}.", 404)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Stock Control {month}-{year}"

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    num_alignment = Alignment(horizontal="right", vertical="center")
    center_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    ws.append([f"Consumables Requirement for the month of {MONTH_NAMES[month - 1]} {year}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(EXPECTED_PARAMETER_COLUMNS))
    ws.cell(row=1, column=1).font = Font(name="Calibri", size=13, bold=True, color="1F4E79")

    ws.append(EXPECTED_PARAMETER_COLUMNS)
    for col_idx in range(1, len(EXPECTED_PARAMETER_COLUMNS) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in res.records:
        ws.append([
            r.item_id,
            r.category or "",
            r.type_of_material or "",
            r.description or "",
            float(r.min_stock_level) if r.min_stock_level is not None else "",
            float(r.max_stock_level) if r.max_stock_level is not None else "",
            float(r.min_order_qty) if r.min_order_qty is not None else "",
            r.lead_time_days if r.lead_time_days is not None else "",
        ])
        curr_row = ws.max_row
        for col_idx in range(1, len(EXPECTED_PARAMETER_COLUMNS) + 1):
            cell = ws.cell(row=curr_row, column=col_idx)
            cell.border = thin_border
            if col_idx in (5, 6, 7):
                cell.alignment = num_alignment
                cell.number_format = "#,##0.0000"
            elif col_idx in (1, 8):
                cell.alignment = center_alignment

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    buf = io.BytesIO()
    wb.save(buf)
    filename = f"KNL_Stock_Parameters_{year}_{month:02d}.xlsx"
    return buf.getvalue(), filename

