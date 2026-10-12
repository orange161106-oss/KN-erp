import calendar
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
from app.models.inventory_masters import Consumable, Unit
from app.models.stock_statements import StockStatementBatch, StockStatementLine
from app.schemas.auth import CurrentUser
from app.schemas.stock_statements import (
    ComparisonSummary,
    RowIssue,
    StockStatementConfirmRequest,
    StockStatementHistoryItem,
    StockStatementLineResponse,
    StockStatementMetadata,
    StockStatementPreviewResponse,
    StockStatementResponse,
    StockStatementSummary,
)
from app.services.audit import log_audit_event


# In-memory storage for validated preview payloads (token -> payload)
_PREVIEW_STORE: dict[str, dict[str, Any]] = {}

# Exact KNL column specification for Stock Statement
EXPECTED_STATEMENT_COLUMNS = [
    "Item Id",
    "Item Description",
    "Cust. Part No.",
    "Unit",
    "Opening Qty.",
    "Opening Value",
    "Receipt Qty.",
    "Receipt Value",
    "Issue Qty.",
    "Issue Value",
    "Closing Qty.",
    "Closing Value",
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def normalize_header(text: Any) -> str:
    """Normalize header text: strip, lowercase, collapse spaces, remove periods."""
    if not text:
        return ""
    clean = re.sub(r"\s+", " ", str(text)).strip().lower()
    return clean.replace(".", "")


def parse_raw_decimal(value: Any, row_num: int, col_name: str, issues: list[RowIssue]) -> Optional[Decimal]:
    """Parse raw cell value into Decimal handling Indian grouping, brackets, negatives, and '-'."""
    if value is None:
        return None

    # Already numeric
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and (value != value or value == float("inf") or value == float("-inf")):
            issues.append(RowIssue(row=row_num, column=col_name, description="Invalid float or NaN/Inf", severity="ERROR"))
            return None
        return Decimal(str(value))

    val_str = str(value).strip()
    if not val_str:
        return None

    # Check for excel errors
    if val_str.startswith("#") or val_str in ("#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?", "#NUM!"):
        issues.append(RowIssue(row=row_num, column=col_name, description=f"Excel calculation error: {val_str}", severity="ERROR"))
        return None

    # Zero indicators
    if val_str in ("-", "--", "—", "NIL", "nil", "Nil"):
        return Decimal("0.0000")

    # Parenthesized negative e.g. (1,234.56)
    is_negative = False
    if val_str.startswith("(") and val_str.endswith(")"):
        is_negative = True
        val_str = val_str[1:-1].strip()
    elif val_str.startswith("-"):
        is_negative = True
        val_str = val_str[1:].strip()

    # Remove commas and spaces
    clean_val = val_str.replace(",", "").replace(" ", "").replace("₹", "").replace("Rs", "")
    try:
        dec = Decimal(clean_val)
        return -dec if is_negative else dec
    except InvalidOperation:
        issues.append(RowIssue(row=row_num, column=col_name, description=f"Non-numeric value '{value}' in numeric column", severity="ERROR"))
        return None


SHORT_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def detect_month_in_text(text: str) -> Optional[tuple[int, Optional[int]]]:
    """Check text for month names (full or abbreviated) and optional year."""
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


def get_statement_end_date(year: int, month: int) -> date:
    """Return the last calendar day of the given period."""
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, last_day)


