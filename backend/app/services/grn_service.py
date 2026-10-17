import csv
from datetime import date, datetime
from decimal import Decimal
import io
import logging
import re
from typing import Any, Optional
from uuid import UUID

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.grn import GRNLineItem, GRNRecord
from app.models.inventory_masters import Consumable
from app.models.requirements import MonthlyRequirementPlan, RequirementLineItem
from app.schemas.requirements import GRNParsedItemResponse, GRNUploadResponse

logger = logging.getLogger("app.services.grn_service")


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _clean_num(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ("-", "—", "–", "N/A", "NA", "null", "None"):
        return 0.0
    # Remove currency symbols, commas, spaces
    s = re.sub(r"[^\d\.\-\+eE]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_date(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    s = str(val).strip()
    if not s:
        return None
    date_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


ITEM_CODE_ALIASES = [
    "item id", "item code", "item_id", "item_code", "itemid", "itemcode",
    "part no", "part_no", "partno", "part number", "material", "item", "material code",
]

QTY_ALIASES = [
    "receipt qty", "receipt_qty", "received qty", "received_qty", "accepted qty",
    "accepted_qty", "qty", "quantity", "receipt quantity", "received quantity",
    "qty received", "grn qty", "rcvd qty",
]

RATE_ALIASES = [
    "unit rate", "unit_rate", "rate", "unit price", "unit_price", "basic rate",
    "po rate", "price", "item rate", "cost", "unit cost", "rate (inr)", "rate (₹)",
]

GRN_NO_ALIASES = [
    "grn no", "grn_no", "grn number", "doc no", "document no", "receipt no",
    "receipt number", "grn#", "doc#", "invoice no", "dc no",
]

DATE_ALIASES = [
    "grn date", "date", "receipt date", "doc date", "posting date", "bill date",
    "invoice date", "entry date",
]

VENDOR_ALIASES = [
    "vendor name", "vendor", "supplier name", "supplier", "party name", "party",
    "vendor_name", "supplier_name",
]

PLANT_ALIASES = [
    "plant", "plant_id", "facility", "plant_name", "location", "unit_location", "works", "unit_name", "unit",
]


def _norm_plant(val: Optional[str]) -> str:
    if not val:
        return ""
    cleaned = str(val).strip().upper().replace(" ", "_").replace("-", "_")
    roman_map = {
        "PLANT_I": "PLANT_1",
        "PLANT_II": "PLANT_2",
        "PLANT_III": "PLANT_3",
        "PLANT_IV": "PLANT_4",
        "PLANT_V": "PLANT_5",
        "PLANT_1": "PLANT_1",
        "PLANT_2": "PLANT_2",
        "PLANT_3": "PLANT_3",
        "PLANT_4": "PLANT_4",
        "PLANT_5": "PLANT_5",
    }
    return roman_map.get(cleaned, cleaned)


def _match_col(name: str, aliases: list[str]) -> bool:
    norm = re.sub(r"[_\-\.\(\)\s]+", " ", name.lower()).strip()
    return norm in aliases or any(alias in norm for alias in aliases)


def parse_grn_tabular_rows(rows: list[list[Any]], filename: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse a list of raw rows (from excel or csv) into metadata and line items."""
    metadata: dict[str, Any] = {
        "grn_no": None,
        "grn_date": None,
        "vendor_name": None,
    }

    # Pass 1: Find the header row and map columns
    header_row_idx = -1
    col_map: dict[str, int] = {}

    for row_idx, row in enumerate(rows[:15]):
        str_cells = [_clean_str(c) for c in row]

        detected_item_col = -1
        detected_qty_col = -1
        detected_rate_col = -1

        for c_idx, cell in enumerate(str_cells):
            if not cell:
                continue
            if _match_col(cell, ITEM_CODE_ALIASES) and detected_item_col == -1:
                detected_item_col = c_idx
            elif _match_col(cell, QTY_ALIASES) and detected_qty_col == -1:
                detected_qty_col = c_idx
            elif _match_col(cell, RATE_ALIASES) and detected_rate_col == -1:
                detected_rate_col = c_idx

        # If this row is the table header:
        if detected_item_col != -1 and (detected_qty_col != -1 or detected_rate_col != -1):
            header_row_idx = row_idx
            col_map["item_code"] = detected_item_col
            if detected_qty_col != -1:
                col_map["qty"] = detected_qty_col
            if detected_rate_col != -1:
                col_map["rate"] = detected_rate_col

            # Detect additional columns in this header row
            for c_idx, cell in enumerate(str_cells):
                if c_idx in (detected_item_col, detected_qty_col, detected_rate_col):
                    continue
                if _match_col(cell, GRN_NO_ALIASES) and "grn_no" not in col_map:
                    col_map["grn_no"] = c_idx
                elif _match_col(cell, DATE_ALIASES) and "grn_date" not in col_map:
                    col_map["grn_date"] = c_idx
                elif _match_col(cell, VENDOR_ALIASES) and "vendor_name" not in col_map:
                    col_map["vendor_name"] = c_idx
                elif _match_col(cell, PLANT_ALIASES) and "plant" not in col_map:
                    col_map["plant"] = c_idx
            break

    # If header row was found after row 0, scan rows 0 to header_row_idx - 1 for title metadata
    if header_row_idx > 0:
        for row in rows[:header_row_idx]:
            for c_idx, cell in enumerate(row):
                s = _clean_str(cell)
                # Check for "GRN No: 123"
                m_grn = re.search(r"(?:GRN\s*(?:No|Number|#)?|Doc\s*No)[\s:]+([A-Za-z0-9\-\/]+)", s, re.IGNORECASE)
                if m_grn and not metadata["grn_no"]:
                    metadata["grn_no"] = m_grn.group(1).strip()
                if _match_col(s, GRN_NO_ALIASES) and c_idx + 1 < len(row) and not metadata["grn_no"]:
                    val = _clean_str(row[c_idx + 1])
                    if val and len(val) > 1:
                        metadata["grn_no"] = val

                m_ven = re.search(r"(?:Vendor|Supplier|Party)[\s:]+([A-Za-z0-9\s\.\,&]+)", s, re.IGNORECASE)
                if m_ven and not metadata["vendor_name"]:
                    metadata["vendor_name"] = m_ven.group(1).strip()
                if _match_col(s, VENDOR_ALIASES) and c_idx + 1 < len(row) and not metadata["vendor_name"]:
                    val = _clean_str(row[c_idx + 1])
                    if val:
                        metadata["vendor_name"] = val

                m_dt = re.search(r"(?:Date|GRN\s*Date)[\s:]+([0-9\-\/\.]{8,10})", s, re.IGNORECASE)
                if m_dt and not metadata["grn_date"]:
                    metadata["grn_date"] = _parse_date(m_dt.group(1))
                if _match_col(s, DATE_ALIASES) and c_idx + 1 < len(row) and not metadata["grn_date"]:
                    val = _parse_date(row[c_idx + 1])
                    if val:
                        metadata["grn_date"] = val

    # Fallback column positions if no header was found
    if header_row_idx == -1:
        header_row_idx = 0
        col_map["item_code"] = 2 if len(rows[0]) > 2 else 0
        col_map["qty"] = 14 if len(rows[0]) > 14 else (1 if len(rows[0]) > 1 else 0)
        col_map["rate"] = 20 if len(rows[0]) > 20 else (2 if len(rows[0]) > 2 else 0)

    # Pass 2: Extract data rows
    line_items: list[dict[str, Any]] = []

    for r_idx in range(header_row_idx + 1, len(rows)):
        row = rows[r_idx]
        if not row:
            continue

        item_col_idx = col_map.get("item_code", 0)
        if item_col_idx >= len(row):
            continue

        raw_item_code = _clean_str(row[item_col_idx]).upper()
        if not raw_item_code or raw_item_code in ("TOTAL", "GRAND TOTAL", "SUB TOTAL", "SUBTOTAL"):
            continue

        qty_idx = col_map.get("qty")
        rate_idx = col_map.get("rate")

        qty = _clean_num(row[qty_idx]) if (qty_idx is not None and qty_idx < len(row)) else 0.0
        rate = _clean_num(row[rate_idx]) if (rate_idx is not None and rate_idx < len(row)) else 0.0

        # Row-level metadata
        if "grn_no" in col_map and col_map["grn_no"] < len(row):
            row_grn = _clean_str(row[col_map["grn_no"]])
            if row_grn and not metadata["grn_no"]:
                metadata["grn_no"] = row_grn

        if "grn_date" in col_map and col_map["grn_date"] < len(row):
            row_dt = _parse_date(row[col_map["grn_date"]])
            if row_dt and not metadata["grn_date"]:
                metadata["grn_date"] = row_dt

        if "vendor_name" in col_map and col_map["vendor_name"] < len(row):
            row_ven = _clean_str(row[col_map["vendor_name"]])
            if row_ven and not metadata["vendor_name"]:
                metadata["vendor_name"] = row_ven

        row_plant = None
        if "plant" in col_map and col_map["plant"] < len(row):
            val_p = _clean_str(row[col_map["plant"]])
            if val_p:
                row_plant = val_p

        line_items.append({
            "item_code": raw_item_code,
            "received_qty": qty,
            "unit_rate": rate,
            "total_amount": round(qty * rate, 2),
            "plant": row_plant,
        })

    # Fallback metadata
    if not metadata["grn_no"]:
        stem = re.sub(r"[^A-Za-z0-9\-]", "", filename.split(".")[0])
        metadata["grn_no"] = f"GRN-{stem.upper() or 'IMPORT'}-{int(datetime.now().timestamp())}"

    if not metadata["grn_date"]:
        metadata["grn_date"] = datetime.now()

    return metadata, line_items


def parse_grn_file(file_bytes: bytes, filename: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse an uploaded GRN file (Excel or CSV)."""
    fn_lower = filename.lower()
    raw_rows: list[list[Any]] = []

    if fn_lower.endswith(".csv"):
        try:
            content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = file_bytes.decode("latin-1")
        reader = csv.reader(io.StringIO(content))
        raw_rows = list(reader)
    else:
        # Excel Workbook
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        if sheet is None:
            sheet = wb.worksheets[0]
        for row in sheet.iter_rows(values_only=True):
            raw_rows.append(list(row))

    if not raw_rows:
        raise ApplicationError("EMPTY_FILE", "The uploaded GRN file is empty.", 400)

    metadata, items = parse_grn_tabular_rows(raw_rows, filename)
    if not items:
        raise ApplicationError("NO_VALID_ITEMS", "No valid GRN line items could be detected in the file.", 400)

    return metadata, items


def process_grn_ingestion(
    db: Session,
    file_bytes: bytes,
    filename: str,
    user_id: Optional[UUID] = None,
    target_month: Optional[int] = None,
    target_year: Optional[int] = None,
) -> GRNUploadResponse:
    """Ingest a GRN file, update consumables latest rate, and update requirement plans."""
    metadata, items = parse_grn_file(file_bytes, filename)

    grn_no = str(metadata["grn_no"])
    grn_date = metadata["grn_date"] or datetime.now()
    vendor_name = metadata.get("vendor_name")

    # Determine planning period
    month = target_month or grn_date.month
    year = target_year or grn_date.year

    # 1. Create or retrieve GRNRecord
    grn_record = GRNRecord(
        grn_no=grn_no,
        grn_date=grn_date,
        vendor_name=vendor_name,
        uploaded_by=user_id,
    )
    db.add(grn_record)
    db.flush()

    # 2. Match consumables
    item_codes = {it["item_code"] for it in items}
    consumables_stmt = select(Consumable).where(
        func.upper(func.btrim(Consumable.item_id)).in_(item_codes)
    )
    matched_consumables = {c.item_id.upper().strip(): c for c in db.scalars(consumables_stmt).all()}

    # Group items by item_code to aggregate duplicate lines within the same GRN
    aggregated_items: dict[str, dict[str, Any]] = {}
    for it in items:
        code = it["item_code"]
        q = float(it["received_qty"] or 0.0)
        r = float(it["unit_rate"] or 0.0)
        p = it.get("plant")
        if code not in aggregated_items:
            aggregated_items[code] = {
                "item_code": code,
                "received_qty": q,
                "unit_rate": r,
                "total_amount": q * r,
                "plant": p,
            }
        else:
            prev = aggregated_items[code]
            new_qty = prev["received_qty"] + q
            new_amount = prev["total_amount"] + (q * r)
            prev["received_qty"] = new_qty
            prev["total_amount"] = new_amount
            if p and not prev.get("plant"):
                prev["plant"] = p
            # Use latest positive rate or weighted average
            if r > 0.0:
                prev["unit_rate"] = r
            elif new_qty > 0.0:
                prev["unit_rate"] = new_amount / new_qty

    # 3. Insert GRNLineItem records & update Consumable latest_grn_rate
    consumables_updated_count = 0
    parsed_response_items: list[GRNParsedItemResponse] = []

    for code, it_data in aggregated_items.items():
        consumable = matched_consumables.get(code)
        rate = float(it_data["unit_rate"])
        qty = float(it_data["received_qty"])
        amount = round(float(it_data["total_amount"]), 2)

        grn_item = GRNLineItem(
            grn_id=grn_record.id,
            consumable_id=consumable.id if consumable else None,
            item_code=code,
            received_qty=qty,
            unit_rate=rate,
            total_amount=amount,
        )
        db.add(grn_item)

        if consumable:
            if rate > 0.0:
                consumable.latest_grn_rate = Decimal(str(round(rate, 4)))
                consumables_updated_count += 1

        parsed_response_items.append(
            GRNParsedItemResponse(
                item_code=code,
                received_qty=qty,
                unit_rate=rate,
                total_amount=amount,
                consumable_matched=consumable is not None,
                consumable_name=consumable.name if consumable else None,
            )
        )

    # 4. Cascade to RequirementLineItem in active plans for this period (month & year)
    requirement_lines_updated = 0
    matched_consumable_ids = [c.id for c in matched_consumables.values()]

    if matched_consumable_ids:
        req_items_stmt = (
            select(RequirementLineItem)
            .join(MonthlyRequirementPlan, RequirementLineItem.plan_id == MonthlyRequirementPlan.id)
            .where(
                MonthlyRequirementPlan.month == month,
                MonthlyRequirementPlan.year == year,
                RequirementLineItem.consumable_id.in_(matched_consumable_ids),
            )
        )
        req_line_items = db.scalars(req_items_stmt).all()

        for req_item in req_line_items:
            # Find matching GRN item
            c_code = None
            if req_item.consumable:
                c_code = req_item.consumable.item_id.upper().strip()
            else:
                for c in matched_consumables.values():
                    if c.id == req_item.consumable_id:
                        c_code = c.item_id.upper().strip()
                        break

            if c_code and c_code in aggregated_items:
                grn_info = aggregated_items[c_code]
                item_plant = grn_info.get("plant")
                if item_plant and req_item.plan and req_item.plan.plant_id:
                    if _norm_plant(req_item.plan.plant_id) != _norm_plant(item_plant):
                        continue

                unit_rate = float(grn_info["unit_rate"])
                received_qty = float(grn_info["received_qty"])

                if unit_rate > 0.0:
                    req_item.rate = unit_rate
                req_item.receipt_qty = float(getattr(req_item, "receipt_qty", 0.0) or 0.0) + received_qty
                req_item.receipt_value = round(req_item.receipt_qty * req_item.rate, 2)
                requirement_lines_updated += 1

    db.commit()
    db.refresh(grn_record)

    total_receipt_qty = sum(it["received_qty"] for it in aggregated_items.values())
    total_receipt_val = sum(it["total_amount"] for it in aggregated_items.values())

    return GRNUploadResponse(
        grn_id=grn_record.id,
        grn_no=grn_no,
        grn_date=grn_date,
        vendor_name=vendor_name,
        total_items=len(aggregated_items),
        total_receipt_qty=round(total_receipt_qty, 4),
        total_receipt_value=round(total_receipt_val, 2),
        consumables_updated=consumables_updated_count,
        requirement_lines_updated=requirement_lines_updated,
        items=parsed_response_items,
    )
