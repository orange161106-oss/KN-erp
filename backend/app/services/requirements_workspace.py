import io
from typing import Optional
from uuid import UUID

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.models.inventory_masters import Consumable
from app.models.production import Plant, Process
from app.schemas.requirements_workspace import (
    RequirementRecalculateResponse,
    RequirementWorkspaceRecord,
)


def calculate_workspace_requirements(
    session, plant_filter=None, consumable_filter=None, status_filter=None, search=None,
) -> list[RequirementWorkspaceRecord]:
    """Display persisted authoritative results; never calculate from workspace guesses.

    Each planning period uses its latest numeric canonical revision. Inventory,
    MSL and shortage fields require the projection/report service and are explicitly
    unavailable here rather than being recalculated with undated open orders.
    """
    from app.models.prd import PlanningVersion
    from app.models.requirements import CalculatedRequirement, RequirementCalculationError
    versions = session.scalars(select(PlanningVersion).order_by(
        PlanningVersion.planning_period, PlanningVersion.version_number.desc())).all()
    latest = {}
    for version in versions:
        latest.setdefault(version.planning_period, version)
    results = []
    for version in latest.values():
        requirements = session.scalars(select(CalculatedRequirement).where(
            CalculatedRequirement.planning_version_id == version.id)).all()
        errors = session.scalars(select(RequirementCalculationError).where(
            RequirementCalculationError.planning_version_id == version.id)).all()
        for row in requirements:
            material = session.get(Consumable, row.consumable_id)
            plant = session.get(Plant, row.plant_id)
            process = session.get(Process, row.process_id)
            results.append(RequirementWorkspaceRecord(
                id=str(row.id), plant=plant.name, process=process.name,
                consumable_code=material.code, description=material.name, unit=row.uom,
                required_qty=format(row.calculated_qty, '.4f'), stock_qty='Unavailable',
                shortage_qty='Unavailable', po_pending_qty='Unavailable', msl='Unavailable',
                status='Calculated', planning_period=version.planning_period,
                revision=version.revision_label,
                remarks='Calculated requirement; approval and dated projection must be reviewed separately.',
            ))
        for error in errors:
            plant = session.get(Plant, error.plant_id) if error.plant_id else None
            results.append(RequirementWorkspaceRecord(
                id=str(error.id), plant=plant.name if plant else 'Unresolved', process='Unresolved',
                consumable_code='', description=error.error_message, unit='', required_qty='Unavailable',
                stock_qty='Unavailable', shortage_qty='Unavailable', po_pending_qty='Unavailable',
                msl='Unavailable', status='Configuration required', remarks=error.error_code,
                planning_period=version.planning_period, revision=version.revision_label,
            ))
    def matches(record):
        for value, fields in ((plant_filter, [record.plant]),
                              (consumable_filter, [record.consumable_code, record.description]),
                              (status_filter, [record.status]),
                              (search, [record.plant, record.process, record.consumable_code, record.description, record.status])):
            if value and value.upper() != 'ALL' and not any(value.lower() in field.lower() for field in fields):
                return False
        return True
    return [record for record in results if matches(record)]

def recalculate_requirements(session) -> RequirementRecalculateResponse:
    records = calculate_workspace_requirements(session)
    critical = sum(1 for r in records if r.status == "Critical shortage")
    low = sum(1 for r in records if r.status == "Low")
    return RequirementRecalculateResponse(
        message=f"Authoritative calculation results refreshed. Found {len(records)} consumable requirements.",
        record_count=len(records),
        critical_shortages=critical,
        low_stock=low,
        records=records,
    )


def export_requirements_excel(
    session,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    record_ids: Optional[list[str]] = None,
) -> bytes:
    records = calculate_workspace_requirements(
        session,
        plant_filter=plant_filter,
        consumable_filter=consumable_filter,
        status_filter=status_filter,
        search=search,
    )
    if record_ids:
        records = [r for r in records if r.id in record_ids]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Consumable Requirements"

    header_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=11)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    headers = [
        "#",
        "Plant",
        "Process",
        "Consumable / Item ID",
        "Description",
        "Unit",
        "Required Qty",
        "Stock Qty",
        "Shortage Qty",
        "PO Pending Qty",
        "Status",
        "Remarks",
    ]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_num in (1, 6, 11) else "left", vertical="center")

    ws.row_dimensions[1].height = 24

    for r_idx, row in enumerate(records, start=1):
        row_data = [
            r_idx,
            row.plant,
            row.process,
            row.consumable_code,
            row.description,
            row.unit,
            row.required_qty,
            row.stock_qty,
            row.shortage_qty,
            row.po_pending_qty,
            row.status,
            row.remarks or "",
        ]
        ws.append(row_data)
        current_row = r_idx + 1
        ws.row_dimensions[current_row].height = 20
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.font = data_font
            cell.border = thin_border
            if col_num in (1, 6, 11):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_num in (7, 8, 9, 10):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0.0000"
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
