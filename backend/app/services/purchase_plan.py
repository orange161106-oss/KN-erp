"""Service layer for Monthly Purchase Planning (Normal View & MD View).

Implements:
- Month-wise purchase planning linked to PRD planning period.
- Normal View (23 columns) and MD View (76 columns) mapping on the same dataset.
- Deterministic purchase gap calculation using approved rules.
- Excel inspection, validation, import merging, and styled export.
- Integration with Purchase Approvals Queue.
"""

from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal
import io
import re
from typing import Any, Optional
from uuid import UUID

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier
from app.models.prd import PlanningVersion
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_plan import PurchasePlan, PurchasePlanItem
from app.schemas.purchase_plan import (
    PlanImportConfirmRequest,
    PlanInspectResult,
    PurchasePlanItemSchema,
    PurchasePlanResponse,
    RecalculatePlanRequest,
    SavePurchasePlanRequest,
    SendToApprovalRequest,
    UpdatePlanParametersRequest,
)

# Standard Column lists as defined in KNL Specification
NORMAL_VIEW_HEADERS = [
    "S. No.", "Req. Type", "Item Id", "Description", "Unit", "Output / Unit",
    "MOQ.", "Min. Stock. Level", "Max. Stock Level", "Rate",
    "O/s.", "Receipt", "Issues", "C/s.", "Prd. Qty.",
    "Sch.", "Req. Qty.", "Order Qty.", "Order Value",
    "Pur. Qty.", "Pur. Value", "Bal. Pur. Qty", "Bal. Pur. Value"
]

MD_VIEW_HEADERS = [
    "Supplier ID", "Supplier name", "Item Id", "Category", "Type of material",
    "S. No.", "Description", "Part No. of saleable item", "Used for- Name of Saleable part",
    "Used Part no (prd order)", "Process name", "Material thickness in mm / Gsm",
    "No of process per part", "Output/ Unit", "Rate",
    "Opening Qty", "Opening Value", "Receipt. Qty.", "Issue Qty.",
    "Closing Qty", "Closing Value", "Rate (Prev)",
    "Min stock level", "Max stock level", "Minimum order qty.", "Lead time to supply in days",
    "Sch. Qty. as per assy R1", "Purchasing Unit", "Sch. Qty. Cons. Itemwise R1",
    "Opening stock", "Req. Qty.", "Order Qty R1", "Order Value R1", "Receipt qty. R1", "Receipt value R1",
    "Sch. Qty. as per assy R2", "Sch. Qty. Cons. Itemwise R2", "Req. R2", "closing stock",
    "Req.qty lessed by issue qty", "Issue Qty. till", "Order Qty. R2", "Order Value R2",
    "Receipt qty. R2", "Receipt value R2",
    "Total Receipt Qty.", "Total receipt value",
    "P1", "P2", "P3", "P4", "P5", "tool room", "Quality", "PMD", "NPD", "HRD",
    "Accounts", "Purchase ,Stores&admin", "Sales", "Req. given by users", "Total Value.",
    "Avg.Monthly Consumption", "Avg.Daily Consumption", "Minimum order Quantity.",
    "Lead time to supply in days (Cons)", "Mini number of days to hold in production",
    "Min stock level (Cons)", "Max stock level (Cons)", "Lead time qty", "Re-Order Level",
    "Cost of MSL", "REORDER LEVEL(MSL+(Avg.reqd.con per dayxLead timr to supply in days))",
    "Avg. consumption per day", "Previous month Plan value", "Previous month Actual value"
]


def _parse_decimal(val: Any) -> Optional[Decimal]:
    if val is None or val == "":
        return None
    try:
        clean = str(val).replace(",", "").strip()
        if not clean or clean.lower() == "none":
            return None
        return Decimal(clean)
    except Exception:
        return None


def _format_decimal(val: Optional[Decimal], places: int = 4) -> str:
    if val is None:
        return "0.00"
    return f"{val:.{places}f}"


