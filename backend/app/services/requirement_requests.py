import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID, uuid4

import openpyxl
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable
from app.models.requirement_requests import RequirementRequest, RequirementRequestBatch
from app.schemas.auth import CurrentUser
from app.schemas.requirement_requests import (
    DuplicateItemWarning,
    ParsedRequestRow,
    RequirementRequestConfirmRequest,
    RequirementRequestConfirmResponse,
    RequirementRequestPreviewResponse,
    SheetImportSummary,
    UnitConflictWarning,
    UnknownItemIdError,
)

SHEET_SOURCE_MAPPINGS = {
    'plant 1': ('PLANT', 'P1'),
    'plant i': ('PLANT', 'P1'),
    'plant 2': ('PLANT', 'P2'),
    'plant ii': ('PLANT', 'P2'),
    'plant 3': ('PLANT', 'P3'),
    'plant iii': ('PLANT', 'P3'),
    'plant 4': ('PLANT', 'P4'),
    'plant iv': ('PLANT', 'P4'),
    'plant 5': ('PLANT', 'P5'),
    'plant v': ('PLANT', 'P5'),
    'tool room': ('DEPARTMENT', 'TOOL_ROOM'),
    'pmd': ('DEPARTMENT', 'PMD'),
    'sales': ('DEPARTMENT', 'SALES'),
    'npd': ('DEPARTMENT', 'NPD'),
    'hrd': ('DEPARTMENT', 'HRD'),
    'qad': ('DEPARTMENT', 'QAD'),
}

MONTH_NAMES = {
    1: ['jan', 'january'],
    2: ['feb', 'february'],
    3: ['mar', 'march'],
    4: ['apr', 'april'],
    5: ['may', 'mayl'],  # Handles historical typo 'Mayl'26'
    6: ['jun', 'june'],
    7: ['jul', 'july'],
    8: ['aug', 'august'],
    9: ['sep', 'sept', 'september'],
    10: ['oct', 'october'],
    11: ['nov', 'november'],
    12: ['dec', 'december'],
}


def normalize_token(val: Any) -> str:
    if val is None:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(val).strip().lower())


def is_month_match(val: Any, target_month: int, target_year: int) -> bool:
    if not val:
        return False
    norm = normalize_token(val)
    if not norm:
        return False
    yr2 = str(target_year)[-2:]
    yr4 = str(target_year)
    tokens = MONTH_NAMES.get(target_month, [])
    for m in tokens:
        if norm == f"{m}{yr2}" or norm == f"{m}{yr4}":
            return True
        if norm.startswith(m) and (norm.endswith(yr2) or norm.endswith(yr4)):
            return True
    return False


def normalize_unit(unit_str: Optional[str]) -> str:
    if not unit_str:
        return ""
    u = normalize_token(unit_str)
    # Common synonyms/abbreviations in KNL consumable sheets
    if u in ["nos", "no", "number", "numbers"]:
        return "nos"
    if u in ["kgs", "kg", "kilogram", "kilograms"]:
        return "kgs"
    if u in ["ltrs", "ltr", "liter", "liters", "litres"]:
        return "ltrs"
    if u in ["sets", "set"]:
        return "sets"
    if u in ["meters", "meter", "mtrs", "mtr", "m"]:
        return "mtrs"
    if u in ["pairs", "pair", "prs", "pr"]:
        return "pairs"
    if u in ["rolls", "roll"]:
        return "rolls"
    if u in ["klr", "kiloliter"]:
        return "klr"
    return u