def parse_and_preview_stock_statement(
    session: Session,
    file_bytes: bytes,
    filename: str,
    selected_month: int,
    selected_year: int,
) -> StockStatementPreviewResponse:
    """Inspect and validate an uploaded stock statement Excel file."""
    statement_end = get_statement_end_date(selected_year, selected_month)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Failed to parse Excel workbook: {str(e)}", 400)

    sheet = wb.active
    if not sheet:
        raise ApplicationError("INVALID_EXCEL_FILE", "The workbook contains no active sheets.", 400)

    # 1. Detect header row & title rows
    header_row_idx = -1
    col_mapping: dict[str, int] = {}  # normalized key -> col 1-indexed
    title_text: Optional[str] = None

    expected_normalized = {
        "item id": "item_id",
        "item description": "item_description",
        "cust part no": "cust_part_no",
        "customer part no": "cust_part_no",
        "unit": "unit",
        "uom": "unit",
        "opening qty": "opening_qty",
        "opening quantity": "opening_qty",
        "opening value": "opening_value",
        "receipt qty": "receipt_qty",
        "receipt quantity": "receipt_qty",
        "receipt value": "receipt_value",
        "issue qty": "issue_qty",
        "issue quantity": "issue_qty",
        "issue value": "issue_value",
        "closing qty": "closing_qty",
        "closing quantity": "closing_qty",
        "closing value": "closing_value",
    }

    errors: list[RowIssue] = []
    warnings: list[RowIssue] = []

    for r in range(1, min(25, sheet.max_row + 1)):
        row_vals = [sheet.cell(row=r, column=c).value for c in range(1, sheet.max_column + 1)]
        row_normalized = [normalize_header(v) for v in row_vals]

        # Check if title row
        first_non_empty = next((str(v) for v in row_vals if v is not None and str(v).strip()), "")
        if first_non_empty and ("stock statement" in first_non_empty.lower() or "statement" in first_non_empty.lower()):
            title_text = first_non_empty

        # Check if matches header
        matches = {col_idx + 1: expected_normalized[val] for col_idx, val in enumerate(row_normalized) if val in expected_normalized}
        if "item_id" in matches.values() and ("closing_qty" in matches.values() or "opening_qty" in matches.values()):
            header_row_idx = r
            # Map canonical keys to column indexes
            for c_idx, canon in matches.items():
                if canon not in col_mapping:
                    col_mapping[canon] = c_idx
            break

    if header_row_idx == -1:
        errors.append(RowIssue(
            row=1,
            column="Header",
            description="Could not locate valid header row with required columns ('Item Id', 'Closing Qty.', etc.).",
            severity="ERROR",
        ))
        return StockStatementPreviewResponse(
            statement_month=selected_month,
            statement_year=selected_year,
            statement_date=statement_end.isoformat(),
            detected_title=title_text,
            source_filename=filename,
            file_token="",
            errors=errors,
            warnings=warnings,
            can_confirm=False,
        )

    # Check for missing required columns
    required_keys = ["item_id", "opening_qty", "receipt_qty", "issue_qty", "closing_qty"]
    for rk in required_keys:
        if rk not in col_mapping:
            errors.append(RowIssue(row=header_row_idx, column=rk, description=f"Required column '{rk}' is missing from header row.", severity="ERROR"))

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

    # Pre-fetch Consumables master for verification
    consumables = session.execute(
        select(Consumable.id, Consumable.code, Consumable.name, Consumable.unit_id)
    ).all()
    consumable_by_code = {c.code.strip().upper(): c for c in consumables}

    units = session.execute(select(Unit.id, Unit.code)).all()
    unit_code_by_id = {u.id: u.code for u in units}

    seen_item_ids: set[str] = set()
    unknown_items: set[str] = set()
    parsed_lines: list[dict[str, Any]] = []

    # Iterate rows
    for r in range(header_row_idx + 1, sheet.max_row + 1):
        item_id_raw = sheet.cell(row=r, column=col_mapping.get("item_id", 1)).value
        if item_id_raw is None or not str(item_id_raw).strip():
            # Check if entire row is empty
            row_has_data = any(sheet.cell(row=r, column=c).value is not None for c in range(1, sheet.max_column + 1))
            if row_has_data:
                # Missing Item ID on non-empty row
                errors.append(RowIssue(row=r, column="Item Id", description="Row has data but Item Id is empty.", severity="ERROR"))
            continue

        item_id_str = str(item_id_raw).strip()
        item_id_upper = item_id_str.upper()

        # Skip total / subtotal summary rows
        if "TOTAL" in item_id_upper or "GRAND TOTAL" in item_id_upper or "SUB TOTAL" in item_id_upper:
            continue

        # Duplicate Item ID check within file
        if item_id_upper in seen_item_ids:
            errors.append(RowIssue(row=r, column="Item Id", description=f"Duplicate Item Id '{item_id_str}' in upload file.", severity="ERROR"))
        seen_item_ids.add(item_id_upper)

        # Check in Consumable Master
        master_consumable = consumable_by_code.get(item_id_upper)
        if not master_consumable:
            unknown_items.add(item_id_str)
            errors.append(RowIssue(
                row=r,
                column="Item Id",
                description=f"Item Id '{item_id_str}' was not found in Consumable Master.",
                severity="ERROR",
            ))

        # Extract values
        desc_val = sheet.cell(row=r, column=col_mapping["item_description"]).value if "item_description" in col_mapping else None
        cust_part_val = sheet.cell(row=r, column=col_mapping["cust_part_no"]).value if "cust_part_no" in col_mapping else None
        unit_val = sheet.cell(row=r, column=col_mapping["unit"]).value if "unit" in col_mapping else None

        line_issues: list[str] = []

        open_qty = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["opening_qty"]).value if "opening_qty" in col_mapping else None, r, "Opening Qty.", errors)
        open_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["opening_value"]).value if "opening_value" in col_mapping else None, r, "Opening Value", errors)
        rcpt_qty = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["receipt_qty"]).value if "receipt_qty" in col_mapping else None, r, "Receipt Qty.", errors)
        rcpt_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["receipt_value"]).value if "receipt_value" in col_mapping else None, r, "Receipt Value", errors)
        iss_qty = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["issue_qty"]).value if "issue_qty" in col_mapping else None, r, "Issue Qty.", errors)
        iss_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["issue_value"]).value if "issue_value" in col_mapping else None, r, "Issue Value", errors)
        cls_qty = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["closing_qty"]).value if "closing_qty" in col_mapping else None, r, "Closing Qty.", errors)
        cls_val = parse_raw_decimal(sheet.cell(row=r, column=col_mapping["closing_value"]).value if "closing_value" in col_mapping else None, r, "Closing Value", errors)

        # Check for negative receipts or issues (blocking errors)
        if rcpt_qty is not None and rcpt_qty < Decimal("0"):
            errors.append(RowIssue(row=r, column="Receipt Qty.", description="Receipt Qty. cannot be negative.", severity="ERROR"))
        if rcpt_val is not None and rcpt_val < Decimal("0"):
            errors.append(RowIssue(row=r, column="Receipt Value", description="Receipt Value cannot be negative.", severity="ERROR"))
        if iss_qty is not None and iss_qty < Decimal("0"):
            errors.append(RowIssue(row=r, column="Issue Qty.", description="Issue Qty. cannot be negative.", severity="ERROR"))
        if iss_val is not None and iss_val < Decimal("0"):
            errors.append(RowIssue(row=r, column="Issue Value", description="Issue Value cannot be negative.", severity="ERROR"))

        # Arithmetic warnings
        diff_qty = None
        if open_qty is not None and rcpt_qty is not None and iss_qty is not None and cls_qty is not None:
            expected_cls_qty = open_qty + rcpt_qty - iss_qty
            diff_q = cls_qty - expected_cls_qty
            if abs(diff_q) > Decimal("0.0001"):
                diff_qty = diff_q
                w_msg = f"Closing Qty ({cls_qty}) != Opening ({open_qty}) + Receipt ({rcpt_qty}) - Issue ({iss_qty}). Diff: {diff_q:+f}"
                warnings.append(RowIssue(row=r, column="Closing Qty.", description=w_msg, severity="WARNING"))
                line_issues.append("QTY_MISMATCH")

        diff_val = None
        if open_val is not None and rcpt_val is not None and iss_val is not None and cls_val is not None:
            expected_cls_val = open_val + rcpt_val - iss_val
            diff_v = cls_val - expected_cls_val
            if abs(diff_v) > Decimal("1.0000"):  # 1.0 tolerance for paise/rounding
                diff_val = diff_v
                w_msg = f"Closing Value ({cls_val}) != Opening ({open_val}) + Receipt ({rcpt_val}) - Issue ({iss_val}). Diff: {diff_v:+f}"
                warnings.append(RowIssue(row=r, column="Closing Value", description=w_msg, severity="WARNING"))
                line_issues.append("VAL_MISMATCH")

        # Negative opening or closing quantity warnings
        if open_qty is not None and open_qty < Decimal("0"):
            warnings.append(RowIssue(row=r, column="Opening Qty.", description=f"Negative Opening Qty ({open_qty}).", severity="WARNING"))
            line_issues.append("NEGATIVE_OPENING")
        if cls_qty is not None and cls_qty < Decimal("0"):
            warnings.append(RowIssue(row=r, column="Closing Qty.", description=f"Negative Closing Qty ({cls_qty}).", severity="WARNING"))
            line_issues.append("NEGATIVE_CLOSING")

        # Unit mismatch warning
        if master_consumable and unit_val:
            master_unit_code = unit_code_by_id.get(master_consumable.unit_id)
            if master_unit_code and str(unit_val).strip().upper() != master_unit_code.upper():
                warnings.append(RowIssue(
                    row=r,
                    column="Unit",
                    description=f"Unit '{unit_val}' differs from Consumable Master unit '{master_unit_code}'.",
                    severity="WARNING",
                ))
                line_issues.append("UNIT_MISMATCH")

        # Description mismatch warning (info only)
        if master_consumable and desc_val and master_consumable.name:
            if str(desc_val).strip().upper() != master_consumable.name.strip().upper():
                line_issues.append("DESC_MISMATCH")

        # Empty cell warning where value expected
        for col_n, col_v in [
            ("Opening Qty.", open_qty), ("Opening Value", open_val),
            ("Receipt Qty.", rcpt_qty), ("Receipt Value", rcpt_val),
            ("Issue Qty.", iss_qty), ("Issue Value", iss_val),
            ("Closing Qty.", cls_qty), ("Closing Value", cls_val),
        ]:
            if col_v is None:
                warnings.append(RowIssue(row=r, column=col_n, description=f"Empty cell in {col_n} (treated as null).", severity="WARNING"))
                line_issues.append(f"EMPTY_{col_n.upper().replace(' ', '_')}")

        parsed_lines.append({
            "source_row": r,
            "item_id": item_id_str,
            "consumable_id": str(master_consumable.id) if master_consumable else None,
            "item_description": str(desc_val).strip() if desc_val else None,
            "cust_part_no": str(cust_part_val).strip() if cust_part_val else None,
            "unit": str(unit_val).strip() if unit_val else None,
            "opening_qty": open_qty,
            "opening_value": open_val,
            "receipt_qty": rcpt_qty,
            "receipt_value": rcpt_val,
            "issue_qty": iss_qty,
            "issue_value": iss_val,
            "closing_qty": cls_qty,
            "closing_value": cls_val,
            "diff_closing_qty": diff_qty,
            "diff_closing_value": diff_val,
            "warning_codes": line_issues,
        })

    # Check for existing active batch
    existing = session.scalar(
        select(StockStatementBatch).where(
            StockStatementBatch.statement_month == selected_month,
            StockStatementBatch.statement_year == selected_year,
            StockStatementBatch.status == "active",
        )
    )

    can_confirm = len(errors) == 0 and len(parsed_lines) > 0

    token = str(uuid.uuid4())
    if can_confirm:
        _PREVIEW_STORE[token] = {
            "month": selected_month,
            "year": selected_year,
            "date": statement_end,
            "filename": filename,
            "file_hash": file_hash,
            "lines": parsed_lines,
            "warnings_count": len(warnings),
        }

    preview_lines = [
        StockStatementLineResponse(
            id=f"preview-{p['source_row']}",
            item_id=p["item_id"],
            consumable_id=p["consumable_id"],
            item_description=p["item_description"],
            cust_part_no=p["cust_part_no"],
            unit=p["unit"],
            opening_qty=p["opening_qty"],
            opening_value=p["opening_value"],
            receipt_qty=p["receipt_qty"],
            receipt_value=p["receipt_value"],
            issue_qty=p["issue_qty"],
            issue_value=p["issue_value"],
            closing_qty=p["closing_qty"],
            closing_value=p["closing_value"],
            source_row=p["source_row"],
            warning_codes=p["warning_codes"],
            diff_closing_qty=p["diff_closing_qty"],
            diff_closing_value=p["diff_closing_value"],
        )
        for p in parsed_lines[:50]
    ]

    return StockStatementPreviewResponse(
        statement_month=selected_month,
        statement_year=selected_year,
        statement_date=statement_end.isoformat(),
        detected_title=title_text,
        source_filename=filename,
        file_token=token,
        is_existing_batch=existing is not None,
        existing_batch_filename=existing.source_filename if existing else None,
        existing_batch_date=existing.uploaded_at if existing else None,
        errors=errors,
        warnings=warnings,
        unknown_items=sorted(list(unknown_items)),
        total_rows=len(parsed_lines),
        warning_count=len(warnings),
        lines_preview=preview_lines,
        can_confirm=can_confirm,
    )