def _get_days_in_period(planning_period: str) -> tuple[int, int]:
    """Returns (month_days, default_working_days)."""
    try:
        parts = planning_period.split("-")
        year, month = int(parts[0]), int(parts[1])
        _, month_days = monthrange(year, month)
        working_days = max(20, month_days - 4)  # ~26-27 working days
        return month_days, working_days
    except Exception:
        return 31, 27


def get_purchase_plan(session: Session, planning_period: str) -> Optional[PurchasePlanResponse]:
    """Retrieve the monthly purchase plan and return full response schema."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == planning_period)
    ).first()

    if not plan:
        return None

    items_schema = []
    total_val = Decimal("0")
    for it in plan.items:
        if it.order_value:
            total_val += it.order_value
        items_schema.append(
            PurchasePlanItemSchema(
                id=str(it.id),
                plan_id=str(it.plan_id),
                s_no=it.s_no,
                item_id=it.item_id,
                description=it.description,
                req_type=it.req_type,
                category=it.category,
                type_of_material=it.type_of_material,
                unit=it.unit,
                purchasing_unit=it.purchasing_unit,
                output_per_unit=it.output_per_unit,
                rate=it.rate,
                moq=it.moq,
                min_stock_level=it.min_stock_level,
                max_stock_level=it.max_stock_level,
                lead_time_days=it.lead_time_days,
                prev_opening_qty=it.prev_opening_qty,
                prev_opening_val=it.prev_opening_val,
                prev_receipt_qty=it.prev_receipt_qty,
                prev_issue_qty=it.prev_issue_qty,
                prev_closing_qty=it.prev_closing_qty,
                prev_closing_val=it.prev_closing_val,
                prev_prd_qty=it.prev_prd_qty,
                sch_qty=it.sch_qty,
                req_qty=it.req_qty,
                order_qty=it.order_qty,
                order_value=it.order_value,
                receipt_qty=it.receipt_qty,
                receipt_value=it.receipt_value,
                sch_qty_r2=it.sch_qty_r2,
                req_qty_r2=it.req_qty_r2,
                order_qty_r2=it.order_qty_r2,
                order_value_r2=it.order_value_r2,
                receipt_qty_r2=it.receipt_qty_r2,
                receipt_val_r2=it.receipt_val_r2,
                pur_qty=it.pur_qty,
                bal_pur_qty=it.bal_pur_qty,
                bal_pur_value=it.bal_pur_value,
                supplier_id=it.supplier_id,
                supplier_name=it.supplier_name,
                part_no_saleable=it.part_no_saleable,
                saleable_part_name=it.saleable_part_name,
                used_part_no=it.used_part_no,
                process_name=it.process_name,
                thickness_gsm=it.thickness_gsm,
                no_of_process_per_part=it.no_of_process_per_part,
                plant_allocations=it.plant_allocations or {},
                consumption_analysis=it.consumption_analysis or {},
                override_reason=it.override_reason,
                is_modified=it.is_modified,
                created_at=it.created_at,
                updated_at=it.updated_at,
            )
        )

    return PurchasePlanResponse(
        id=str(plan.id),
        planning_period=plan.planning_period,
        planning_version_id=str(plan.planning_version_id) if plan.planning_version_id else None,
        revision_label=plan.revision_label,
        status=plan.status,
        msl_days_gas=plan.msl_days_gas,
        msl_days_general=plan.msl_days_general,
        month_days=plan.month_days,
        working_days=plan.working_days,
        source_filename=plan.source_filename,
        created_by=str(plan.created_by) if plan.created_by else None,
        created_by_name=plan.creator.username if plan.creator else "System",
        created_at=plan.created_at,
        modified_by=str(plan.modified_by) if plan.modified_by else None,
        modified_by_name=plan.modifier.username if plan.modifier else None,
        modified_at=plan.modified_at,
        total_items=len(plan.items),
        total_order_value=total_val,
        items=items_schema,
    )


def save_or_init_plan(
    session: Session,
    planning_period: str,
    user_id: UUID,
    params: Optional[UpdatePlanParametersRequest] = None,
) -> PurchasePlanResponse:
    """Initialize or update plan parameters for the month."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == planning_period)
    ).first()

    month_days, working_days = _get_days_in_period(planning_period)

    # Link to requirement version if exists
    version = session.scalars(
        select(PlanningVersion).where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
    ).first()

    if not plan:
        plan = PurchasePlan(
            planning_period=planning_period,
            planning_version_id=version.id if version else None,
            revision_label="R1",
            status="DRAFT",
            msl_days_gas=Decimal("2.0"),
            msl_days_general=Decimal("10.0"),
            month_days=month_days,
            working_days=working_days,
            created_by=user_id,
            modified_by=user_id,
        )
        session.add(plan)
        session.flush()

    if params:
        if params.msl_days_gas is not None:
            plan.msl_days_gas = params.msl_days_gas
        if params.msl_days_general is not None:
            plan.msl_days_general = params.msl_days_general
        if params.working_days is not None:
            plan.working_days = params.working_days
        plan.modified_by = user_id
        plan.modified_at = datetime.now(timezone.utc)

    session.commit()
    return get_purchase_plan(session, planning_period)  # type: ignore