def _compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def preview_requirement_requests_workbook(
    session: Session,
    file_bytes: bytes,
    filename: str,
    planning_month: int,
    planning_year: int,
    sheet_name_filter: Optional[str] = None,
) -> RequirementRequestPreviewResponse:
    if not file_bytes:
        raise ApplicationError("INVALID_REQUEST_FILE", "Uploaded file is empty.", 422)

    planning_period = f"{planning_year:04d}-{planning_month:02d}"
    file_hash = _compute_file_hash(file_bytes)

    # Load master consumables from DB
    master_consumables_rows = session.execute(
        select(Consumable.id, Consumable.item_id, Consumable.name, Consumable.purchasing_unit)
    ).all()
    master_by_code: dict[str, dict[str, Any]] = {}
    for r in master_consumables_rows:
        if r.item_id:
            master_by_code[r.item_id.strip().upper()] = {
                "id": r.id,
                "name": r.name,
                "purchasing_unit": r.purchasing_unit,
            }

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_WORKBOOK", f"Failed to open workbook: {str(e)}", 422) from e

    sheets_to_process: list[tuple[str, str, str]] = []  # (sheet_name, source_type, source_code)
    for name in wb.sheetnames:
        norm_name = re.sub(r'\s+', ' ', name.strip().lower())
        if sheet_name_filter and norm_name != normalize_token(sheet_name_filter):
            continue
        if norm_name in SHEET_SOURCE_MAPPINGS:
            stype, scode = SHEET_SOURCE_MAPPINGS[norm_name]
            sheets_to_process.append((name, stype, scode))

    if not sheets_to_process:
        available = ", ".join(wb.sheetnames[:15])
        raise ApplicationError(
            "NO_MATCHING_REQUEST_SHEETS",
            f"No recognizable plant or department request sheets found. Available sheets: {available}",
            422,
        )

    all_valid_requests: list[ParsedRequestRow] = []
    all_unknown_items: list[UnknownItemIdError] = []
    all_duplicates: list[DuplicateItemWarning] = []
    sheet_summaries: list[SheetImportSummary] = []
    units_by_item: dict[str, dict[str, str]] = {}  # item_id -> {source_code: submitted_unit}

    total_zero_skipped = 0

    for sheet_name, source_type, source_code in sheets_to_process:
        ws = wb[sheet_name]

        # 1. Detect month column
        month_col = None
        month_row_idx = None
        for r in range(1, min(6, ws.max_row + 1)):
            for c in range(1, ws.max_column + 1):
                val = ws.cell(r, c).value
                if is_month_match(val, planning_month, planning_year):
                    month_col = c
                    month_row_idx = r
                    break
            if month_col:
                break

        if not month_col:
            # Month header not found for this sheet
            continue

        # 2. Detect column headers (Item ID, Unit, Description)
        item_id_col = None
        unit_col = None
        desc_col = None
        header_row_idx = None
        for r in range(1, min(6, ws.max_row + 1)):
            for c in range(1, ws.max_column + 1):
                val = ws.cell(r, c).value
                norm = normalize_token(val)
                if norm in ['itemid', 'itemcode', 'itemno']:
                    item_id_col = c
                    header_row_idx = r
                elif norm == 'unit':
                    unit_col = c
                elif norm in ['itemdescription', 'description']:
                    desc_col = c
            if item_id_col:
                break

        if not item_id_col:
            continue

        data_start_row = max(filter(None, [month_row_idx, header_row_idx, 1])) + 1

        sheet_valid_count = 0
        sheet_unknown_count = 0
        sheet_duplicate_count = 0
        sheet_zero_count = 0
        sheet_total_qty = Decimal("0")
        seen_in_sheet: set[str] = set()

        for r in range(data_start_row, ws.max_row + 1):
            raw_id = ws.cell(r, item_id_col).value
            if not raw_id:
                continue
            item_id_str = str(raw_id).strip().upper()

            # Ignore structural rows (Total, headers, etc.)
            norm_id = normalize_token(item_id_str)
            if norm_id in ['total', 'itemid', 'sno', 'grandtotal']:
                continue

            # Flag invalid format (e.g. "Resharpenning", words without digits)
            if not re.match(r'^[A-Z0-9_-]{5,20}$', item_id_str) or not any(c.isdigit() for c in item_id_str):
                continue

            desc = str(ws.cell(r, desc_col).value).strip() if (desc_col and ws.cell(r, desc_col).value) else None
            unit_val = str(ws.cell(r, unit_col).value).strip() if (unit_col and ws.cell(r, unit_col).value) else "NOS"

            qty_val = ws.cell(r, month_col).value
            if qty_val is None:
                sheet_zero_count += 1
                continue

            try:
                dec_qty = Decimal(str(qty_val).strip())
            except (InvalidOperation, TypeError, ValueError):
                sheet_zero_count += 1
                continue

            if dec_qty <= Decimal("0"):
                sheet_zero_count += 1
                continue

            # Duplicate check within sheet
            if item_id_str in seen_in_sheet:
                sheet_duplicate_count += 1
                all_duplicates.append(
                    DuplicateItemWarning(
                        sheet=sheet_name,
                        row=r,
                        item_id=item_id_str,
                        description=desc,
                        quantity=dec_qty,
                    )
                )
                continue
            seen_in_sheet.add(item_id_str)

            # Master check
            master_item = master_by_code.get(item_id_str)
            if not master_item:
                sheet_unknown_count += 1
                all_unknown_items.append(
                    UnknownItemIdError(
                        sheet=sheet_name,
                        row=r,
                        item_id=item_id_str,
                        description=desc,
                        unit=unit_val,
                        quantity=dec_qty,
                    )
                )
                continue

            # Valid consumable request
            sheet_valid_count += 1
            sheet_total_qty += dec_qty
            units_by_item.setdefault(item_id_str, {})[source_code] = unit_val

            all_valid_requests.append(
                ParsedRequestRow(
                    source_type=source_type,
                    source_code=source_code,
                    sheet_name=sheet_name,
                    row_number=r,
                    item_id=item_id_str,
                    consumable_id=master_item["id"],
                    consumable_name=master_item["name"] or (desc or item_id_str),
                    unit=unit_val,
                    quantity=dec_qty,
                )
            )

        total_zero_skipped += sheet_zero_count
        sheet_summaries.append(
            SheetImportSummary(
                sheet_name=sheet_name,
                source_type=source_type,
                source_code=source_code,
                header_row=header_row_idx or 1,
                month_column=month_col,
                item_id_column=item_id_col,
                valid_count=sheet_valid_count,
                unknown_count=sheet_unknown_count,
                duplicate_count=sheet_duplicate_count,
                zero_or_blank_count=sheet_zero_count,
                total_quantity=sheet_total_qty,
            )
        )

    wb.close()

    # Unit conflict evaluation across sheets (Section 2h)
    unit_conflicts: list[UnitConflictWarning] = []
    for item_id, source_units in units_by_item.items():
        unique_submitted_units = set(source_units.values())
        if len(unique_submitted_units) > 1:
            master_info = master_by_code.get(item_id, {})
            master_unit = master_info.get("purchasing_unit")
            master_norm = normalize_unit(master_unit)
            # Check if all submitted units normalize to the master purchasing unit
            normalized_submitted = {normalize_unit(u) for u in unique_submitted_units}
            is_compatible = (master_norm in normalized_submitted) and (len(normalized_submitted) == 1)

            unit_conflicts.append(
                UnitConflictWarning(
                    item_id=item_id,
                    consumable_name=master_info.get("name"),
                    master_purchasing_unit=master_unit,
                    submitted_units=source_units,
                    is_compatible=is_compatible,
                    message=(
                        f"Unit variation resolved to master purchasing unit '{master_unit}'."
                        if is_compatible
                        else f"Unit conflict across sources: {source_units}. Excluded from total until unit conversion is verified."
                    ),
                )
            )

    # Check for existing active batches for this month/year
    existing_batches = session.scalars(
        select(RequirementRequestBatch).where(
            RequirementRequestBatch.planning_month == planning_month,
            RequirementRequestBatch.planning_year == planning_year,
            RequirementRequestBatch.status == "ACTIVE",
        )
    ).all()
    warning_msg = None
    if existing_batches:
        srcs = ", ".join({b.source_code for b in existing_batches})
        warning_msg = f"An import for {planning_period} already exists for sources ({srcs}). Confirming will replace existing requests."

    review_token = hashlib.sha256(
        f"{file_hash}:{planning_period}:{len(all_valid_requests)}:{len(all_unknown_items)}".encode()
    ).hexdigest()

    return RequirementRequestPreviewResponse(
        filename=filename,
        planning_month=planning_month,
        planning_year=planning_year,
        planning_period=planning_period,
        file_hash=file_hash,
        sheets_processed=sheet_summaries,
        total_valid_requests=len(all_valid_requests),
        total_unknown_ids=len(all_unknown_items),
        total_zero_skipped=total_zero_skipped,
        valid_requests=all_valid_requests,
        unknown_items=all_unknown_items,
        duplicates=all_duplicates,
        unit_conflicts=unit_conflicts,
        can_confirm=bool(all_valid_requests),
        existing_batches_warning=warning_msg,
        review_token=review_token,
    )