def confirm_stock_statement_import(
    session: Session,
    request: StockStatementConfirmRequest,
    current_user: CurrentUser,
) -> StockStatementResponse:
    """Commit the parsed stock statement in one atomic transaction, marking existing batches superseded."""
    token_data = _PREVIEW_STORE.get(request.file_token)
    if not token_data:
        raise ApplicationError("EXPIRED_TOKEN", "Import session expired or invalid. Please re-upload the file.", 400)

    if (
        token_data["month"] != request.statement_month
        or token_data["year"] != request.statement_year
    ):
        raise ApplicationError("PERIOD_MISMATCH", "Token period does not match confirmed month/year.", 400)

    # 1. Existing batch check
    existing_batches = session.scalars(
        select(StockStatementBatch).where(
            StockStatementBatch.statement_month == request.statement_month,
            StockStatementBatch.statement_year == request.statement_year,
            StockStatementBatch.status == "active",
        )
    ).all()

    if existing_batches and not request.replace_confirmed:
        raise ApplicationError(
            "REPLACE_CONFIRMATION_REQUIRED",
            f"An active stock statement already exists for {MONTH_NAMES[request.statement_month - 1]} {request.statement_year}. Confirmation required to replace.",
            409,
        )

    # Mark existing active batches as superseded
    now_utc = datetime.now(timezone.utc)
    for old_batch in existing_batches:
        old_batch.status = "superseded"
        old_batch.updated_at = now_utc
        old_batch.updated_by = current_user.id
        log_audit_event(
            session=session,
            entity_type="StockStatementBatch",
            entity_id=old_batch.id,
            action="UPDATE",
            actor_id=current_user.id,
            before_state={"status": "active"},
            after_state={"status": "superseded"},
            reason=f"Superseded by replacement upload '{token_data['filename']}' for period {request.statement_month}/{request.statement_year}.",
        )

    # 2. Insert new batch
    new_batch = StockStatementBatch(
        statement_month=request.statement_month,
        statement_year=request.statement_year,
        statement_date=token_data["date"],
        source_filename=token_data["filename"],
        file_hash=token_data["file_hash"],
        status="active",
        row_count=len(token_data["lines"]),
        warning_count=token_data["warnings_count"],
        uploaded_by=current_user.id,
        uploaded_at=now_utc,
        created_by=current_user.id,
        created_at=now_utc,
        updated_by=current_user.id,
        updated_at=now_utc,
    )
    session.add(new_batch)
    session.flush()

    # 3. Insert lines
    line_objects: list[StockStatementLine] = []
    for line in token_data["lines"]:
        line_obj = StockStatementLine(
            batch_id=new_batch.id,
            item_id=line["item_id"],
            consumable_id=uuid.UUID(line["consumable_id"]) if line["consumable_id"] else None,
            item_description=line["item_description"],
            cust_part_no=line["cust_part_no"],
            unit=line["unit"],
            opening_qty=line["opening_qty"],
            opening_value=line["opening_value"],
            receipt_qty=line["receipt_qty"],
            receipt_value=line["receipt_value"],
            issue_qty=line["issue_qty"],
            issue_value=line["issue_value"],
            closing_qty=line["closing_qty"],
            closing_value=line["closing_value"],
            source_row=line["source_row"],
            warning_codes=line["warning_codes"],
            created_at=now_utc,
            updated_at=now_utc,
        )
        line_objects.append(line_obj)

    session.add_all(line_objects)

    log_audit_event(
        session=session,
        entity_type="StockStatementBatch",
        entity_id=new_batch.id,
        action="CREATE",
        actor_id=current_user.id,
        before_state={},
        after_state={
            "period": f"{request.statement_month}/{request.statement_year}",
            "filename": token_data["filename"],
            "row_count": len(line_objects),
            "warning_count": token_data["warnings_count"],
        },
        reason=f"Uploaded monthly stock statement for {MONTH_NAMES[request.statement_month - 1]} {request.statement_year}.",
    )

    session.commit()

    # Cleanup preview store
    _PREVIEW_STORE.pop(request.file_token, None)

    return get_stock_statement(session, request.statement_month, request.statement_year)