def recalculate_plan(
    session: Session,
    req: RecalculatePlanRequest,
    user_id: UUID,
) -> PurchasePlanResponse:
    """Recalculate purchase plan quantities using approved deterministic formulas."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == req.planning_period)
    ).first()

    if not plan:
        raise ApplicationError("PLAN_NOT_FOUND", "No monthly purchase plan found for this period.")

    if req.msl_days_gas is not None:
        plan.msl_days_gas = req.msl_days_gas
    if req.msl_days_general is not None:
        plan.msl_days_general = req.msl_days_general

    for it in plan.items:
        # Available stock = closing stock or (opening + receipts - issues)
        avail = it.prev_closing_qty
        if avail is None:
            opening = it.prev_opening_qty or Decimal("0")
            rcpt = it.prev_receipt_qty or Decimal("0")
            iss = it.prev_issue_qty or Decimal("0")
            avail = opening + rcpt - iss

        msl = it.min_stock_level or Decimal("0")
        req_q = it.req_qty or Decimal("0")
        moq = it.moq or Decimal("0")

        # Deterministic formula:
        # Gap = MSL + Requirement - Available Stock
        gap = msl + req_q - avail

        # If user did not manually override, calculate order_qty
        if not (it.is_modified and it.override_reason):
            if gap > Decimal("0"):
                calc_qty = max(gap, moq)
            else:
                calc_qty = Decimal("0")
            it.order_qty = calc_qty

        # Order value = Order Qty * Rate
        if it.order_qty and it.rate:
            it.order_value = it.order_qty * it.rate
        else:
            it.order_value = Decimal("0")

    plan.status = "CALCULATED"
    plan.modified_by = user_id
    plan.modified_at = datetime.now(timezone.utc)
    session.commit()

    return get_purchase_plan(session, req.planning_period)  # type: ignore


def save_plan_items(
    session: Session,
    req: SavePurchasePlanRequest,
    user_id: UUID,
) -> PurchasePlanResponse:
    """Save user edits to permitted fields."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == req.planning_period)
    ).first()

    if not plan:
        raise ApplicationError("PLAN_NOT_FOUND", "No monthly purchase plan found for this period.")

    items_by_id = {str(it.id): it for it in plan.items}

    for update in req.items:
        it = items_by_id.get(update.id)
        if not it:
            continue

        if update.rate is not None:
            it.rate = update.rate
        if update.moq is not None:
            it.moq = update.moq
        if update.min_stock_level is not None:
            it.min_stock_level = update.min_stock_level
        if update.max_stock_level is not None:
            it.max_stock_level = update.max_stock_level
        if update.lead_time_days is not None:
            it.lead_time_days = update.lead_time_days
        if update.plant_allocations is not None:
            it.plant_allocations = update.plant_allocations

        # If order_qty manually adjusted
        if update.order_qty is not None and update.order_qty != it.order_qty:
            it.order_qty = update.order_qty
            it.is_modified = True
            it.override_reason = update.override_reason or "Manual user override"
            if it.rate:
                it.order_value = it.order_qty * it.rate

    plan.modified_by = user_id
    plan.modified_at = datetime.now(timezone.utc)
    session.commit()

    return get_purchase_plan(session, req.planning_period)  # type: ignore


