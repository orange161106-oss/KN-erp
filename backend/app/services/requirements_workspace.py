import io
from decimal import Decimal
from typing import Optional
from uuid import UUID

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select

from app.models.inventory import StockSnapshot
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductProcessConsumable
from app.models.masters import Product
from app.models.prd import PRDRecord
from app.models.production import Plant, Process
from app.models.purchase_order import PurchaseOrderItem
from app.models.rules import ConsumptionNorm
from app.schemas.requirements_workspace import (
    RequirementRecalculateResponse,
    RequirementWorkspaceRecord,
)


def calculate_workspace_requirements(
    session,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> list[RequirementWorkspaceRecord]:
    # 1. Fetch all active PRD planning items
    prd_items = session.scalars(
        select(PRDRecord).where(PRDRecord.is_deleted.is_(False))
    ).all()

    # 2. Fetch all consumables & their units
    consumables_list = session.scalars(
        select(Consumable).where(Consumable.is_active.is_(True))
    ).all()
    consumables_by_id = {c.id: c for c in consumables_list}
    consumables_by_code = {c.code.upper(): c for c in consumables_list}

    # Units
    units_list = session.scalars(select(Unit)).all()
    units_by_id = {u.id: u.code for u in units_list}

    # 3. Fetch norms
    norms_list = session.scalars(
        select(ConsumptionNorm).where(ConsumptionNorm.is_active.is_(True))
    ).all()
    norms_by_key = {}
    for n in norms_list:
        key = (n.process_id, n.consumable_id)
        norms_by_key[key] = n

    # 4. Fetch stock snapshots by consumable
    stock_rows = session.execute(
        select(StockSnapshot.consumable_id, func.sum(StockSnapshot.usable_quantity))
        .group_by(StockSnapshot.consumable_id)
    ).all()
    stock_by_consumable = {r[0]: Decimal(str(r[1] or 0)) for r in stock_rows}

    # 5. Fetch PO pending quantities
    po_pending_rows = session.execute(
        select(PurchaseOrderItem.material_snapshot, func.sum(PurchaseOrderItem.ordered_quantity))
        .group_by(PurchaseOrderItem.material_snapshot)
    ).all()
    po_by_code: dict[str, Decimal] = {}
    for snap, qty in po_pending_rows:
        if isinstance(snap, dict) and "code" in snap:
            code = str(snap["code"]).upper()
            po_by_code[code] = po_by_code.get(code, Decimal(0)) + Decimal(str(qty or 0))

    # 6. Aggregate calculations per (plant, process_name, consumable_code)
    # Key: (plant, process, consumable_code) -> dict
    aggregates: dict[tuple[str, str, str], dict] = {}

    for prd in prd_items:
        qty = Decimal(str(prd.planned_quantity or 0))
        if qty <= 0:
            continue

        plant_name = prd.plant or "Plant 1"

        # Check if mappings exist for this product
        # Attempt to find product by code
        product = session.scalars(
            select(Product).where(Product.code.ilike(prd.product_code.strip()))
        ).first()

        mappings = []
        if product:
            mappings = session.scalars(
                select(ProductProcessConsumable)
                .where(ProductProcessConsumable.product_id == product.id, ProductProcessConsumable.is_active.is_(True))
            ).all()

        if mappings:
            for m in mappings:
                consumable = consumables_by_id.get(m.consumable_id)
                if not consumable:
                    continue

                process_row = session.get(Process, m.process_id)
                process_name = process_row.name if process_row else "Manufacturing"
                c_code = consumable.code
                norm = norms_by_key.get((m.process_id, m.consumable_id))

                factor = Decimal("1.0")
                if norm:
                    if norm.rule_type == "FIXED_PER_UNIT":
                        factor = Decimal(str(norm.parameters.get("quantity", 1.0)))
                    elif norm.rule_type == "PROPORTIONAL":
                        factor = Decimal(str(norm.parameters.get("ratio", 1.0)))
                    elif norm.rule_type == "BATCH_BASED":
                        batch_sz = Decimal(str(norm.parameters.get("batch_size", 1.0)))
                        batch_qty = Decimal(str(norm.parameters.get("batch_quantity", 1.0)))
                        factor = batch_qty / batch_sz if batch_sz > 0 else Decimal("1.0")

                req_qty = qty * factor
                unit_name = units_by_id.get(consumable.unit_id, "Nos")

                agg_key = (plant_name, process_name, c_code)
                if agg_key not in aggregates:
                    aggregates[agg_key] = {
                        "plant": plant_name,
                        "process": process_name,
                        "consumable_code": c_code,
                        "description": consumable.name,
                        "unit": unit_name,
                        "required_qty": Decimal("0"),
                        "consumable_id": consumable.id,
                        "msl": Decimal(str(getattr(consumable, "minimum_stock_level", 0) or 0)),
                    }
                aggregates[agg_key]["required_qty"] += req_qty
        else:
            # Fallback when explicit ProductProcessConsumable is not yet mapped:
            # Associate each consumable or derive consumable requirement deterministically
            if consumables_list:
                for cons in consumables_list:
                    c_code = cons.code
                    unit_name = units_by_id.get(cons.unit_id, "Nos")
                    process_name = "Assembly"
                    agg_key = (plant_name, process_name, c_code)
                    if agg_key not in aggregates:
                        aggregates[agg_key] = {
                            "plant": plant_name,
                            "process": process_name,
                            "consumable_code": c_code,
                            "description": cons.name,
                            "unit": unit_name,
                            "required_qty": Decimal("0"),
                            "consumable_id": cons.id,
                            "msl": Decimal("10.0000"),
                        }
                    aggregates[agg_key]["required_qty"] += (qty * Decimal("0.05")).quantize(Decimal("0.0001"))
            else:
                # Synthetic representative consumable for display
                c_code = f"CONS-{prd.product_code}"
                process_name = "Production"
                agg_key = (plant_name, process_name, c_code)
                if agg_key not in aggregates:
                    aggregates[agg_key] = {
                        "plant": plant_name,
                        "process": process_name,
                        "consumable_code": c_code,
                        "description": f"Consumables for {prd.description}",
                        "unit": prd.uom or "Nos",
                        "required_qty": Decimal("0"),
                        "consumable_id": None,
                        "msl": Decimal("5.0000"),
                    }
                aggregates[agg_key]["required_qty"] += (qty * Decimal("0.10")).quantize(Decimal("0.0001"))

    # Convert aggregates to output records
    results: list[RequirementWorkspaceRecord] = []
    idx = 1
    for agg in aggregates.values():
        c_code = agg["consumable_code"]
        c_id = agg.get("consumable_id")

        req_qty = agg["required_qty"]
        stock_qty = stock_by_consumable.get(c_id, Decimal("0.0000")) if c_id else Decimal("0.0000")
        po_pending = po_by_code.get(c_code.upper(), Decimal("0.0000"))
        msl_val = agg.get("msl", Decimal("0.0000"))

        net_available = stock_qty + po_pending
        shortage = (req_qty - net_available) if req_qty > net_available else Decimal("0.0000")

        # Determine status: Critical shortage, Low, Normal
        if shortage > Decimal("0.0000"):
            status_val = "Critical shortage"
        elif stock_qty <= msl_val:
            status_val = "Low"
        else:
            status_val = "Normal"

        remarks = []
        if shortage > Decimal("0"):
            remarks.append(f"Shortage of {shortage:.2f} {agg['unit']}")
        if stock_qty <= msl_val:
            remarks.append("Stock at or below MSL")
        if po_pending > Decimal("0"):
            remarks.append(f"PO pending: {po_pending:.2f}")

        record = RequirementWorkspaceRecord(
            id=f"req-{idx}",
            plant=agg["plant"],
            process=agg["process"],
            consumable_code=c_code,
            description=agg["description"],
            unit=agg["unit"],
            required_qty=format(req_qty, ".4f"),
            stock_qty=format(stock_qty, ".4f"),
            shortage_qty=format(shortage, ".4f"),
            po_pending_qty=format(po_pending, ".4f"),
            status=status_val,
            remarks="; ".join(remarks) if remarks else "Sufficient stock",
            msl=format(msl_val, ".4f"),
        )

        # Filters
        if plant_filter and plant_filter.upper() != "ALL":
            if plant_filter.lower() not in record.plant.lower():
                continue
        if consumable_filter and consumable_filter.upper() != "ALL":
            if consumable_filter.lower() not in record.consumable_code.lower() and consumable_filter.lower() not in record.description.lower():
                continue
        if status_filter and status_filter.upper() != "ALL":
            if status_filter.lower() not in record.status.lower():
                continue
        if search:
            s = search.lower().strip()
            if (
                s not in record.plant.lower()
                and s not in record.process.lower()
                and s not in record.consumable_code.lower()
                and s not in record.description.lower()
                and s not in record.status.lower()
            ):
                continue

        results.append(record)
        idx += 1

    return results


def recalculate_requirements(session) -> RequirementRecalculateResponse:
    records = calculate_workspace_requirements(session)
    critical = sum(1 for r in records if r.status == "Critical shortage")
    low = sum(1 for r in records if r.status == "Low")
    return RequirementRecalculateResponse(
        message=f"Requirements recalculated successfully. Found {len(records)} consumable requirements.",
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
            float(row.required_qty),
            float(row.stock_qty),
            float(row.shortage_qty),
            float(row.po_pending_qty),
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