def get_stock_statement(
    session: Session,
    month: int,
    year: int,
    search: Optional[str] = None,
    unit_filter: Optional[str] = None,
) -> StockStatementResponse:
    """Retrieve the active stock statement for the specified month and year."""
    statement_end = get_statement_end_date(year, month)

    batch = session.scalar(
        select(StockStatementBatch).where(
            StockStatementBatch.statement_month == month,
            StockStatementBatch.statement_year == year,
            StockStatementBatch.status == "active",
        )
    )

    if not batch:
        meta = StockStatementMetadata(
            has_statement=False,
            statement_month=month,
            statement_year=year,
            statement_date=statement_end.isoformat(),
            row_count=0,
            warning_count=0,
        )
        summary = StockStatementSummary()
        return StockStatementResponse(metadata=meta, summary=summary, records=[])

    creator = session.get(User, batch.created_by) if batch.created_by else None
    updater = session.get(User, batch.updated_by) if batch.updated_by else None

    # Query lines
    stmt = select(StockStatementLine).where(StockStatementLine.batch_id == batch.id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            (StockStatementLine.item_id.ilike(term))
            | (StockStatementLine.item_description.ilike(term))
            | (StockStatementLine.cust_part_no.ilike(term))
        )
    if unit_filter and unit_filter.strip():
        stmt = stmt.where(StockStatementLine.unit == unit_filter.strip())

    stmt = stmt.order_by(StockStatementLine.source_row)
    lines = session.scalars(stmt).all()

    # Calculate summary over all lines in batch
    totals = session.execute(
        select(
            func.count(StockStatementLine.id),
            func.coalesce(func.sum(StockStatementLine.opening_value), 0),
            func.coalesce(func.sum(StockStatementLine.receipt_value), 0),
            func.coalesce(func.sum(StockStatementLine.issue_value), 0),
            func.coalesce(func.sum(StockStatementLine.closing_value), 0),
        ).where(StockStatementLine.batch_id == batch.id)
    ).one()

    warning_rows_count = session.scalar(
        select(func.count(StockStatementLine.id)).where(
            StockStatementLine.batch_id == batch.id,
            func.jsonb_array_length(StockStatementLine.warning_codes) > 0,
        )
    ) or 0

    records: list[StockStatementLineResponse] = []
    for l in lines:
        diff_q = None
        if l.opening_qty is not None and l.receipt_qty is not None and l.issue_qty is not None and l.closing_qty is not None:
            diff_q = l.closing_qty - (l.opening_qty + l.receipt_qty - l.issue_qty)
        diff_v = None
        if l.opening_value is not None and l.receipt_value is not None and l.issue_value is not None and l.closing_value is not None:
            diff_v = l.closing_value - (l.opening_value + l.receipt_value - l.issue_value)

        records.append(
            StockStatementLineResponse(
                id=str(l.id),
                item_id=l.item_id,
                consumable_id=str(l.consumable_id) if l.consumable_id else None,
                item_description=l.item_description,
                cust_part_no=l.cust_part_no,
                unit=l.unit,
                opening_qty=l.opening_qty,
                opening_value=l.opening_value,
                receipt_qty=l.receipt_qty,
                receipt_value=l.receipt_value,
                issue_qty=l.issue_qty,
                issue_value=l.issue_value,
                closing_qty=l.closing_qty,
                closing_value=l.closing_value,
                source_row=l.source_row,
                warning_codes=l.warning_codes or [],
                diff_closing_qty=diff_q,
                diff_closing_value=diff_v,
            )
        )

    meta = StockStatementMetadata(
        has_statement=True,
        batch_id=str(batch.id),
        statement_month=month,
        statement_year=year,
        statement_date=batch.statement_date.isoformat(),
        source_filename=batch.source_filename,
        status=batch.status,
        created_at=batch.created_at,
        created_by_name=creator.full_name or creator.username if creator else None,
        updated_at=batch.updated_at,
        updated_by_name=updater.full_name or updater.username if updater else None,
        row_count=batch.row_count,
        warning_count=batch.warning_count,
    )

    summary = StockStatementSummary(
        item_count=int(totals[0]),
        total_opening_value=Decimal(str(totals[1])),
        total_receipt_value=Decimal(str(totals[2])),
        total_issue_value=Decimal(str(totals[3])),
        total_closing_value=Decimal(str(totals[4])),
        warning_rows_count=warning_rows_count,
    )

    return StockStatementResponse(metadata=meta, summary=summary, records=records)


