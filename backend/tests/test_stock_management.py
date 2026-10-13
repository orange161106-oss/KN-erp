import io
from decimal import Decimal
import openpyxl
import pytest

from app.schemas.stock_statements import RowIssue
from app.services.stock_management_service import (
    detect_month_in_text,
    get_previous_month,
    normalize_header,
    parse_raw_decimal,
    parse_raw_int,
)


def test_normalize_header_management():
    assert normalize_header("Category") == "category"
    assert normalize_header("Type of Material") == "type of material"
    assert normalize_header("Item Id") == "item id"
    assert normalize_header("Description") == "description"
    assert normalize_header("Min. Stock Level") == "min stock level"
    assert normalize_header("Max. Stock Level") == "max stock level"
    assert normalize_header("Min Order Qty") == "min order qty"
    assert normalize_header("Lead Time in Days") == "lead time in days"


def test_parse_raw_int():
    issues: list[RowIssue] = []

    assert parse_raw_int(15, 1, "Lead Time in Days", issues) == 15
    assert parse_raw_int("30", 2, "Lead Time in Days", issues) == 30
    assert parse_raw_int("-", 3, "Lead Time in Days", issues) == 0
    assert parse_raw_int("", 4, "Lead Time in Days", issues) is None
    assert parse_raw_int(None, 5, "Lead Time in Days", issues) is None

    # Fractional lead time days must generate blocking issue
    issues_frac: list[RowIssue] = []
    res = parse_raw_int("14.5", 6, "Lead Time in Days", issues_frac)
    assert res is None
    assert len(issues_frac) == 1
    assert issues_frac[0].severity == "ERROR"
    assert "whole number" in issues_frac[0].description


def test_get_previous_month():
    assert get_previous_month(10, 2026) == (9, 2026)
    assert get_previous_month(1, 2026) == (12, 2025)
    assert get_previous_month(5, 2024) == (4, 2024)


def create_management_workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Row 1: Title
    ws.cell(row=1, column=1, value="KNL Stock Control Parameters - October 2026")

    # Row 2: Headers (8 exact columns)
    headers = [
        "Category", "Type of Material", "Item Id", "Description",
        "Min. Stock Level", "Max. Stock Level", "Min Order Qty", "Lead Time in Days"
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=2, column=col_idx, value=h)

    # Row 3: Item 1 (Valid)
    row3 = ["Consumable", "Raw Material", "TEST-01", "Welding Rod", 100, 500, 200, 15]
    for col_idx, val in enumerate(row3, start=1):
        ws.cell(row=3, column=col_idx, value=val)

    # Row 4: Item 2 (Min > Max violation)
    row4 = ["Consumable", "Raw Material", "TEST-02", "Grinding Disk", 600, 300, 50, 7]
    for col_idx, val in enumerate(row4, start=1):
        ws.cell(row=4, column=col_idx, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

