import calendar
from datetime import datetime, timezone
from decimal import Decimal
import io
from typing import Optional
from uuid import UUID

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.prd import PlanningVersion
from app.models.purchase_approval import PurchaseApproval
from app.models.requirements import MonthlyRequirementRecord
from app.models.stock_statements import (
    StockParameter,
    StockParameterBatch,
    StockStatementBatch,
    StockStatementLine,
)
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import SubmitPurchaseApprovalRequest
from app.schemas.purchase_workspace import (
    PurchaseSubmitResponse,
    PurchaseWorkspaceRecord,
    PurchaseWorkspaceResponse,
)
from app.services.purchase_approval import submit_purchase_approval
from app.services.requirements_workspace import get_monthly_plan_metadata
from app.services.stock_management_service import resolve_stock_parameter_for_item


def _q4(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _latest_version(session: Session, planning_period: str) -> PlanningVersion | None:
    return session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )


def _find_active_consumable(session: Session, code: str) -> tuple[Consumable | None, Unit | None]:
    consumable = session.scalar(
        select(Consumable).where(
            func.upper(Consumable.code) == code.strip().upper(),
            Consumable.is_active == True,  # noqa: E712
        )
    )
    unit = session.get(Unit, consumable.unit_id) if consumable else None
    return consumable, unit


def _supplier_options(session: Session, consumable_id) -> list[tuple[SupplierConsumable, Supplier]]:
    rows = session.execute(
        select(SupplierConsumable, Supplier)
        .join(Supplier, SupplierConsumable.supplier_id == Supplier.id)
        .where(
            SupplierConsumable.consumable_id == consumable_id,
            SupplierConsumable.is_active == True,  # noqa: E712
            Supplier.is_active == True,  # noqa: E712
        )
        .order_by(Supplier.code)
    ).all()
    return list(rows)


def _approval_for(
    session: Session,
    *,
    planning_version_id,
    consumable_id,
    supplier_id,
) -> PurchaseApproval | None:
    return session.scalar(
        select(PurchaseApproval)
        .where(
            PurchaseApproval.planning_version_id == planning_version_id,
            PurchaseApproval.consumable_id == consumable_id,
            PurchaseApproval.supplier_id == supplier_id,
        )
        .order_by(PurchaseApproval.created_at.desc())
        .limit(1)
    )