def send_to_approval_queue(
    session: Session,
    req: SendToApprovalRequest,
    user_id: UUID,
) -> dict[str, Any]:
    """Submit recommended purchase plan items into the existing approval queue."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == req.planning_period)
    ).first()

    if not plan:
        raise ApplicationError("PLAN_NOT_FOUND", "Purchase plan not found.")

    submitted_count = 0
    items_to_process = plan.items
    if req.item_ids:
        items_to_process = [it for it in plan.items if str(it.id) in req.item_ids or it.item_id in req.item_ids]

    for it in items_to_process:
        if not it.order_qty or it.order_qty <= Decimal("0"):
            continue

        # Look up or create consumable master
        consumable = session.scalars(
            select(Consumable).where(Consumable.code == it.item_id)
        ).first()

        # Look up supplier
        supplier = None
        if it.supplier_id:
            supplier = session.scalars(
                select(Supplier).where(Supplier.code == it.supplier_id)
            ).first()

        if not supplier:
            supplier = session.scalars(select(Supplier)).first()

        if not consumable or not supplier:
            continue

        appr = PurchaseApproval(
            consumable_id=consumable.id,
            supplier_id=supplier.id,
            planning_version_id=plan.planning_version_id,
            rule_version="M5.1_V1",
            raw_calculated_qty=it.order_qty,
            system_recommended_qty=it.order_qty,
            uom=it.unit,
            status="PENDING",
            reason=f"Monthly purchase plan for {plan.planning_period} ({it.description})",
            requested_by=user_id,
        )
        session.add(appr)
        submitted_count += 1

    plan.status = "SUBMITTED"
    plan.modified_by = user_id
    plan.modified_at = datetime.now(timezone.utc)
    session.commit()

    return {
        "status": "SUCCESS",
        "submitted_count": submitted_count,
        "message": f"Successfully submitted {submitted_count} purchase recommendations to the Approval Queue.",
    }


def inspect_purchase_excel(file_bytes: bytes, filename: str) -> PlanInspectResult:
    """Inspect uploaded Excel file, detecting MD View vs Normal View."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Cannot parse Excel workbook: {exc}")

    sheet_name = wb.sheetnames[0]
    ws = wb[sheet_name]

    # Search first 5 rows for header row
    detected_headers = []
    header_row_idx = 1
    detected_view = "UNKNOWN"

    for r in range(1, min(6, ws.max_row + 1)):
        row_vals = [str(ws.cell(r, c).value or "").strip() for c in range(1, ws.max_column + 1)]
        row_str = " ".join(row_vals).lower()

        # Check for Normal View markers
        if "s. no." in row_str and ("moq" in row_str or "req. type" in row_str or "order qty" in row_str):
            detected_headers = row_vals
            header_row_idx = r
            detected_view = "NORMAL_VIEW"
            break

        # Check for MD View markers
        if "supplier id" in row_str and ("saleable" in row_str or "process name" in row_str or "thickness" in row_str):
            detected_headers = row_vals
            header_row_idx = r
            detected_view = "MD_VIEW"
            break

    if detected_view == "UNKNOWN":
        # Fallback: check row 1 or 2
        detected_headers = [str(ws.cell(2, c).value or "").strip() for c in range(1, ws.max_column + 1)]
        if len(detected_headers) > 30:
            detected_view = "MD_VIEW"
        else:
            detected_view = "NORMAL_VIEW"

    sample_rows = []
    validation_errors = []

    for r in range(header_row_idx + 1, min(header_row_idx + 10, ws.max_row + 1)):
        row_dict: dict[str, Any] = {}
        has_val = False
        for c in range(1, len(detected_headers) + 1):
            h = detected_headers[c - 1] if c - 1 < len(detected_headers) and detected_headers[c - 1] else f"Col_{c}"
            val = ws.cell(r, c).value
            if val is not None:
                has_val = True
                val_str = str(val).strip()
                if any(err_code in val_str for err_code in ["#REF!", "#VALUE!", "#DIV/0!"]):
                    validation_errors.append({
                        "row": r,
                        "column": h,
                        "error": f"Invalid Excel formula evaluation: {val_str}",
                    })
            row_dict[h] = str(val) if val is not None else ""
        if has_val:
            sample_rows.append(row_dict)

    return PlanInspectResult(
        filename=filename,
        detected_view=detected_view,
        sheet_name=sheet_name,
        total_rows=max(0, ws.max_row - header_row_idx),
        total_columns=len(detected_headers),
        headers=detected_headers,
        missing_required_headers=[],
        validation_errors=validation_errors,
        sample_rows=sample_rows,
    )


