import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID, uuid4

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select, update

from app.core.errors import ApplicationError
from app.models.prd import PRDRecord
from app.schemas.prd_workspace import (
    PRDExcelImportResponse,
    PRDExcelInspectResponse,
    PRDExcelSheetInspectInfo,
    PRDWorkspaceRecordResponse,
    PRDWorkspaceSaveRequest,
    PRDWorkspaceSaveResponse,
)
from app.services.purchase_order import audit


def to_prd_record_response(row: PRDRecord) -> PRDWorkspaceRecordResponse:
    return PRDWorkspaceRecordResponse(
        id=row.id,
        row_index=row.row_index,
        plant=row.plant,
        customer=row.customer,
        product_code=row.product_code,
        description=row.description,
        planned_quantity=format(row.planned_quantity, ".4f") if row.planned_quantity is not None else "0.0000",
        uom=row.uom or "Nos",
        target_period=row.target_period,
        planning_version=row.planning_version or "V1",
        status=row.status or "SAVED",
        remarks=row.remarks,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_prd_records(
    session,
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> list[PRDWorkspaceRecordResponse]:
    query = select(PRDRecord).where(PRDRecord.is_deleted.is_(False))

    if plant and plant.upper() != "ALL":
        query = query.where(PRDRecord.plant.ilike(f"%{plant.strip()}%"))
    if target_period and target_period.upper() != "ALL":
        query = query.where(PRDRecord.target_period == target_period.strip())
    if planning_version and planning_version.upper() != "ALL":
        query = query.where(PRDRecord.planning_version == planning_version.strip())
    if status and status.upper() != "ALL":
        query = query.where(PRDRecord.status == status.upper())

    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            or_(
                PRDRecord.product_code.ilike(s),
                PRDRecord.description.ilike(s),
                PRDRecord.plant.ilike(s),
                PRDRecord.customer.ilike(s),
                PRDRecord.target_period.ilike(s),
                PRDRecord.planning_version.ilike(s),
                PRDRecord.remarks.ilike(s),
            )
        )

    rows = session.scalars(
        query.order_by(PRDRecord.row_index.asc().nulls_last(), PRDRecord.created_at.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [to_prd_record_response(r) for r in rows]


def save_prd_records(
    session,
    data: PRDWorkspaceSaveRequest,
    actor: UUID,
) -> PRDWorkspaceSaveResponse:
    saved_records = []

    # Process deletions
    for del_id in data.deleted_ids:
        row = session.get(PRDRecord, del_id)
        if row and not row.is_deleted:
            row.is_deleted = True
            row.updated_at = datetime.now(timezone.utc)
            audit(
                session, actor, row.id, "DELETE_ROW", data.reason,
                {"id": str(row.id), "product_code": row.product_code},
                old={"status": row.status, "is_deleted": False},
                entity="prd_records"
            )

    # Process additions / updates
    for item in data.records:
        try:
            qty = Decimal(str(item.planned_quantity).strip())
            if qty < 0:
                raise ValueError("Quantity must be non-negative")
        except (InvalidOperation, ValueError):
            raise ApplicationError(
                "INVALID_QUANTITY",
                f"Invalid planned quantity '{item.planned_quantity}' for part {item.product_code}.",
                422,
            )

        existing = session.get(PRDRecord, item.id) if item.id else None
        if existing and not existing.is_deleted:
            old_vals = {
                "product_code": existing.product_code,
                "plant": existing.plant,
                "planned_quantity": str(existing.planned_quantity),
                "status": existing.status,
            }
            existing.plant = item.plant.strip()
            existing.customer = item.customer.strip() if item.customer else None
            existing.product_code = item.product_code.strip()
            existing.description = item.description.strip()
            existing.planned_quantity = qty
            existing.uom = item.uom.strip() or "Nos"
            existing.target_period = item.target_period.strip()
            existing.planning_version = item.planning_version.strip() or "V1"
            existing.status = item.status or "SAVED"
            existing.remarks = item.remarks
            existing.row_index = item.row_index
            existing.updated_at = datetime.now(timezone.utc)
            saved_records.append(existing)
            audit(
                session, actor, existing.id, "UPDATE_ROW", data.reason,
                {"id": str(existing.id), "product_code": item.product_code, "planned_quantity": str(qty)},
                old=old_vals, entity="prd_records"
            )
        else:
            new_row = PRDRecord(
                id=item.id or uuid4(),
                row_index=item.row_index,
                plant=item.plant.strip(),
                customer=item.customer.strip() if item.customer else None,
                product_code=item.product_code.strip(),
                description=item.description.strip(),
                planned_quantity=qty,
                uom=item.uom.strip() or "Nos",
                target_period=item.target_period.strip(),
                planning_version=item.planning_version.strip() or "V1",
                status="SAVED",
                remarks=item.remarks,
                created_by=actor,
            )
            session.add(new_row)
            saved_records.append(new_row)
            audit(
                session, actor, new_row.id, "CREATE_ROW", data.reason,
                {"id": str(new_row.id), "product_code": item.product_code, "planned_quantity": str(qty)},
                entity="prd_records"
            )

    session.commit()
    return PRDWorkspaceSaveResponse(
        saved_count=len(saved_records),
        deleted_count=len(data.deleted_ids),
        records=[to_prd_record_response(r) for r in saved_records],
    )


def delete_prd_record(session, identity: UUID, actor: UUID, reason: str = "Row deleted") -> None:
    row = session.get(PRDRecord, identity)
    if not row or row.is_deleted:
        raise ApplicationError("RECORD_NOT_FOUND", "PRD planning record not found.", 404)
    row.is_deleted = True
    row.updated_at = datetime.now(timezone.utc)
    audit(
        session, actor, row.id, "DELETE_ROW", reason,
        {"id": str(row.id), "product_code": row.product_code},
        old={"is_deleted": False}, entity="prd_records"
    )
    session.commit()


def bulk_delete_prd_records(
    session,
    ids: list[UUID] | None = None,
    delete_all_matching: bool = False,
    search: str | None = None,
    plant: str | None = None,
    target_period: str | None = None,
    planning_version: str | None = None,
    status: str | None = None,
    actor: UUID | None = None,
    reason: str = "Bulk delete PRD records",
) -> int:
    query = select(PRDRecord).where(PRDRecord.is_deleted.is_(False))
    if delete_all_matching:
        if plant and plant.upper() != "ALL":
            query = query.where(PRDRecord.plant.ilike(f"%{plant.strip()}%"))
        if target_period and target_period.upper() != "ALL":
            query = query.where(PRDRecord.target_period == target_period.strip())
        if planning_version and planning_version.upper() != "ALL":
            query = query.where(PRDRecord.planning_version == planning_version.strip())
        if status and status.upper() != "ALL":
            query = query.where(PRDRecord.status == status.upper())
        if search and search.strip():
            s = f"%{search.strip()}%"
            query = query.where(
                or_(
                    PRDRecord.product_code.ilike(s),
                    PRDRecord.description.ilike(s),
                    PRDRecord.plant.ilike(s),
                    PRDRecord.customer.ilike(s),
                    PRDRecord.target_period.ilike(s),
                    PRDRecord.planning_version.ilike(s),
                    PRDRecord.remarks.ilike(s),
                )
            )
    elif ids:
        query = query.where(PRDRecord.id.in_(ids))
    else:
        return 0

    records_to_delete = session.scalars(query).all()
    count = len(records_to_delete)
    if count == 0:
        return 0

    target_ids = [r.id for r in records_to_delete]
    session.execute(
        update(PRDRecord)
        .where(PRDRecord.id.in_(target_ids))
        .values(is_deleted=True, updated_at=datetime.now(timezone.utc))
    )

    if actor:
        audit(
            session, actor, uuid4(), "BULK_DELETE_ROWS", reason,
            {"deleted_count": count, "deleted_ids": [str(i) for i in target_ids[:50]]},
            entity="prd_records"
        )

    session.commit()
    return count


def inspect_prd_excel(file_bytes: bytes, filename: str) -> PRDExcelInspectResponse:
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "The uploaded file is empty.", 422)

    sheets_info = []
    if filename.lower().endswith(".csv"):
        import csv
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            csv_rows = list(csv.reader(io.StringIO(text)))
        except Exception as exc:
            raise ApplicationError("INVALID_CSV", f"Could not read CSV file: {str(exc)}", 422)

        header_row = [str(c).strip() for c in csv_rows[0]] if csv_rows else []
        data_rows = csv_rows[1:] if len(csv_rows) > 1 else []
        sample = []
        for d_row in data_rows[:5]:
            row_dict = {}
            for idx, h in enumerate(header_row):
                val = d_row[idx] if idx < len(d_row) else ""
                row_dict[h] = str(val) if val is not None else ""
            sample.append(row_dict)

        sheets_info.append(PRDExcelSheetInspectInfo(
            name="Sheet1",
            row_count=len(data_rows),
            column_count=len(header_row),
            headers=header_row,
            sample_rows=sample,
        ))
    else:
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        except Exception:
            try:
                workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            except Exception as exc:
                raise ApplicationError("INVALID_EXCEL", f"Could not read Excel file: {str(exc)}", 422)

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            if not hasattr(sheet, "iter_rows"):
                continue
            rows = list(sheet.iter_rows(values_only=True))
            header_row = None
            data_rows = []
            for r in rows:
                if any(c is not None and str(c).strip() != "" for c in r):
                    if header_row is None:
                        header_row = [str(c).strip() if c is not None else f"Col_{i+1}" for i, c in enumerate(r)]
                    else:
                        data_rows.append(r)

            headers = header_row or []
            sample = []
            for d_row in data_rows[:5]:
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = d_row[idx] if idx < len(d_row) else ""
                    row_dict[h] = str(val) if val is not None else ""
                sample.append(row_dict)

            sheets_info.append(PRDExcelSheetInspectInfo(
                name=sheet_name,
                row_count=len(data_rows),
                column_count=len(headers),
                headers=headers,
                sample_rows=sample,
            ))

    if not sheets_info:
        raise ApplicationError("NO_DATA_SHEETS", "Workbook contains no readable sheets.", 422)

    return PRDExcelInspectResponse(filename=filename, sheets=sheets_info)


def import_prd_excel(
    session,
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    actor: UUID,
    mode: str = "APPEND",
    reason: str = "Excel sheet import",
) -> PRDExcelImportResponse:
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "The uploaded file is empty.", 422)

    if filename.lower().endswith(".csv"):
        import csv
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            rows = list(csv.reader(io.StringIO(text)))
        except Exception as exc:
            raise ApplicationError("INVALID_CSV", f"Could not read CSV file: {str(exc)}", 422)
    else:
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        except Exception:
            workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)

        if sheet_name not in workbook.sheetnames:
            raise ApplicationError("SHEET_NOT_FOUND", f"Sheet '{sheet_name}' not found.", 404)
        sheet = workbook[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))

    non_empty_rows = [r for r in rows if any(c is not None and str(c).strip() != "" for c in r)]
    if not non_empty_rows:
        raise ApplicationError("EMPTY_SHEET", f"Sheet '{sheet_name}' has no data rows.", 422)

    header_idx_map: dict[str, int] = {}
    best_header_idx = None
    best_matches = 0

    for r_idx, r in enumerate(non_empty_rows[:10]):
        temp_map: dict[str, int] = {}
        for idx, cell in enumerate(r):
            if cell is None:
                continue
            key = str(cell).strip().lower().replace("_", " ").replace("-", " ")
            if any(w in key for w in ["part description", "product description", "description", "item description"]):
                temp_map.setdefault("description", idx)
            elif any(w in key for w in ["plant code", "plant name", "plant", "unit location"]):
                temp_map.setdefault("plant", idx)
            elif any(w in key for w in ["customer name", "customer", "client"]):
                temp_map.setdefault("customer", idx)
            elif any(w in key for w in ["part number", "part no", "product code", "product no", "part #", "item code"]):
                temp_map.setdefault("product_code", idx)
            elif any(w in key for w in ["plan qty", "production plan qty", "planned qty", "plan quantity", "quantity", "qty"]):
                temp_map.setdefault("planned_quantity", idx)
            elif any(w in key for w in ["month/date", "month", "target period", "period", "planning month", "date"]):
                temp_map.setdefault("target_period", idx)
            elif any(w in key for w in ["planning version", "version", "rev", "revision"]):
                temp_map.setdefault("planning_version", idx)
            elif any(w in key for w in ["uom", "unit"]):
                temp_map.setdefault("uom", idx)
            elif any(w in key for w in ["remarks", "remark", "notes", "comments"]):
                temp_map.setdefault("remarks", idx)

        if len(temp_map) > best_matches:
            best_matches = len(temp_map)
            best_header_idx = r_idx
            header_idx_map = temp_map

    if best_header_idx is None:
        best_header_idx = 0
        header_idx_map = {
            "plant": 0,
            "customer": 1,
            "product_code": 2,
            "description": 3,
            "planned_quantity": 4,
            "target_period": 5,
        }

    data_rows = non_empty_rows[best_header_idx + 1:]
    if not data_rows:
        data_rows = non_empty_rows

    if mode == "REPLACE":
        active = session.scalars(select(PRDRecord).where(PRDRecord.is_deleted.is_(False))).all()
        for r in active:
            r.is_deleted = True

    imported_rows: list[PRDRecord] = []
    base_idx = session.scalar(select(func.coalesce(func.max(PRDRecord.row_index), 0)).where(PRDRecord.is_deleted.is_(False))) or 0

    for i, row in enumerate(data_rows, start=1):
        if not any(c is not None and str(c).strip() != "" for c in row):
            continue

        plant_val = str(row[header_idx_map["plant"]]).strip() if "plant" in header_idx_map and header_idx_map["plant"] < len(row) and row[header_idx_map["plant"]] is not None else "Plant 1"
        cust_val = str(row[header_idx_map["customer"]]).strip() if "customer" in header_idx_map and header_idx_map["customer"] < len(row) and row[header_idx_map["customer"]] is not None else None
        prod_val = str(row[header_idx_map["product_code"]]).strip() if "product_code" in header_idx_map and header_idx_map["product_code"] < len(row) and row[header_idx_map["product_code"]] is not None else f"PART-{i}"
        raw_desc = str(row[header_idx_map["description"]]).strip() if "description" in header_idx_map and header_idx_map["description"] < len(row) and row[header_idx_map["description"]] is not None else ""
        desc_val = raw_desc if raw_desc else f"{prod_val} Product"

        raw_qty = row[header_idx_map["planned_quantity"]] if "planned_quantity" in header_idx_map and header_idx_map["planned_quantity"] < len(row) else 0
        try:
            qty_val = Decimal(str(raw_qty).strip())
        except (InvalidOperation, ValueError, TypeError):
            qty_val = Decimal("0")

        uom_val = str(row[header_idx_map["uom"]]).strip() if "uom" in header_idx_map and header_idx_map["uom"] < len(row) and row[header_idx_map["uom"]] is not None else "Nos"
        now_period = datetime.now().strftime("%Y-%m")
        period_val = str(row[header_idx_map["target_period"]]).strip() if "target_period" in header_idx_map and header_idx_map["target_period"] < len(row) and row[header_idx_map["target_period"]] is not None else now_period
        ver_val = str(row[header_idx_map["planning_version"]]).strip() if "planning_version" in header_idx_map and header_idx_map["planning_version"] < len(row) and row[header_idx_map["planning_version"]] is not None else "V1"
        rem_val = str(row[header_idx_map["remarks"]]).strip() if "remarks" in header_idx_map and header_idx_map["remarks"] < len(row) and row[header_idx_map["remarks"]] is not None else None

        rec = PRDRecord(
            id=uuid4(),
            row_index=base_idx + i,
            plant=plant_val,
            customer=cust_val,
            product_code=prod_val,
            description=desc_val,
            planned_quantity=qty_val,
            uom=uom_val,
            target_period=period_val,
            planning_version=ver_val,
            status="SAVED",
            remarks=rem_val,
            created_by=actor,
        )
        session.add(rec)
        imported_rows.append(rec)

    audit(
        session, actor, uuid4(), "IMPORT_EXCEL_SHEET", reason,
        {"sheet_name": sheet_name, "filename": filename, "imported_count": len(imported_rows)},
        entity="prd_records"
    )

    session.commit()
    return PRDExcelImportResponse(
        sheet_name=sheet_name,
        imported_count=len(imported_rows),
        records=[to_prd_record_response(r) for r in imported_rows],
    )