def list_purchase_workspace(
    session: Session,
    *,
    month: int,
    year: int,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
) -> PurchaseWorkspaceResponse:
    planning_period = f"{year:04d}-{month:02d}"
    meta = get_monthly_plan_metadata(session, month, year)
    version = _latest_version(session, planning_period)

    if not version:
        return PurchaseWorkspaceResponse(plan_metadata=meta, records=[])

    rows = session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ).all()

    # Look up previous month's stock statement and current month's stock parameters
    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year

    prev_statement_batch = session.scalar(
        select(StockStatementBatch).where(
            StockStatementBatch.statement_month == prev_month,
            StockStatementBatch.statement_year == prev_year,
            StockStatementBatch.status == "active",
        )
    )
    stmt_lines_map: dict[str, StockStatementLine] = {}
    if prev_statement_batch:
        lines = session.scalars(
            select(StockStatementLine).where(
                StockStatementLine.batch_id == prev_statement_batch.id,
                StockStatementLine.item_class == "CONSUMABLE",
            )
        ).all()
        for l in lines:
            stmt_lines_map[l.item_id.strip().upper()] = l

    current_param_batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == month,
            StockParameterBatch.year == year,
            StockParameterBatch.status == "active",
        )
    )
    params_by_item: dict[str, list[StockParameter]] = {}
    if current_param_batch:
        params = session.scalars(
            select(StockParameter)
            .where(StockParameter.batch_id == current_param_batch.id)
            .order_by(StockParameter.source_row)
        ).all()
        for p in params:
            params_by_item.setdefault(p.item_id.strip().upper(), []).append(p)

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        key = row.consumable_code.strip().upper() or row.consumable_name.strip().upper()
        bucket = grouped.setdefault(
            key,
            {
                "code": row.consumable_code.strip(),
                "name": row.consumable_name.strip(),
                "unit": row.unit,
                "required": Decimal("0"),
                "stock": Decimal("0"),
                "po_pending": Decimal("0"),
                "shortage": Decimal("0"),
                "count": 0,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
        )
        bucket["required"] = bucket["required"] + row.scheduled_consumable_qty  # type: ignore[operator]
        bucket["stock"] = bucket["stock"] + row.stock_qty  # type: ignore[operator]
        bucket["po_pending"] = bucket["po_pending"] + row.po_pending_qty  # type: ignore[operator]
        bucket["shortage"] = bucket["shortage"] + row.shortage_qty  # type: ignore[operator]
        bucket["count"] = int(bucket["count"]) + 1
        if row.updated_at:
            bucket["updated_at"] = row.updated_at

    records: list[PurchaseWorkspaceRecord] = []
    for key, bucket in grouped.items():
        code = str(bucket["code"])
        consumable, stock_unit = _find_active_consumable(session, code)
        suppliers = _supplier_options(session, consumable.id) if consumable else []
        supplier = suppliers[0][1] if suppliers else None
        shortage = _q4(bucket["shortage"])  # type: ignore[arg-type]
        recommended = shortage if shortage > Decimal("0") else Decimal("0.0000")
        approval = (
            _approval_for(
                session,
                planning_version_id=version.id,
                consumable_id=consumable.id,
                supplier_id=supplier.id,
            )
            if consumable and supplier
            else None
        )

        if not consumable:
            status = "MASTER_REQUIRED"
            remarks = "No active consumable master matches this requirement code."
        elif not supplier:
            status = "SUPPLIER_REQUIRED"
            remarks = "No active supplier mapping exists for this consumable."
        elif recommended <= Decimal("0"):
            status = "NO_PURCHASE_REQUIRED"
            remarks = "No positive shortage is available for approval submission."
        elif approval:
            status = "SUBMITTED"
            remarks = f"Existing approval queue item is {approval.status}."
        else:
            status = "READY_FOR_APPROVAL"
            remarks = "Ready to submit to the existing purchase approval queue."

        item_key = code.strip().upper()
        flags: list[str] = []
        if prev_statement_batch:
            if item_key in stmt_lines_map:
                stmt_line = stmt_lines_map[item_key]
                if stmt_line.closing_qty is not None:
                    effective_stock = stmt_line.closing_qty
                else:
                    effective_stock = _q4(bucket["stock"])
            else:
                effective_stock = _q4(bucket["stock"])
                flags.append(f"Not in {prev_month:02d}/{prev_year} statement")
        else:
            effective_stock = _q4(bucket["stock"])
            flags.append(f"No stock statement for {prev_month:02d}/{prev_year}")

        if not current_param_batch:
            flags.append(f"No stock parameters for {month:02d}/{year}")
        else:
            item_params = params_by_item.get(item_key, [])
            resolved_param, param_flag = resolve_stock_parameter_for_item(
                item_params,
                category=category,
            )
            if param_flag:
                flags.append(param_flag)
            elif resolved_param is not None:
                if (
                    recommended > Decimal("0")
                    and resolved_param.min_order_qty is not None
                    and recommended < resolved_param.min_order_qty
                ):
                    recommended = _q4(resolved_param.min_order_qty)
                flags.append(
                    f"Limits ({resolved_param.category or 'Default'}): "
                    f"Min={_q4(resolved_param.min_stock_level)}, "
                    f"Max={_q4(resolved_param.max_stock_level)}, "
                    f"MOQ={_q4(resolved_param.min_order_qty)}, "
                    f"Lead={resolved_param.lead_time_days if resolved_param.lead_time_days is not None else 0}d"
                )

        if flags:
            remarks = f"{remarks} [{'; '.join(flags)}]" if remarks else "; ".join(flags)

        record = PurchaseWorkspaceRecord(
            id=f"{version.id}:{key}",
            planning_period=planning_period,
            planning_month=month,
            planning_year=year,
            plan_id=str(version.id),
            revision=version.revision_label,
            consumable_id=consumable.id if consumable else None,
            consumable_code=code,
            consumable_name=str(bucket["name"]),
            supplier_id=supplier.id if supplier else None,
            supplier_code=supplier.code if supplier else None,
            supplier_name=supplier.name if supplier else None,
            unit=stock_unit.code if stock_unit else str(bucket["unit"]),
            required_qty=_q4(bucket["required"]),  # type: ignore[arg-type]
            stock_qty=_q4(effective_stock),
            po_pending_qty=_q4(bucket["po_pending"]),  # type: ignore[arg-type]
            shortage_qty=shortage,
            system_recommended_qty=recommended,
            approval_status=approval.status if approval else None,
            approval_id=approval.id if approval else None,
            status=status,
            remarks=remarks,
            source_row_count=int(bucket["count"]),
            created_at=bucket["created_at"],  # type: ignore[arg-type]
            updated_at=bucket["updated_at"],  # type: ignore[arg-type]
        )
        records.append(record)

    if search:
        q = search.lower()
        records = [
            r for r in records
            if q in r.consumable_code.lower()
            or q in r.consumable_name.lower()
            or (r.supplier_code and q in r.supplier_code.lower())
            or (r.supplier_name and q in r.supplier_name.lower())
        ]
    if status_filter:
        records = [r for r in records if r.status == status_filter]

    records.sort(key=lambda r: (r.status != "READY_FOR_APPROVAL", r.consumable_code))
    return PurchaseWorkspaceResponse(plan_metadata=meta, records=records)


def submit_purchase_workspace_records(
    session: Session,
    *,
    month: int,
    year: int,
    record_ids: list[str],
    reason: Optional[str],
    current_user: CurrentUser,
) -> PurchaseSubmitResponse:
    if not record_ids:
        raise ApplicationError("EMPTY_SUBMISSION", "Select at least one purchase recommendation.", 400)

    workspace = list_purchase_workspace(session, month=month, year=year)
    selected = [row for row in workspace.records if row.id in set(record_ids)]
    if not selected:
        raise ApplicationError("NO_MATCHING_RECORDS", "No selected purchase records were found.", 404)

    submitted = 0
    skipped = 0
    for row in selected:
        if (
            row.status != "READY_FOR_APPROVAL"
            or not row.consumable_id
            or not row.supplier_id
            or row.system_recommended_qty <= Decimal("0")
        ):
            skipped += 1
            continue

        submit_purchase_approval(
            session,
            SubmitPurchaseApprovalRequest(
                consumable_id=row.consumable_id,
                supplier_id=row.supplier_id,
                planning_version_id=UUID(row.plan_id) if row.plan_id else None,
                raw_calculated_qty=row.shortage_qty,
                system_recommended_qty=row.system_recommended_qty,
                uom=row.unit,
                reason=reason or "Submitted from monthly Purchase workspace.",
            ),
            current_user,
        )
        submitted += 1

    refreshed = list_purchase_workspace(session, month=month, year=year)
    return PurchaseSubmitResponse(
        message=f"Submitted {submitted} purchase recommendation(s) to approval queue.",
        submitted_count=submitted,
        skipped_count=skipped,
        records=refreshed.records,
        plan_metadata=refreshed.plan_metadata,
    )


def export_purchase_workspace_excel(
    session: Session,
    *,
    month: int,
    year: int,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    record_ids: Optional[list[str]] = None,
) -> bytes:
    workspace = list_purchase_workspace(
        session,
        month=month,
        year=year,
        search=search,
        status_filter=status_filter,
    )
    records = workspace.records
    if record_ids:
        ids = set(record_ids)
        records = [r for r in records if r.id in ids]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Purchase Recommendations"

    navy_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    steel_fill = PatternFill(start_color="2E5B88", end_color="2E5B88", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="1B3A5C")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    period_label = f"{calendar.month_name[month]} {year}"
    ws.cell(row=1, column=1, value="KNL PURCHASE RECOMMENDATIONS").font = title_font
    ws.cell(
        row=2,
        column=1,
        value=f"Planning Period: {period_label} | Revision: {workspace.plan_metadata.revision_label} | Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    )

    headers = [
        "Consumable Code",
        "Consumable Name",
        "Supplier Code",
        "Supplier Name",
        "Unit",
        "Required Qty",
        "Stock Qty",
        "PO Pending Qty",
        "Shortage Qty",
        "System Recommended Qty",
        "Status",
        "Approval Status",
        "Source Rows",
        "Remarks",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = navy_fill if col <= 5 else steel_fill
        cell.font = header_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, record in enumerate(records, start=5):
        values = [
            record.consumable_code,
            record.consumable_name,
            record.supplier_code or "",
            record.supplier_name or "",
            record.unit,
            record.required_qty,
            record.stock_qty,
            record.po_pending_qty,
            record.shortage_qty,
            record.system_recommended_qty,
            record.status,
            record.approval_status or "",
            record.source_row_count,
            record.remarks or "",
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.font = data_font
            cell.border = thin_border
            if col in (6, 7, 8, 9, 10):
                cell.number_format = "#,##0.0000"
                cell.alignment = Alignment(horizontal="right")

    for col in ws.columns:
        width = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(12, min(width + 3, 48))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
