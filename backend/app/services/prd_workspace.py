import io
import zipfile
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
            if row.status == "VALIDATED":
                raise ApplicationError("PRD_HISTORY_PROTECTED", "Import a new revision instead of deleting validated history.", 409)
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
            if existing.status == "VALIDATED":
                raise ApplicationError("PRD_HISTORY_PROTECTED", "Import a new revision instead of editing validated history.", 409)
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
    if row.status == "VALIDATED":
        raise ApplicationError("PRD_HISTORY_PROTECTED", "Validated revision history cannot be deleted.", 409)
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
    if any(r.status == "VALIDATED" for r in records_to_delete):
        raise ApplicationError("PRD_HISTORY_PROTECTED", "Validated revision history cannot be deleted.", 409)
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
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 200 * 1024 * 1024:
                    raise ApplicationError('SOURCE_TOO_LARGE', 'The expanded workbook exceeds the import limit.', 422)
            workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        except ApplicationError:
            raise
        except Exception:
            raise ApplicationError("INVALID_EXCEL", "Could not read Excel workbook.", 422) from None

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            if not hasattr(sheet, "iter_rows"):
                continue
            # Inspection only samples the beginning of each sheet. Imports validate
            # the full selected sheet separately with strict row/column limits.
            rows = list(sheet.iter_rows(max_row=20, max_col=min(sheet.max_column, 128), values_only=True))
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
                row_count=max(0, sheet.max_row - 1),
                column_count=sheet.max_column,
                headers=headers,
                sample_rows=sample,
            ))
        workbook.close()

    if not sheets_info:
        raise ApplicationError("NO_DATA_SHEETS", "Workbook contains no readable sheets.", 422)

    return PRDExcelInspectResponse(filename=filename, sheets=sheets_info)


def import_prd_excel(session, file_bytes, filename, sheet_name, actor, mode='APPEND',
                     reason='Excel PRD import', target_period=None, revision_label=None):
    from app.services.product_source import source_rows
    from app.services.prd_source import parse, revision
    from app.models.masters import Product
    from app.models.mappings import ProductPlant
    from app.models.production import Plant
    from app.models.prd import ImportBatch, PlanningVersion
    from app.services.prd import promote_batch_to_planning_version
    if mode != 'APPEND':
        raise ApplicationError('PRD_HISTORY_PROTECTED', 'Import a new revision instead of replacing revision history.', 409)
    rows = parse(source_rows(file_bytes, filename, sheet_name), target_period, revision_label)
    products = list(session.scalars(select(Product).where(Product.is_active.is_(True))))
    period, label = rows[0]['period'], rows[0]['revision']
    if session.scalar(select(PlanningVersion.id).where(PlanningVersion.planning_period == period,
                         PlanningVersion.version_number == revision(label))):
        raise ApplicationError('PRD_REVISION_EXISTS', 'This revision already exists. Keep its history and use a new revision for changes.', 409)
    staged, workspace = [], []
    seen = set()
    for row in rows:
        matches = [p for p in products if any(source and source in {p.code, p.item_id, p.part_number}
                   for source in (row['item_id'], row['part_number'], row['code']))]
        if len(matches) != 1:
            raise ApplicationError('PRODUCT_REVIEW_REQUIRED', f"Row {row['source_row_number']} needs one unambiguous active product master. Review it in Masters → Products.", 422)
        product = matches[0]
        if row['uom'] and row['uom'].casefold() != product.uom.casefold():
            raise ApplicationError('PRD_UNIT_MISMATCH', f"Product {product.code}: source production unit differs from its reviewed master.", 422)
        mappings = list(session.scalars(select(ProductPlant).where(ProductPlant.product_id == product.id,
                          ProductPlant.is_active.is_(True))))
        if row['plant']:
            mappings = [m for m in mappings if session.get(Plant, m.plant_id).name == row['plant']]
        elif len(mappings) > 1:
            mappings = [m for m in mappings if m.is_primary]
        if len(mappings) != 1 or not session.get(Plant, mappings[0].plant_id).is_active:
            raise ApplicationError('PLANT_MAPPING_REQUIRED', f"Product {product.code} needs one verified active plant mapping or an explicit source plant.", 422)
        plant = session.get(Plant, mappings[0].plant_id)
        if (product.id, plant.id) in seen:
            raise ApplicationError('DUPLICATE_PRD_ITEM', f"Product {product.code} occurs more than once for {plant.name}; review the source rows.", 422)
        seen.add((product.id, plant.id))
        staged.append({'product_code': product.code, 'product_id': str(product.id), 'plant_code': plant.name,
                       'planned_quantity': str(row['quantity']), 'uom': product.uom, 'target_period': period,
                       'source_row_number': row['source_row_number'], 'customer_id': None,
                       'source_item_id': row['item_id'], 'source_part_number': row['part_number']})
        workspace.append(PRDRecord(id=uuid4(), row_index=row['source_row_number'], plant=plant.name,
                          product_code=product.code, description=product.name, planned_quantity=row['quantity'],
                          uom=product.uom, target_period=period, planning_version=label, status='VALIDATED', created_by=actor))
    import hashlib
    batch = ImportBatch(filename=filename, file_size_bytes=len(file_bytes), uploaded_by=actor, status='VALIDATED',
                        row_count=len(staged), valid_row_count=len(staged), error_row_count=0, staged_data=staged)
    session.add(batch)
    session.add_all(workspace)
    session.flush()
    audit(session, actor, batch.id, 'IMPORT_VERIFIED_PRD', reason,
          {'sheet': sheet_name, 'filename': filename, 'sha256': hashlib.sha256(file_bytes).hexdigest(),
           'planning_period': period, 'revision': label, 'row_count': len(staged)}, entity='import_batches')
    promote_batch_to_planning_version(session, batch.id, actor, period, label)
    return PRDExcelImportResponse(sheet_name=sheet_name, imported_count=len(workspace),
                                 records=[to_prd_record_response(r) for r in workspace])

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