def export_prd_excel(
    session,
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    record_ids: Optional[list[UUID]] = None,
) -> bytes:
    query = select(PRDRecord).where(PRDRecord.is_deleted.is_(False))
    if record_ids:
        query = query.where(PRDRecord.id.in_(record_ids))
    else:
        if plant and plant.upper() != "ALL":
            query = query.where(PRDRecord.plant.ilike(f"%{plant.strip()}%"))
        if target_period and target_period.upper() != "ALL":
            query = query.where(PRDRecord.target_period == target_period.strip())
        if planning_version and planning_version.upper() != "ALL":
            query = query.where(PRDRecord.planning_version == planning_version.strip())
        if status and status.upper() != "ALL":
            query = query.where(PRDRecord.status == status.upper())
        if search:
            s = f"%{search.strip()}%"
            query = query.where(
                or_(
                    PRDRecord.product_code.ilike(s),
                    PRDRecord.description.ilike(s),
                    PRDRecord.plant.ilike(s),
                    PRDRecord.customer.ilike(s),
                    PRDRecord.target_period.ilike(s),
                    PRDRecord.planning_version.ilike(s),
                    PRDRecord.remarks.ilike(s),
                )
            )

    rows = session.scalars(
        query.order_by(PRDRecord.row_index.asc().nulls_last(), PRDRecord.created_at.asc())
    ).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PRD Planning"

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
        "Customer",
        "Product/Part No.",
        "Description",
        "Production Plan Qty",
        "Unit",
        "Month/Date",
        "Planning Version",
        "Status",
        "Remarks",
    ]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_num in (1, 6, 7, 8, 9, 10) else "left", vertical="center")

    ws.row_dimensions[1].height = 24

    for r_idx, row in enumerate(rows, start=1):
        qty_val = float(row.planned_quantity) if row.planned_quantity is not None else 0.0
        row_data = [
            row.row_index or r_idx,
            row.plant,
            row.customer or "",
            row.product_code,
            row.description,
            qty_val,
            row.uom,
            row.target_period,
            row.planning_version,
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
            if col_num in (1, 7, 8, 9, 10):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_num == 6:
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