def list_stock_statement_history(
    session: Session,
    month: int,
    year: int,
) -> list[StockStatementHistoryItem]:
    """List historical upload batches for a month/year (active and superseded)."""
    batches = session.scalars(
        select(StockStatementBatch)
        .where(
            StockStatementBatch.statement_month == month,
            StockStatementBatch.statement_year == year,
        )
        .order_by(StockStatementBatch.created_at.desc())
    ).all()

    items: list[StockStatementHistoryItem] = []
    for b in batches:
        uploader = session.get(User, b.uploaded_by) if b.uploaded_by else None
        items.append(
            StockStatementHistoryItem(
                batch_id=str(b.id),
                statement_month=b.statement_month,
                statement_year=b.statement_year,
                statement_date=b.statement_date.isoformat(),
                source_filename=b.source_filename,
                status=b.status,
                row_count=b.row_count,
                warning_count=b.warning_count,
                uploaded_at=b.uploaded_at,
                uploaded_by_name=uploader.full_name or uploader.username if uploader else None,
            )
        )
    return items


def export_stock_statement_excel(
    session: Session,
    month: int,
    year: int,
) -> tuple[bytes, str]:
    """Export the active stock statement to an Excel workbook matching KNL columns."""
    res = get_stock_statement(session, month, year)
    if not res.metadata.has_statement:
        raise ApplicationError("NOT_FOUND", f"No stock statement found for {MONTH_NAMES[month - 1]} {year}.", 404)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Stock Statement {month}-{year}"

    # Header styling
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

    # Title line
    ws.append([f"KNL Stock Statement for the month of {MONTH_NAMES[month - 1]} {year} (As of {res.metadata.statement_date})"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(EXPECTED_STATEMENT_COLUMNS))
    ws.cell(row=1, column=1).font = Font(name="Calibri", size=13, bold=True, color="1F4E79")

    # Header row
    ws.append(EXPECTED_STATEMENT_COLUMNS)
    for col_idx in range(1, len(EXPECTED_STATEMENT_COLUMNS) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Data rows
    for r in res.records:
        ws.append([
            r.item_id,
            r.item_description or "",
            r.cust_part_no or "",
            r.unit or "",
            float(r.opening_qty) if r.opening_qty is not None else "",
            float(r.opening_value) if r.opening_value is not None else "",
            float(r.receipt_qty) if r.receipt_qty is not None else "",
            float(r.receipt_value) if r.receipt_value is not None else "",
            float(r.issue_qty) if r.issue_qty is not None else "",
            float(r.issue_value) if r.issue_value is not None else "",
            float(r.closing_qty) if r.closing_qty is not None else "",
            float(r.closing_value) if r.closing_value is not None else "",
        ])
        curr_row = ws.max_row
        for col_idx in range(1, len(EXPECTED_STATEMENT_COLUMNS) + 1):
            cell = ws.cell(row=curr_row, column=col_idx)
            cell.border = thin_border
            if col_idx in (5, 6, 7, 8, 9, 10, 11, 12):
                cell.alignment = num_alignment
                cell.number_format = "#,##0.0000" if col_idx % 2 != 0 else "#,##0.00"
            elif col_idx in (1, 4):
                cell.alignment = center_alignment

    # Auto column width
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    buf = io.BytesIO()
    wb.save(buf)
    filename = f"KNL_Stock_Statement_{year}_{month:02d}.xlsx"
    return buf.getvalue(), filename


def export_error_report_excel(issues: list[RowIssue], filename: str) -> tuple[bytes, str]:
    """Generate an Excel error/warning report from validation issues."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Validation Issues"

    headers = ["Excel Row", "Column", "Severity", "Description"]
    ws.append(headers)
    for col_idx in range(1, 5):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    for issue in issues:
        ws.append([issue.row, issue.column, issue.severity, issue.description])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 15)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"Error_Report_{filename}.xlsx"