def confirm_requirement_requests(
    session: Session,
    request: RequirementRequestConfirmRequest,
    preview: RequirementRequestPreviewResponse,
    actor: CurrentUser,
) -> RequirementRequestConfirmResponse:
    # 1. Authorization check
    has_perm = actor.is_super_admin or actor.requests_create or "ADMIN" in [r.upper() for r in actor.roles]
    if not has_perm:
        raise ApplicationError(
            "PERMISSION_DENIED",
            "User does not have permission to import or modify requirement requests.",
            403,
        )

    if request.review_token != preview.review_token:
        raise ApplicationError(
            "STALE_PREVIEW",
            "Preview token is stale or invalid. Please preview the file again before confirming.",
            409,
        )

    target_sources = set(request.source_codes) if request.source_codes else {
        s.source_code for s in preview.sheets_processed
    }

    # Group valid requests by source_code
    requests_by_source: dict[str, list[ParsedRequestRow]] = {}
    for r in preview.valid_requests:
        if r.source_code in target_sources:
            requests_by_source.setdefault(r.source_code, []).append(r)

    created_batch_ids: list[UUID] = []
    superseded_batch_count = 0
    total_imported_rows = 0

    # In single transaction
    for sheet_summary in preview.sheets_processed:
        source_code = sheet_summary.source_code
        if source_code not in target_sources:
            continue

        rows = requests_by_source.get(source_code, [])

        # Mark existing active batches for (month, year, source_code) as SUPERSEDED
        existing_active_batches = session.scalars(
            select(RequirementRequestBatch).where(
                RequirementRequestBatch.planning_month == preview.planning_month,
                RequirementRequestBatch.planning_year == preview.planning_year,
                RequirementRequestBatch.source_code == source_code,
                RequirementRequestBatch.status == "ACTIVE",
            )
        ).all()
        for eb in existing_active_batches:
            eb.status = "SUPERSEDED"
            superseded_batch_count += 1

        # Mark existing active requests as SUPERSEDED
        session.execute(
            update(RequirementRequest)
            .where(
                RequirementRequest.planning_month == preview.planning_month,
                RequirementRequest.planning_year == preview.planning_year,
                RequirementRequest.source_code == source_code,
                RequirementRequest.status == "ACTIVE",
            )
            .values(status="SUPERSEDED")
        )

        batch_id = uuid4()
        batch = RequirementRequestBatch(
            id=batch_id,
            planning_month=preview.planning_month,
            planning_year=preview.planning_year,
            source_type=sheet_summary.source_type,
            source_code=source_code,
            source_filename=preview.filename,
            sheet_name=sheet_summary.sheet_name,
            file_hash=preview.file_hash,
            status="ACTIVE",
            row_count=len(rows),
            valid_row_count=len(rows),
            error_row_count=sheet_summary.unknown_count,
            validation_summary={
                "zero_or_blank_count": sheet_summary.zero_or_blank_count,
                "duplicate_count": sheet_summary.duplicate_count,
                "total_quantity": str(sheet_summary.total_quantity),
            },
            uploaded_by=actor.id,
        )
        session.add(batch)
        created_batch_ids.append(batch_id)

        for row in rows:
            req_item = RequirementRequest(
                id=uuid4(),
                planning_month=preview.planning_month,
                planning_year=preview.planning_year,
                source_type=row.source_type,
                source_code=row.source_code,
                consumable_id=row.consumable_id,
                quantity=row.quantity,
                unit=row.unit,
                import_batch_id=batch_id,
                status="ACTIVE",
                created_by=actor.id,
            )
            session.add(req_item)
            total_imported_rows += 1

        from app.models.auth import User
        valid_actor_id = actor.id if (actor and actor.id and session.get(User, actor.id)) else None
        session.add(
            AuditLog(
                actor_id=valid_actor_id,
                user_id=valid_actor_id,
                action="IMPORT_REQUIREMENT_REQUESTS",
                entity_type="requirement_request_batch",
                entity_id=batch_id,
                new_values={
                    "planning_period": preview.planning_period,
                    "source_code": source_code,
                    "row_count": len(rows),
                    "file_hash": preview.file_hash,
                },
                reason=f"Imported {source_code} consumable requests for {preview.planning_period}",
            )
        )

    session.commit()

    return RequirementRequestConfirmResponse(
        planning_month=preview.planning_month,
        planning_year=preview.planning_year,
        planning_period=preview.planning_period,
        imported_batch_count=len(created_batch_ids),
        imported_row_count=total_imported_rows,
        superseded_batch_count=superseded_batch_count,
        batch_ids=created_batch_ids,
        message=f"Successfully imported {total_imported_rows} consumable requests across {len(created_batch_ids)} sources for {preview.planning_period}.",
    )