def import_purchase_plan_sheet(
    session: Session,
    confirm_req: PlanImportConfirmRequest,
    user_id: UUID,
) -> PurchasePlanResponse:
    """Import and merge purchase plan records by item_id."""
    period = confirm_req.planning_period
    save_or_init_plan(session, period, user_id)

    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == period)
    ).first()

    if not plan:
        raise ApplicationError("PLAN_CREATION_FAILED", "Unable to create purchase plan container.")

    existing_items = {it.item_id: it for it in plan.items}
    s_no_counter = len(plan.items) + 1

    for row_data in confirm_req.rows:
        # Match item id from row
        item_id = row_data.get("Item Id") or row_data.get("item_id") or row_data.get("Item ID") or row_data.get("Consumable Code")
        if not item_id or str(item_id).strip() == "":
            continue
        item_id = str(item_id).strip()

        desc = row_data.get("Description") or row_data.get("description") or f"Consumable {item_id}"
        unit = row_data.get("Unit") or row_data.get("Purchasing Unit") or "PCS"

        it = existing_items.get(item_id)
        if not it:
            it = PurchasePlanItem(
                plan_id=plan.id,
                item_id=item_id,
                description=desc,
                unit=unit,
                s_no=s_no_counter,
            )
            s_no_counter += 1
            session.add(it)
            existing_items[item_id] = it

        # Assign fields
        it.description = desc
        it.unit = unit
        if "Req. Type" in row_data:
            it.req_type = row_data["Req. Type"]
        if "Category" in row_data:
            it.category = row_data["Category"]
        if "Rate" in row_data:
            it.rate = _parse_decimal(row_data["Rate"])
        if "MOQ." in row_data or "Minimum order qty." in row_data:
            it.moq = _parse_decimal(row_data.get("MOQ.") or row_data.get("Minimum order qty."))
        if "Min. Stock. Level" in row_data or "Min stock level" in row_data:
            it.min_stock_level = _parse_decimal(row_data.get("Min. Stock. Level") or row_data.get("Min stock level"))
        if "Max. Stock Level" in row_data or "Max stock level" in row_data:
            it.max_stock_level = _parse_decimal(row_data.get("Max. Stock Level") or row_data.get("Max stock level"))
        if "Lead time to supply in days" in row_data:
            try:
                it.lead_time_days = int(row_data["Lead time to supply in days"])
            except Exception:
                pass

        # Previous month stock
        if "Opening Qty" in row_data or "O/s." in row_data:
            it.prev_opening_qty = _parse_decimal(row_data.get("Opening Qty") or row_data.get("O/s."))
        if "Receipt" in row_data or "Receipt. Qty." in row_data:
            it.prev_receipt_qty = _parse_decimal(row_data.get("Receipt") or row_data.get("Receipt. Qty."))
        if "Issues" in row_data or "Issue Qty." in row_data:
            it.prev_issue_qty = _parse_decimal(row_data.get("Issues") or row_data.get("Issue Qty."))
        if "C/s." in row_data or "Closing Qty" in row_data:
            it.prev_closing_qty = _parse_decimal(row_data.get("C/s.") or row_data.get("Closing Qty"))

        # Selected month
        if "Sch." in row_data or "Sch. Qty. as per assy R1" in row_data:
            it.sch_qty = _parse_decimal(row_data.get("Sch.") or row_data.get("Sch. Qty. as per assy R1"))
        if "Req. Qty." in row_data:
            it.req_qty = _parse_decimal(row_data["Req. Qty."])
        if "Order Qty." in row_data or "Order Qty R1" in row_data:
            it.order_qty = _parse_decimal(row_data.get("Order Qty.") or row_data.get("Order Qty R1"))

        # Auto calculate order value
        if it.order_qty and it.rate:
            it.order_value = it.order_qty * it.rate

        # Supplier details (MD View)
        if "Supplier ID" in row_data:
            it.supplier_id = row_data["Supplier ID"]
        if "Supplier name" in row_data:
            it.supplier_name = row_data["Supplier name"]
        if "Process name" in row_data:
            it.process_name = row_data["Process name"]

    plan.source_filename = confirm_req.filename
    plan.modified_by = user_id
    plan.modified_at = datetime.now(timezone.utc)
    session.commit()

    return get_purchase_plan(session, period)  # type: ignore


