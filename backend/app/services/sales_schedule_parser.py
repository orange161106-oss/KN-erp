"""KNL Sales Schedule (Production Order from Sales) Two-Pass Parser and Service.

Handles KNL's hierarchical Excel layout ("Pro.Order.pdf"):
- Left columns: S.No, Part No, Item ID, Part Description.
- Quantity columns with 4-row headers: Month label, Schedule given on, Month date, Revision (R0, R1, R2).
- Section / company headings in data rows rather than inline columns.
- Two-pass parser:
    * First block (Ashok Leyland) has NO heading row, identified by closing "ASHOK LEYLAND - TOTAL".
    * Subsequent blocks have opening heading banner and closing "TOTAL" / "- TOTAL" row.
    * Job Work tagged with section_type = 'JOB_WORK'.
    * Closing subtotal reconciliation checks.
    * Grand Total reconciliation check.
- Exact alias matching via customer_aliases table (no fuzzy matching, unknown headings block import).
- Skips INR Value columns ("Value", "Lakhs", "Rs", "INR").
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID, uuid4

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.masters import Customer, CustomerAlias, Product


# ---------------------------------------------------------------------------
# Default Seeding for KNL Customers & Aliases
# ---------------------------------------------------------------------------

DEFAULT_CUSTOMERS = [
    {
        "code": "CUST-AL",
        "name": "Ashok Leyland",
        "aliases": [
            {"alias": "ASHOK LEYLAND", "group": None},
        ],
    },
    {
        "code": "CUST-TAFE",
        "name": "TAFE",
        "aliases": [
            {"alias": "TAFE", "group": None},
        ],
    },
    {
        "code": "CUST-TAFE-FED",
        "name": "TAFE FED",
        "aliases": [
            {"alias": "TAFE FED Component", "group": "Component"},
            {"alias": "TAFE FED Child Parts", "group": "Child Parts"},
            {"alias": "TAFE FED", "group": None},
        ],
    },
    {
        "code": "CUST-TVS",
        "name": "TVS Motor Company",
        "aliases": [
            {"alias": "TVS COMPONENT", "group": "Component"},
            {"alias": "TVS CHILD PARTS", "group": "Child Parts"},
            {"alias": "TVS", "group": None},
        ],
    },
    {
        "code": "CUST-MINDA",
        "name": "Minda Corporation",
        "aliases": [
            {"alias": "MINDA", "group": None},
        ],
    },
    {
        "code": "CUST-GREAVES",
        "name": "Greaves Mobility",
        "aliases": [
            {"alias": "GREAVES MOBILITY", "group": None},
        ],
    },
    {
        "code": "CUST-JOBWORK",
        "name": "Job Work",
        "aliases": [
            {"alias": "JOB WORK", "group": "Job Work"},
        ],
    },
]


def normalize_alias(text: str) -> str:
    """Normalize alias text for strict, deterministic matching.
    
    1. Trim whitespace and collapse multiple spaces.
    2. Strip trailing '- TOTAL', 'TOTAL', '-TOTAL' (case-insensitive).
    3. Lowercase.
    """
    if not text:
        return ""
    cleaned = " ".join(str(text).strip().split())
    # Strip trailing total markers
    cleaned = re.sub(r"\s*[-–—]?\s*TOTAL\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.strip().split())
    return cleaned.lower()


def seed_default_customers_and_aliases(session: Session) -> None:
    """Ensure standard KNL customers and verified aliases exist in PostgreSQL."""
    existing_codes = set(session.scalars(select(Customer.code)).all())
    existing_aliases = set(session.scalars(select(CustomerAlias.normalized_alias)).all())

    needed_custs = [c for c in DEFAULT_CUSTOMERS if c["code"] not in existing_codes]
    needed_aliases = [
        (c["code"], a) for c in DEFAULT_CUSTOMERS
        for a in c["aliases"]
        if normalize_alias(a["alias"]) not in existing_aliases
    ]
    if not needed_custs and not needed_aliases:
        return

    cust_by_code: dict[str, Customer] = {}
    if existing_codes:
        for c in session.scalars(select(Customer).where(Customer.code.in_(list(existing_codes)))).all():
            cust_by_code[c.code] = c

    for item in needed_custs:
        new_cust = Customer(
            id=uuid4(),
            code=item["code"],
            name=item["name"],
            is_active=True,
        )
        session.add(new_cust)
        cust_by_code[item["code"]] = new_cust
    if needed_custs:
        session.flush()

    for code, alias_data in needed_aliases:
        parent_cust = cust_by_code.get(code)
        if not parent_cust:
            continue
        alias_text = alias_data["alias"]
        norm = normalize_alias(alias_text)
        session.add(
            CustomerAlias(
                id=uuid4(),
                customer_id=parent_cust.id,
                alias_text=alias_text,
                normalized_alias=norm,
                group_label=alias_data["group"],
                is_active=True,
            )
        )
    session.flush()
    session.flush()


# ---------------------------------------------------------------------------
# Date & Period Helpers
# ---------------------------------------------------------------------------

def parse_period_string(value: Any) -> str:
    """Parse various month representations (Oct'26, 01.10.2026, 2026-10) to YYYY-MM."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    text = str(value or "").strip()
    if not text:
        raise ApplicationError("PLANNING_PERIOD_REQUIRED", "Planning month is missing.", 422)

    # Standard formats
    for fmt in ("%Y-%m", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError:
            pass

    # "Oct'26", "Oct-26", "October 2026", "Oct 2026"
    m_match = re.match(r"^([a-zA-Z]{3,9})[\s'’\-_]*([0-9]{2,4})$", text)
    if m_match:
        m_name, y_raw = m_match.groups()
        if len(y_raw) == 2:
            year = 2000 + int(y_raw)
        else:
            year = int(y_raw)
        try:
            dt = datetime.strptime(f"{m_name[:3]} {year}", "%b %Y")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    raise ApplicationError("PLANNING_PERIOD_INVALID", f"Could not parse period '{text}'.", 422)


def parse_date_value(value: Any) -> Optional[datetime]:
    """Parse cell value to datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def is_value_column_header(text: str) -> bool:
    """Check if header denotes an INR monetary value column that must be ignored."""
    lower = str(text or "").lower()
    return any(kw in lower for kw in ("value", "lakhs", "lakh", "inr", "rs", "₹", "rupee"))


# ---------------------------------------------------------------------------
# Sales Schedule Parser
# ---------------------------------------------------------------------------

class QuantityColumnMetadata:
    def __init__(
        self,
        col_index: int,
        month_label: str,
        planning_period: str,
        revision_label: str,
        schedule_given_on: Optional[datetime] = None,
        month_date: Optional[datetime] = None,
    ):
        self.col_index = col_index
        self.month_label = month_label
        self.planning_period = planning_period
        self.revision_label = revision_label.upper()
        self.schedule_given_on = schedule_given_on
        self.month_date = month_date

    @property
    def key(self) -> str:
        return f"{self.planning_period}_{self.revision_label}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "col_index": self.col_index,
            "month_label": self.month_label,
            "planning_period": self.planning_period,
            "revision_label": self.revision_label,
            "schedule_given_on": self.schedule_given_on.strftime("%d.%m.%Y") if self.schedule_given_on else None,
            "month_date": self.month_date.strftime("%d.%m.%Y") if self.month_date else None,
        }


def detect_header_layout(rows: list[tuple[Any, ...]]) -> tuple[int, dict[str, int], list[QuantityColumnMetadata]]:
    """Detect left column positions and all valid revision quantity columns.
    
    Returns:
        header_row_index: Row index where column identities reside (0-based)
        left_columns: {'s_no': idx, 'part_number': idx, 'item_id': idx, 'description': idx}
        quantity_columns: list of QuantityColumnMetadata
    """
    left_columns: dict[str, int] = {}
    header_row_idx = -1

    # Scan top 10 rows for Part No / Item ID / Description / S.No
    for r_idx, row in enumerate(rows[:10]):
        norm_cells = [re.sub(r"[^a-z0-9]", "", str(c or "").lower()) for c in row]
        col_map = {}
        for c_idx, cell in enumerate(norm_cells):
            if cell in ("sno", "slno", "serialno", "snumber"):
                col_map["s_no"] = c_idx
            elif cell in ("partno", "partnumber", "productcode", "productpartno"):
                col_map["part_number"] = c_idx
            elif cell in ("itemid", "itemcode"):
                col_map["item_id"] = c_idx
            elif cell in ("partdescription", "description", "itemdescription", "productname"):
                col_map["description"] = c_idx

        if "description" in col_map and ("part_number" in col_map or "item_id" in col_map):
            header_row_idx = r_idx
            left_columns = col_map
            break

    if header_row_idx == -1:
        # Fallback: assume first row or look for any description column
        for r_idx, row in enumerate(rows[:5]):
            norm_cells = [re.sub(r"[^a-z0-9]", "", str(c or "").lower()) for c in row]
            for c_idx, cell in enumerate(norm_cells):
                if "desc" in cell:
                    left_columns["description"] = c_idx
                if "part" in cell or "code" in cell:
                    left_columns["part_number"] = c_idx
                if "item" in cell:
                    left_columns["item_id"] = c_idx
                if "sno" in cell:
                    left_columns["s_no"] = c_idx
            if "description" in left_columns:
                header_row_idx = r_idx
                break

    if header_row_idx == -1:
        raise ApplicationError("HEADER_NOT_FOUND", "Could not locate table header with Part No and Description.", 422)

    # Defaults for missing left columns if possible
    if "part_number" not in left_columns:
        left_columns["part_number"] = 1
    if "item_id" not in left_columns:
        left_columns["item_id"] = 2
    if "description" not in left_columns:
        left_columns["description"] = 3

    # Detect Quantity columns (columns to the right of Description)
    max_left_col = max(left_columns.values())
    num_cols = len(rows[header_row_idx]) if rows else 0

    quantity_columns: list[QuantityColumnMetadata] = []

    # Check if we have 4-row header structure above or at header_row_idx
    # In KNL's Pro.Order:
    # row 0: Month label (e.g. Oct'26)
    # row 1: Schedule given on (e.g. 22.09.2026)
    # row 2: Month date (e.g. 01.10.2026)
    # row 3: Revision label (e.g. R0)
    has_four_tier = header_row_idx >= 3

    for col_idx in range(max_left_col + 1, num_cols):
        # Check all cells in this column in rows 0..header_row_idx
        col_cells = [rows[r][col_idx] if col_idx < len(rows[r]) else None for r in range(header_row_idx + 1)]
        col_text_combined = " ".join(str(c or "") for c in col_cells)

        # Skip value columns (rupees, lakhs, inr)
        if is_value_column_header(col_text_combined):
            continue

        if has_four_tier:
            row0_val = col_cells[0]
            row1_val = col_cells[1]
            row2_val = col_cells[2]
            row3_val = col_cells[3]

            # Row 3 is typically the revision (R0, R1, R2, etc.)
            rev_match = re.search(r"\b(R(?:0|[1-9][0-9]*))\b", str(row3_val or "").strip().upper())
            if not rev_match:
                # Might be row 0 or row 2
                rev_match = re.search(r"\b(R(?:0|[1-9][0-9]*))\b", col_text_combined.upper())

            if rev_match:
                revision_label = rev_match.group(1)
                # Parse period from row 0 or row 2
                try:
                    period_val = parse_period_string(row0_val)
                except ApplicationError:
                    try:
                        period_val = parse_period_string(row2_val)
                    except ApplicationError:
                        continue

                schedule_given_on = parse_date_value(row1_val)
                month_date = parse_date_value(row2_val)

                quantity_columns.append(
                    QuantityColumnMetadata(
                        col_index=col_idx,
                        month_label=str(row0_val or period_val).strip(),
                        planning_period=period_val,
                        revision_label=revision_label,
                        schedule_given_on=schedule_given_on,
                        month_date=month_date,
                    )
                )
        else:
            # Single-tier header (e.g. "Oct'26 R0" or "Quantity" / "Planned Qty")
            header_cell = str(col_cells[header_row_idx] or "").strip()
            rev_match = re.search(r"\b(R(?:0|[1-9][0-9]*))\b", header_cell.upper())
            revision_label = rev_match.group(1) if rev_match else "R0"
            try:
                period_val = parse_period_string(header_cell)
            except ApplicationError:
                period_val = datetime.now().strftime("%Y-%m")

            norm = re.sub(r"[^a-z0-9]", "", header_cell.lower())
            if "qty" in norm or "quantity" in norm or rev_match:
                quantity_columns.append(
                    QuantityColumnMetadata(
                        col_index=col_idx,
                        month_label=header_cell,
                        planning_period=period_val,
                        revision_label=revision_label,
                    )
                )

    if not quantity_columns:
        raise ApplicationError("QUANTITY_COLUMNS_MISSING", "No valid planned-quantity revision columns found.", 422)

    return header_row_idx, left_columns, quantity_columns


def is_closing_row(text: str) -> bool:
    """Check if cell text denotes a block closing subtotal row."""
    if not text:
        return False
    upper = str(text).strip().upper()
    if "GRAND TOTAL" in upper:
        return False
    return "TOTAL" in upper


def is_grand_total_row(text: str) -> bool:
    """Check if cell text denotes Grand Total row."""
    if not text:
        return False
    upper = str(text).strip().upper()
    return "GRAND TOTAL" in upper


def parse_decimal_safe(value: Any) -> Decimal:
    """Parse numeric cell value to Decimal. Blank or None becomes 0."""
    if value is None or str(value).strip() == "":
        return Decimal("0.0000")
    try:
        d = Decimal(str(value).strip().replace(",", ""))
        if not d.is_finite() or d < 0:
            return Decimal("0.0000")
        return d.quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return Decimal("0.0000")


# ---------------------------------------------------------------------------
# Two-Pass Block Extraction & Alias Matching
# ---------------------------------------------------------------------------

def parse_sales_schedule_data(
    rows: list[tuple[Any, ...]],
    session: Session,
    target_period: Optional[str] = None,
    revision_label: Optional[str] = None,
    *, seed_defaults: bool = True,
) -> dict[str, Any]:
    """Parse sales schedule workbook rows using KNL two-pass block parser."""
    if seed_defaults:
        seed_default_customers_and_aliases(session)

    header_row_idx, left_cols, qty_cols = detect_header_layout(rows)

    # Filter to specific quantity column if target_period and revision_label supplied
    active_qty_cols = qty_cols
    if target_period:
        target_p = parse_period_string(target_period)
        active_qty_cols = [q for q in active_qty_cols if q.planning_period == target_p]
    if revision_label:
        rev_clean = revision_label.strip().upper()
        active_qty_cols = [q for q in active_qty_cols if q.revision_label == rev_clean]

    if not active_qty_cols:
        active_qty_cols = qty_cols  # keep all if filter yielded none

    # Load active aliases into memory map: normalized_alias -> (Customer, CustomerAlias)
    alias_results = session.execute(
        select(CustomerAlias, Customer)
        .join(Customer, CustomerAlias.customer_id == Customer.id)
        .where(CustomerAlias.is_active.is_(True), Customer.is_active.is_(True))
    ).all()
    alias_map: dict[str, tuple[Customer, CustomerAlias]] = {
        alias.normalized_alias: (cust, alias)
        for alias, cust in alias_results
    }

    # Load active products for part number checks
    active_products = list(session.scalars(select(Product).where(Product.is_active.is_(True))))
    product_code_set = {p.code for p in active_products}
    product_item_set = {p.item_id for p in active_products if p.item_id}
    product_part_set = {p.part_number for p in active_products if p.part_number}

    data_rows = rows[header_row_idx + 1 :]

    # Pass 1: Scan rows to identify blocks and part rows
    blocks: list[dict[str, Any]] = []
    current_heading: Optional[str] = None
    current_part_rows: list[dict[str, Any]] = []
    grand_total_quantities: dict[str, Decimal] = {}

    for row_offset, row in enumerate(data_rows):
        source_row_num = header_row_idx + 2 + row_offset
        if not any(c is not None and str(c).strip() != "" for c in row):
            continue  # empty row

        def get_val(idx: Optional[int]) -> str:
            if idx is not None and idx < len(row) and row[idx] is not None:
                return str(row[idx]).strip()
            return ""

        s_no = get_val(left_cols.get("s_no"))
        part_no = get_val(left_cols.get("part_number"))
        item_id = get_val(left_cols.get("item_id"))
        description = get_val(left_cols.get("description"))

        # Combine text for row-level classification
        row_summary = f"{part_no} {item_id} {description}".strip()

        # Check for Grand Total
        if is_grand_total_row(row_summary) or any(is_grand_total_row(str(c)) for c in row[:5]):
            # Record grand total quantities
            for q_col in active_qty_cols:
                raw_qty = row[q_col.col_index] if q_col.col_index < len(row) else None
                grand_total_quantities[q_col.key] = parse_decimal_safe(raw_qty)
            break  # end of data

        # Check for Closing Total Row
        if is_closing_row(row_summary) or any(is_closing_row(str(c)) for c in row[:5]):
            raw_closing_label = description or part_no
            closing_heading = raw_closing_label
            # If current_heading is None, this closing row identifies the FIRST block (Ashok Leyland)
            if not current_heading:
                current_heading = re.sub(r"\s*[-–—]?\s*TOTAL\s*$", "", raw_closing_label, flags=re.IGNORECASE).strip()

            closing_totals: dict[str, Decimal] = {}
            for q_col in active_qty_cols:
                raw_qty = row[q_col.col_index] if q_col.col_index < len(row) else None
                closing_totals[q_col.key] = parse_decimal_safe(raw_qty)

            blocks.append({
                "heading_text": current_heading,
                "closing_label": raw_closing_label,
                "part_rows": current_part_rows,
                "closing_totals": closing_totals,
            })
            current_heading = None
            current_part_rows = []
            continue

        # Check if Heading Row (e.g. "TAFE", "TAFE FED Component", "JOB WORK")
        # Heading rows typically have empty S.No, no Item ID, and empty/zero quantities
        has_id = bool(part_no or item_id)
        has_qty = any(
            parse_decimal_safe(row[q_col.col_index] if q_col.col_index < len(row) else None) > 0
            for q_col in active_qty_cols
        )

        is_heading_candidate = (
            description
            and not item_id
            and not has_qty
            and not re.match(r"^\d+$", s_no)
        )

        if is_heading_candidate:
            current_heading = description
            current_part_rows = []
            continue

        # Part Row
        if not part_no and not item_id and not description:
            continue

        quantities: dict[str, Decimal] = {}
        for q_col in active_qty_cols:
            raw_qty = row[q_col.col_index] if q_col.col_index < len(row) else None
            quantities[q_col.key] = parse_decimal_safe(raw_qty)

        # Check master mapping
        is_mapped_part = (
            part_no in product_code_set
            or part_no in product_part_set
            or item_id in product_item_set
            or item_id in product_code_set
        )

        current_part_rows.append({
            "source_row": source_row_num,
            "s_no": s_no,
            "part_no": part_no,
            "item_id": item_id,
            "description": description,
            "quantities": quantities,
            "is_mapped_part": is_mapped_part,
        })

    # Close any dangling block
    if current_part_rows and current_heading:
        blocks.append({
            "heading_text": current_heading,
            "closing_label": current_heading,
            "part_rows": current_part_rows,
            "closing_totals": {},
        })

    # Pass 2: Alias Resolution & Reconciliation
    processed_blocks: list[dict[str, Any]] = []
    unmapped_headings: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    all_flat_rows: list[dict[str, Any]] = []

    grand_sum_by_revision: dict[str, Decimal] = {q.key: Decimal("0.0000") for q in active_qty_cols}

    for b_idx, block in enumerate(blocks):
        heading = block["heading_text"]
        norm = normalize_alias(heading)
        section_type = "JOB_WORK" if "job work" in norm else "STANDARD"

        matched_entry = alias_map.get(norm)
        customer_id: Optional[UUID] = None
        customer_name: Optional[str] = None
        customer_code: Optional[str] = None
        group_label: Optional[str] = None
        is_mapped = False

        if matched_entry:
            cust, alias_obj = matched_entry
            customer_id = cust.id
            customer_name = cust.name
            customer_code = cust.code
            group_label = alias_obj.group_label
            is_mapped = True
        else:
            if heading not in unmapped_headings:
                unmapped_headings.append(heading)

        # Block quantity reconciliation
        block_sums: dict[str, Decimal] = {q.key: Decimal("0.0000") for q in active_qty_cols}
        for p_row in block["part_rows"]:
            for q_key, q_val in p_row["quantities"].items():
                block_sums[q_key] += q_val
                grand_sum_by_revision[q_key] += q_val

        reconciliation_ok = True
        reconciliation_diffs: dict[str, str] = {}
        for q_col in active_qty_cols:
            q_key = q_col.key
            part_sum = block_sums[q_key]
            sheet_total = block["closing_totals"].get(q_key)
            if sheet_total is not None and sheet_total > 0:
                diff = abs(part_sum - sheet_total)
                if diff > Decimal("0.0001"):
                    reconciliation_ok = False
                    reconciliation_diffs[q_key] = str(diff)
                    warnings.append(
                        f"Block '{heading}' sum ({part_sum}) differs from sheet total ({sheet_total}) for {q_col.revision_label}. Diff: {diff}."
                    )

        # Build flat rows with Customer, Customer ID, Group
        for p_row in block["part_rows"]:
            for q_col in active_qty_cols:
                q_key = q_col.key
                qty = p_row["quantities"].get(q_key, Decimal("0.0000"))
                all_flat_rows.append({
                    "source_row": p_row["source_row"],
                    "customer_id": str(customer_id) if customer_id else None,
                    "customer": customer_name or heading,
                    "customer_code": customer_code or "",
                    "customer_group": group_label or ("Job Work" if section_type == "JOB_WORK" else None),
                    "product_code": p_row["part_no"] or p_row["item_id"],
                    "item_id": p_row["item_id"],
                    "part_no": p_row["part_no"],
                    "description": p_row["description"],
                    "planned_quantity": format(qty, ".4f"),
                    "uom": "Nos",
                    "target_period": q_col.planning_period,
                    "planning_version": q_col.revision_label,
                    "revision": q_col.revision_label,
                    "schedule_given_on": q_col.schedule_given_on.isoformat() if q_col.schedule_given_on else None,
                    "section_type": section_type,
                    "is_mapped_part": p_row["is_mapped_part"],
                })

        processed_blocks.append({
            "block_index": b_idx + 1,
            "heading_text": heading,
            "closing_label": block["closing_label"],
            "customer_name": customer_name,
            "customer_code": customer_code,
            "customer_id": str(customer_id) if customer_id else None,
            "group_label": group_label,
            "section_type": section_type,
            "part_count": len(block["part_rows"]),
            "quantities": {k: format(v, ".4f") for k, v in block_sums.items()},
            "sheet_totals": {k: format(v, ".4f") for k, v in block["closing_totals"].items()},
            "reconciliation_ok": reconciliation_ok,
            "reconciliation_diff": reconciliation_diffs,
            "is_mapped": is_mapped,
        })

    # Grand Total Reconciliation
    grand_reconciliation_ok = True
    grand_diffs: dict[str, str] = {}
    for q_col in active_qty_cols:
        q_key = q_col.key
        parts_total = grand_sum_by_revision[q_key]
        sheet_grand = grand_total_quantities.get(q_key)
        if sheet_grand is not None and sheet_grand > 0:
            diff = abs(parts_total - sheet_grand)
            if diff > Decimal("0.0001"):
                grand_reconciliation_ok = False
                grand_diffs[q_key] = str(diff)
                warnings.append(
                    f"Grand total check failed for {q_col.revision_label}: Sum of blocks ({parts_total}) does not match sheet Grand Total ({sheet_grand}). Diff: {diff}."
                )

    if unmapped_headings:
        errors.append(
            f"{len(unmapped_headings)} unknown company heading(s) detected: {', '.join(unmapped_headings)}. Please map them to continue."
        )

    # Check for duplicate parts within blocks
    for b in processed_blocks:
        seen_parts = set()
        block_parts = [r for r in all_flat_rows if r["customer"] == (b["customer_name"] or b["heading_text"])]
        for r in block_parts:
            key = (r["product_code"], r["target_period"], r["revision"])
            if key in seen_parts:
                warnings.append(f"Duplicate part '{r['product_code']}' in block '{b['heading_text']}'.")
            seen_parts.add(key)

    can_confirm = len(unmapped_headings) == 0 and len(all_flat_rows) > 0

    return {
        "header_row_index": header_row_idx + 1,
        "available_revisions": [q.to_dict() for q in qty_cols],
        "active_revisions": [q.to_dict() for q in active_qty_cols],
        "blocks": processed_blocks,
        "unmapped_aliases": unmapped_headings,
        "grand_total": {
            "parts_sum": {k: format(v, ".4f") for k, v in grand_sum_by_revision.items()},
            "sheet_grand_total": {k: format(v, ".4f") for k, v in grand_total_quantities.items()},
            "reconciliation_ok": grand_reconciliation_ok,
            "diffs": grand_diffs,
        },
        "total_part_rows": len(all_flat_rows),
        "sample_rows": all_flat_rows[:50],
        "can_confirm": can_confirm,
        "warnings": warnings,
        "errors": errors,
        "_all_flat_rows": all_flat_rows,
    }


def read_workbook_rows(file_bytes: bytes, filename: str, sheet_name: Optional[str] = None) -> tuple[str, list[tuple[Any, ...]]]:
    """Safely open workbook and extract rows from chosen sheet."""
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "Uploaded file is empty.", 422)

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 200 * 1024 * 1024:
                raise ApplicationError("SOURCE_TOO_LARGE", "Expanded workbook exceeds safe limit (200MB).", 422)
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except ApplicationError:
        raise
    except Exception as exc:
        raise ApplicationError("INVALID_EXCEL", f"Could not read Excel file: {str(exc)}", 422)

    try:
        target_sheet = sheet_name or wb.sheetnames[0]
        if target_sheet not in wb.sheetnames:
            raise ApplicationError("SHEET_NOT_FOUND", f"Sheet '{target_sheet}' not found in workbook.", 422)
        sheet = wb[target_sheet]
        rows = list(sheet.iter_rows(values_only=True))
        return target_sheet, rows
    finally:
        wb.close()