def export_unknown_items_csv(unknown_items: list[UnknownItemIdError]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sheet Name", "Row Number", "Item ID", "Description", "Unit", "Quantity", "Error Reason"])
    for item in unknown_items:
        writer.writerow([
            item.sheet,
            item.row,
            item.item_id,
            item.description or "",
            item.unit or "",
            str(item.quantity),
            "Item ID not found in consumable master",
        ])
    return output.getvalue().encode("utf-8")


def get_active_requirement_requests_map(
    session: Session,
    planning_month: int,
    planning_year: int,
) -> dict[UUID, dict[str, Any]]:
    """Query active requirement requests for a given month/year.

    Returns:
        dict keyed by consumable_id -> {
            'P1': Decimal, 'P2': Decimal, ..., 'TOOL_ROOM': Decimal, ...,
            'TOTAL': Decimal,
            'units': {source_code: unit},
            'has_unit_conflict': bool,
            'is_unit_compatible': bool,
        }
    """
    rows = session.execute(
        select(
            RequirementRequest.consumable_id,
            RequirementRequest.source_code,
            RequirementRequest.quantity,
            RequirementRequest.unit,
            Consumable.purchasing_unit,
        )
        .join(Consumable, Consumable.id == RequirementRequest.consumable_id)
        .where(
            RequirementRequest.planning_month == planning_month,
            RequirementRequest.planning_year == planning_year,
            RequirementRequest.status == "ACTIVE",
        )
    ).all()

    by_consumable: dict[UUID, dict[str, Any]] = {}
    for consumable_id, source_code, qty, unit, purchasing_unit in rows:
        if consumable_id not in by_consumable:
            by_consumable[consumable_id] = {
                "P1": Decimal("0"),
                "P2": Decimal("0"),
                "P3": Decimal("0"),
                "P4": Decimal("0"),
                "P5": Decimal("0"),
                "TOOL_ROOM": Decimal("0"),
                "PMD": Decimal("0"),
                "SALES": Decimal("0"),
                "NPD": Decimal("0"),
                "HRD": Decimal("0"),
                "QAD": Decimal("0"),
                "TOTAL": Decimal("0"),
                "units": {},
                "purchasing_unit": purchasing_unit,
                "has_unit_conflict": False,
                "is_unit_compatible": True,
            }
        bucket = by_consumable[consumable_id]
        if source_code in bucket:
            bucket[source_code] += qty
        bucket["units"][source_code] = unit

    # Evaluate unit conflict per consumable and calculate total
    for consumable_id, bucket in by_consumable.items():
        unique_units = set(bucket["units"].values())
        norm_units = {normalize_unit(u) for u in unique_units}
        raw_total = (
            bucket["P1"] + bucket["P2"] + bucket["P3"] + bucket["P4"] + bucket["P5"]
            + bucket["TOOL_ROOM"] + bucket["PMD"] + bucket["SALES"]
            + bucket["NPD"] + bucket["HRD"] + bucket["QAD"]
        )
        bucket["raw_sum"] = raw_total
        bucket["TOTAL"] = raw_total
        if len(norm_units) > 1:
            bucket["has_unit_conflict"] = True
            bucket["is_unit_compatible"] = False
            details_parts = [f"{src}: {u}" for src, u in bucket["units"].items()]
            bucket["unit_conflict_details"] = f"Unit conflict across sources: {', '.join(details_parts)}"
        else:
            bucket["has_unit_conflict"] = False
            bucket["is_unit_compatible"] = True
            bucket["unit_conflict_details"] = None

    return by_consumable