def export_purchase_plan_excel(
    session: Session,
    planning_period: str,
    view_type: str = "NORMAL_VIEW",
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> bytes:
    """Generate Excel export in either Normal View (23 cols) or MD View (76 cols)."""
    plan = session.scalars(
        select(PurchasePlan).where(PurchasePlan.planning_period == planning_period)
    ).first()

    if not plan:
        raise ApplicationError("PLAN_NOT_FOUND", "Purchase plan not found for export.")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Purchase Plan"

    # Styling helpers
    header_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    band_fill = PatternFill(start_color="3E7CB1", end_color="3E7CB1", fill_type="solid")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    band_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=9)
    bold_font = Font(name="Segoe UI", size=9, bold=True)
    border_thin = Border(
        left=Side(style="thin", color="E0E0E0"),
        right=Side(style="thin", color="E0E0E0"),
        top=Side(style="thin", color="E0E0E0"),
        bottom=Side(style="thin", color="E0E0E0"),
    )

    items = plan.items
    if search:
        q = search.lower()
        items = [it for it in items if q in it.item_id.lower() or q in it.description.lower()]

    if view_type == "NORMAL_VIEW":
        # Row 1: Title
        ws.cell(1, 1, "KNL").font = Font(name="Segoe UI", size=14, bold=True, color="1B3A5C")
        ws.cell(1, 2, f"Consumable Purchase Plan vs Actual for the month of {plan.planning_period}").font = Font(name="Segoe UI", size=12, bold=True)

        # Row 2: Parameters
        ws.cell(2, 2, f"No. of MSL Days for Gas: {plan.msl_days_gas} | No. of MSL Days: {plan.msl_days_general} | Month Days: {plan.month_days} | Working Days: {plan.working_days}").font = data_font

        # Row 3: Column Headers
        headers = NORMAL_VIEW_HEADERS
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(3, col_idx, h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Row 4+: Data
        row_idx = 4
        for it in items:
            ws.cell(row_idx, 1, it.s_no).alignment = Alignment(horizontal="center")
            ws.cell(row_idx, 2, it.req_type or "PRODUCTION CONSUMABLES")
            ws.cell(row_idx, 3, it.item_id).font = bold_font
            ws.cell(row_idx, 4, it.description)
            ws.cell(row_idx, 5, it.unit).alignment = Alignment(horizontal="center")
            ws.cell(row_idx, 6, float(it.output_per_unit or 0))
            ws.cell(row_idx, 7, float(it.moq or 0))
            ws.cell(row_idx, 8, float(it.min_stock_level or 0))
            ws.cell(row_idx, 9, float(it.max_stock_level or 0))
            ws.cell(row_idx, 10, float(it.rate or 0))
            ws.cell(row_idx, 11, float(it.prev_opening_qty or 0))
            ws.cell(row_idx, 12, float(it.prev_receipt_qty or 0))
            ws.cell(row_idx, 13, float(it.prev_issue_qty or 0))
            ws.cell(row_idx, 14, float(it.prev_closing_qty or 0))
            ws.cell(row_idx, 15, float(it.prev_prd_qty or 0))
            ws.cell(row_idx, 16, float(it.sch_qty or 0))
            ws.cell(row_idx, 17, float(it.req_qty or 0))
            ws.cell(row_idx, 18, float(it.order_qty or 0)).font = bold_font
            ws.cell(row_idx, 19, float(it.order_value or 0)).font = bold_font
            ws.cell(row_idx, 20, float(it.pur_qty or 0))
            ws.cell(row_idx, 21, float(it.pur_value or 0))
            ws.cell(row_idx, 22, float(it.bal_pur_qty or 0))
            ws.cell(row_idx, 23, float(it.bal_pur_value or 0))

            for col in range(1, 24):
                ws.cell(row_idx, col).border = border_thin
            row_idx += 1

    else:
        # MD VIEW (76 Columns)
        ws.cell(1, 1, "KNL Consumables Requirement for the month of " + plan.planning_period).font = Font(name="Segoe UI", size=14, bold=True, color="1B3A5C")
        ws.cell(1, 8, f"Working days: {plan.working_days}").font = bold_font

        headers = MD_VIEW_HEADERS
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(2, col_idx, h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        row_idx = 3
        for it in items:
            ws.cell(row_idx, 1, it.supplier_id or "")
            ws.cell(row_idx, 2, it.supplier_name or "")
            ws.cell(row_idx, 3, it.item_id).font = bold_font
            ws.cell(row_idx, 4, it.category or "")
            ws.cell(row_idx, 5, it.type_of_material or "")
            ws.cell(row_idx, 6, it.s_no)
            ws.cell(row_idx, 7, it.description)
            ws.cell(row_idx, 8, it.part_no_saleable or "")
            ws.cell(row_idx, 9, it.saleable_part_name or "")
            ws.cell(row_idx, 10, it.used_part_no or "")
            ws.cell(row_idx, 11, it.process_name or "")
            ws.cell(row_idx, 12, it.thickness_gsm or "")
            ws.cell(row_idx, 13, float(it.no_of_process_per_part or 0))
            ws.cell(row_idx, 14, float(it.output_per_unit or 0))
            ws.cell(row_idx, 15, float(it.rate or 0))
            ws.cell(row_idx, 16, float(it.prev_opening_qty or 0))
            ws.cell(row_idx, 17, float(it.prev_opening_val or 0))
            ws.cell(row_idx, 18, float(it.prev_receipt_qty or 0))
            ws.cell(row_idx, 19, float(it.prev_issue_qty or 0))
            ws.cell(row_idx, 20, float(it.prev_closing_qty or 0))
            ws.cell(row_idx, 21, float(it.prev_closing_val or 0))
            ws.cell(row_idx, 22, float(it.rate or 0))
            ws.cell(row_idx, 23, float(it.min_stock_level or 0))
            ws.cell(row_idx, 24, float(it.max_stock_level or 0))
            ws.cell(row_idx, 25, float(it.moq or 0))
            ws.cell(row_idx, 26, it.lead_time_days or 0)
            ws.cell(row_idx, 27, float(it.sch_qty or 0))
            ws.cell(row_idx, 28, it.purchasing_unit or it.unit)
            ws.cell(row_idx, 29, float(it.sch_qty or 0))
            ws.cell(row_idx, 30, float(it.prev_closing_qty or 0))
            ws.cell(row_idx, 31, float(it.req_qty or 0))
            ws.cell(row_idx, 32, float(it.order_qty or 0)).font = bold_font
            ws.cell(row_idx, 33, float(it.order_value or 0)).font = bold_font
            ws.cell(row_idx, 34, float(it.receipt_qty or 0))
            ws.cell(row_idx, 35, float(it.receipt_value or 0))

            # R2 columns
            ws.cell(row_idx, 36, float(it.sch_qty_r2 or 0))
            ws.cell(row_idx, 37, float(it.sch_qty_r2 or 0))
            ws.cell(row_idx, 38, float(it.req_qty_r2 or 0))
            ws.cell(row_idx, 39, float(it.prev_closing_qty or 0))
            ws.cell(row_idx, 40, float(it.req_qty_r2 or 0))
            ws.cell(row_idx, 41, float(it.prev_issue_qty or 0))
            ws.cell(row_idx, 42, float(it.order_qty_r2 or 0))
            ws.cell(row_idx, 43, float(it.order_value_r2 or 0))
            ws.cell(row_idx, 44, float(it.receipt_qty_r2 or 0))
            ws.cell(row_idx, 45, float(it.receipt_val_r2 or 0))

            # Totals
            ws.cell(row_idx, 46, float((it.receipt_qty or 0) + (it.receipt_qty_r2 or 0)))
            ws.cell(row_idx, 47, float((it.receipt_value or 0) + (it.receipt_val_r2 or 0)))

            # Plant-wise allocations
            alloc = it.plant_allocations or {}
            ws.cell(row_idx, 48, float(alloc.get("p1", 0)))
            ws.cell(row_idx, 49, float(alloc.get("p2", 0)))
            ws.cell(row_idx, 50, float(alloc.get("p3", 0)))
            ws.cell(row_idx, 51, float(alloc.get("p4", 0)))
            ws.cell(row_idx, 52, float(alloc.get("p5", 0)))
            ws.cell(row_idx, 53, float(alloc.get("tool_room", 0)))
            ws.cell(row_idx, 54, float(alloc.get("quality", 0)))
            ws.cell(row_idx, 55, float(alloc.get("pmd", 0)))
            ws.cell(row_idx, 56, float(alloc.get("npd", 0)))
            ws.cell(row_idx, 57, float(alloc.get("hrd", 0)))
            ws.cell(row_idx, 58, float(alloc.get("accounts", 0)))
            ws.cell(row_idx, 59, float(alloc.get("admin", 0)))
            ws.cell(row_idx, 60, float(alloc.get("sales", 0)))
            ws.cell(row_idx, 61, float(alloc.get("req_by_users", 0)))
            ws.cell(row_idx, 62, float(alloc.get("total_value", 0)))

            # Consumption & Stock analysis
            analysis = it.consumption_analysis or {}
            ws.cell(row_idx, 63, float(analysis.get("avg_monthly_con", 0)))
            ws.cell(row_idx, 64, float(analysis.get("avg_daily_con", 0)))
            ws.cell(row_idx, 65, float(it.moq or 0))
            ws.cell(row_idx, 66, it.lead_time_days or 0)
            ws.cell(row_idx, 67, float(analysis.get("hold_days", 0)))
            ws.cell(row_idx, 68, float(it.min_stock_level or 0))
            ws.cell(row_idx, 69, float(it.max_stock_level or 0))
            ws.cell(row_idx, 70, float(analysis.get("lead_time_qty", 0)))
            ws.cell(row_idx, 71, float(analysis.get("reorder_level", 0)))
            ws.cell(row_idx, 72, float(analysis.get("cost_of_msl", 0)))
            ws.cell(row_idx, 73, float(analysis.get("reorder_level_formula", 0)))
            ws.cell(row_idx, 74, float(analysis.get("avg_daily_con", 0)))
            ws.cell(row_idx, 75, float(analysis.get("prev_plan_val", 0)))
            ws.cell(row_idx, 76, float(analysis.get("prev_actual_val", 0)))

            for col in range(1, len(headers) + 1):
                ws.cell(row_idx, col).border = border_thin
            row_idx += 1

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 16

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
