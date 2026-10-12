import hashlib
import io
import time
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID, uuid4

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.mappings import ProductPlant
from app.models.masters import Customer, CustomerAlias, Product
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderHeader, PRDOrderItem, PRDRecord
from app.models.production import Plant
from app.schemas.prd_workspace import (
    PRDExcelImportResponse,
    PRDExcelInspectResponse,
    PRDExcelSheetInspectInfo,
    PRDWorkspaceRecordResponse,
    PRDWorkspaceSaveRequest,
    PRDWorkspaceSaveResponse,
    SalesScheduleBlockInfo,
    SalesScheduleGrandTotal,
    SalesScheduleImportPreviewResponse,
    SalesScheduleRevisionInfo,
)
from app.services.prd import promote_batch_to_planning_version
from app.services.purchase_order import audit
from app.services.sales_schedule_parser import (
    normalize_alias,
    parse_sales_schedule_data,
    read_workbook_rows,
    seed_default_customers_and_aliases,
)

# In-memory storage for staging uploaded files between preview and confirmation
_STAGED_FILES: dict[str, tuple[bytes, str, float]] = {}


def _cleanup_stale_staged_files() -> None:
    now = time.time()
    stale_keys = [k for k, (_, _, t) in _STAGED_FILES.items() if now - t > 3600]
    for k in stale_keys:
        _STAGED_FILES.pop(k, None)


def to_prd_record_response(row: PRDRecord) -> PRDWorkspaceRecordResponse:
    return PRDWorkspaceRecordResponse(
        id=row.id,
        row_index=row.row_index,
        plant=row.plant,
        customer=row.customer,
        customer_id=row.customer_id,
        customer_code=row.customer_code,
        customer_group=row.customer_group,
        product_code=row.product_code,
        description=row.description,
        planned_quantity=format(row.planned_quantity, ".4f") if row.planned_quantity is not None else "0.0000",
        uom=row.uom or "Nos",
        target_period=row.target_period,
        planning_version=row.planning_version or "V1",
        revision=row.revision or row.planning_version or "R0",
        schedule_given_on=row.schedule_given_on,
        section_type=row.section_type or "STANDARD",
        status=row.status or "SAVED",
        remarks=row.remarks,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_prd_records(
    session: Session,
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    customer: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> list[PRDWorkspaceRecordResponse]:
    query = select(PRDRecord).where(PRDRecord.is_deleted.is_(False))

    if plant and plant.upper() != "ALL":
        query = query.where(PRDRecord.plant.ilike(f"%{plant.strip()}%"))
    if target_period and target_period.upper() != "ALL":
        query = query.where(PRDRecord.target_period == target_period.strip())
    if planning_version and planning_version.upper() != "ALL":
        query = query.where(
            or_(
                PRDRecord.planning_version == planning_version.strip(),
                PRDRecord.revision == planning_version.strip(),
            )
        )
    if status and status.upper() != "ALL":
        query = query.where(PRDRecord.status == status.upper())
    if customer and customer.upper() != "ALL":
        query = query.where(
            or_(
                PRDRecord.customer.ilike(f"%{customer.strip()}%"),
                PRDRecord.customer_code.ilike(f"%{customer.strip()}%"),
            )
        )

    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            or_(
                PRDRecord.product_code.ilike(s),
                PRDRecord.description.ilike(s),
                PRDRecord.plant.ilike(s),
                PRDRecord.customer.ilike(s),
                PRDRecord.customer_code.ilike(s),
                PRDRecord.customer_group.ilike(s),
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
    session: Session,
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
            existing.customer_id = item.customer_id
            existing.customer_code = item.customer_code
            existing.customer_group = item.customer_group
            existing.product_code = item.product_code.strip()
            existing.description = item.description.strip()
            existing.planned_quantity = qty
            existing.uom = item.uom.strip() or "Nos"
            existing.target_period = item.target_period.strip()
            existing.planning_version = item.planning_version.strip() or "V1"
            existing.revision = item.revision or item.planning_version or "R0"
            existing.section_type = item.section_type or "STANDARD"
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
                customer_id=item.customer_id,
                customer_code=item.customer_code,
                customer_group=item.customer_group,
                product_code=item.product_code.strip(),
                description=item.description.strip(),
                planned_quantity=qty,
                uom=item.uom.strip() or "Nos",
                target_period=item.target_period.strip(),
                planning_version=item.planning_version.strip() or "V1",
                revision=item.revision or item.planning_version or "R0",
                section_type=item.section_type or "STANDARD",
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


def delete_prd_record(session: Session, identity: UUID, actor: UUID, reason: str = "Row deleted") -> None:
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
    session: Session,
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


# ---------------------------------------------------------------------------
# Sales Schedule Multi-Step Preview & Confirmation
# ---------------------------------------------------------------------------

def preview_sales_schedule_upload(
    session: Session,
    file_bytes: bytes,
    filename: str,
    sheet_name: Optional[str] = None,
    target_period: Optional[str] = None,
    revision_label: Optional[str] = None,
) -> SalesScheduleImportPreviewResponse:
    """Parse sales schedule workbook and return interactive inspection results."""
    _cleanup_stale_staged_files()

    # Get available sheets
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception as exc:
        raise ApplicationError("INVALID_EXCEL", f"Could not open workbook: {str(exc)}", 422)

    chosen_sheet, rows = read_workbook_rows(file_bytes, filename, sheet_name)

    parse_result = parse_sales_schedule_data(
        rows=rows,
        session=session,
        target_period=target_period,
        revision_label=revision_label,
    )

    file_token = str(uuid4())
    _STAGED_FILES[file_token] = (file_bytes, filename, time.time())

    return SalesScheduleImportPreviewResponse(
        filename=filename,
        sheet_name=chosen_sheet,
        sheet_names=sheet_names,
        header_row_index=parse_result["header_row_index"],
        available_revisions=[SalesScheduleRevisionInfo(**r) for r in parse_result["available_revisions"]],
        active_revisions=[SalesScheduleRevisionInfo(**r) for r in parse_result["active_revisions"]],
        blocks=[SalesScheduleBlockInfo(**b) for b in parse_result["blocks"]],
        unmapped_aliases=parse_result["unmapped_aliases"],
        grand_total=SalesScheduleGrandTotal(**parse_result["grand_total"]),
        total_part_rows=parse_result["total_part_rows"],
        sample_rows=parse_result["sample_rows"],
        can_confirm=parse_result["can_confirm"],
        warnings=parse_result["warnings"],
        errors=parse_result["errors"],
        file_token=file_token,
    )


def confirm_sales_schedule_import(
    session: Session,
    file_token: str,
    sheet_name: str,
    target_period: Optional[str],
    revision_label: Optional[str],
    plant_code: Optional[str],
    actor: UUID,
    alias_mappings: Optional[dict[str, UUID]] = None,
    mode: str = "APPEND",
    reason: str = "Confirmed KNL sales schedule import",
) -> PRDExcelImportResponse:
    """Confirm and atomically save the verified sales schedule into database."""
    _cleanup_stale_staged_files()

    staged_tuple = _STAGED_FILES.get(file_token)
    if not staged_tuple:
        raise ApplicationError("EXPIRED_TOKEN", "Staged file session expired. Please re-upload.", 422)

    file_bytes, filename, _ = staged_tuple

    # 1. Process inline alias mappings if user supplied them in modal
    if alias_mappings:
        for alias_text, cust_id in alias_mappings.items():
            cust = session.get(Customer, cust_id)
            if cust and cust.is_active:
                norm = normalize_alias(alias_text)
                existing = session.scalar(select(CustomerAlias).where(CustomerAlias.normalized_alias == norm))
                if existing:
                    existing.customer_id = cust.id
                    existing.alias_text = alias_text.strip()
                    existing.is_active = True
                else:
                    session.add(
                        CustomerAlias(
                            customer_id=cust.id,
                            alias_text=alias_text.strip(),
                            normalized_alias=norm,
                            is_active=True,
                        )
                    )
        session.flush()

    # 2. Re-parse with newly committed aliases
    chosen_sheet, rows = read_workbook_rows(file_bytes, filename, sheet_name)
    parse_result = parse_sales_schedule_data(
        rows=rows,
        session=session,
        target_period=target_period,
        revision_label=revision_label,
    )

    if parse_result["unmapped_aliases"]:
        raise ApplicationError(
            "UNMAPPED_ALIASES",
            f"Cannot import with unmapped company headings: {', '.join(parse_result['unmapped_aliases'])}. Map them first.",
            422,
        )

    all_flat_rows = parse_result["_all_flat_rows"]
    if not all_flat_rows:
        raise ApplicationError("EMPTY_DATA", "No valid parts found to import.", 422)

    # 3. Determine target period & revision
    period = all_flat_rows[0]["target_period"]
    rev_label = all_flat_rows[0]["revision"]
    rev_number = int(rev_label[1:]) if rev_label.startswith("R") and rev_label[1:].isdigit() else 0

    # Ensure revision doesn't collide
    existing_version = session.scalar(
        select(PlanningVersion).where(
            PlanningVersion.planning_period == period,
            PlanningVersion.version_number == rev_number,
        )
    )
    if existing_version and mode == "APPEND":
        raise ApplicationError(
            "PRD_REVISION_EXISTS",
            f"Revision {rev_label} for {period} already exists. Increment revision (e.g. R1) to preserve audit history.",
            409,
        )

    # 4. Ensure plant exists
    effective_plant_name = plant_code.strip() if plant_code else "Plant 1"
    plant_obj = session.scalar(select(Plant).where(Plant.name == effective_plant_name))
    if not plant_obj:
        plant_obj = session.scalar(select(Plant).where(Plant.is_active.is_(True)))
        if not plant_obj:
            plant_obj = Plant(name=effective_plant_name, code="PLANT-1", is_active=True)
            session.add(plant_obj)
            session.flush()

    # 5. Ensure products and plant mappings exist
    for r in all_flat_rows:
        p_code = r["product_code"]
        existing_prod = session.scalar(select(Product).where(Product.code == p_code))
        if not existing_prod:
            existing_prod = Product(
                code=p_code,
                name=r["description"] or p_code,
                uom=r["uom"] or "PCS",
                part_number=r["part_no"],
                item_id=r["item_id"],
                is_active=True,
            )
            session.add(existing_prod)
            session.flush()

        pp = session.scalar(
            select(ProductPlant).where(
                ProductPlant.product_id == existing_prod.id,
                ProductPlant.plant_id == plant_obj.id,
            )
        )
        if not pp:
            session.add(ProductPlant(product_id=existing_prod.id, plant_id=plant_obj.id, is_active=True, is_primary=True))

    session.flush()

    # 6. Save PRDRecord rows
    workspace_records: list[PRDRecord] = []
    staged_items: list[dict[str, Any]] = []

    m_parts = period.split("-")
    p_year = int(m_parts[0]) if len(m_parts) > 0 and m_parts[0].isdigit() else None
    p_month = int(m_parts[1]) if len(m_parts) > 1 and m_parts[1].isdigit() else None

    for idx, r in enumerate(all_flat_rows, start=1):
        p_obj = session.scalar(select(Product).where(Product.code == r["product_code"]))
        qty_dec = Decimal(r["planned_quantity"])

        rec = PRDRecord(
            id=uuid4(),
            row_index=idx,
            plant=plant_obj.name,
            customer=r["customer"],
            customer_id=UUID(r["customer_id"]) if r.get("customer_id") else None,
            customer_code=r.get("customer_code"),
            customer_group=r.get("customer_group"),
            source_customer_label=r["customer"],
            source_row=r["source_row"],
            product_code=r["product_code"],
            description=r["description"],
            planned_quantity=qty_dec,
            uom=r["uom"] or "Nos",
            target_period=period,
            planning_version=rev_label,
            revision=rev_label,
            schedule_given_on=datetime.fromisoformat(r["schedule_given_on"]) if r.get("schedule_given_on") else None,
            plan_month=p_month,
            plan_year=p_year,
            section_type=r.get("section_type") or "STANDARD",
            status="VALIDATED",
            created_by=actor,
        )
        session.add(rec)
        workspace_records.append(rec)

        staged_items.append({
            "product_code": r["product_code"],
            "product_id": str(p_obj.id) if p_obj else str(uuid4()),
            "plant_code": plant_obj.name,
            "planned_quantity": str(qty_dec),
            "uom": r["uom"] or "Nos",
            "target_period": period,
            "source_row_number": r["source_row"],
            "customer_id": r.get("customer_id"),
        })

    # 7. Create ImportBatch and promote to PlanningVersion
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    batch = ImportBatch(
        filename=filename,
        file_size_bytes=len(file_bytes),
        uploaded_by=actor,
        status="VALIDATED",
        row_count=len(staged_items),
        valid_row_count=len(staged_items),
        error_row_count=0,
        file_hash=file_sha256,
        validation_summary={
            "blocks_count": len(parse_result["blocks"]),
            "grand_total": parse_result["grand_total"],
            "planning_period": period,
            "revision": rev_label,
        },
        staged_data=staged_items,
    )
    session.add(batch)
    session.flush()

    audit(
        session, actor, batch.id, "IMPORT_VERIFIED_PRD", reason,
        {
            "sheet": sheet_name,
            "filename": filename,
            "sha256": file_sha256,
            "planning_period": period,
            "revision": rev_label,
            "row_count": len(staged_items),
        },
        entity="import_batches",
    )

    promote_batch_to_planning_version(session, batch.id, actor, period, rev_label)

    # Clean up staged token
    _STAGED_FILES.pop(file_token, None)

    return PRDExcelImportResponse(
        sheet_name=sheet_name,
        imported_count=len(workspace_records),
        records=[to_prd_record_response(r) for r in workspace_records],
    )


# ---------------------------------------------------------------------------
# Excel Export with Full Customer Columns
# ---------------------------------------------------------------------------

def export_prd_excel(
    session: Session,
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    customer: Optional[str] = None,
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
            query = query.where(
                or_(
                    PRDRecord.planning_version == planning_version.strip(),
                    PRDRecord.revision == planning_version.strip(),
                )
            )
        if status and status.upper() != "ALL":
            query = query.where(PRDRecord.status == status.upper())
        if customer and customer.upper() != "ALL":
            query = query.where(
                or_(
                    PRDRecord.customer.ilike(f"%{customer.strip()}%"),
                    PRDRecord.customer_code.ilike(f"%{customer.strip()}%"),
                )
            )
        if search:
            s = f"%{search.strip()}%"
            query = query.where(
                or_(
                    PRDRecord.product_code.ilike(s),
                    PRDRecord.description.ilike(s),
                    PRDRecord.plant.ilike(s),
                    PRDRecord.customer.ilike(s),
                    PRDRecord.customer_code.ilike(s),
                    PRDRecord.customer_group.ilike(s),
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
        "Customer",
        "Customer ID",
        "Group",
        "Plant",
        "Product / Part No.",
        "Description",
        "Production Plan Qty",
        "Unit",
        "Month / Date",
        "Revision",
        "Section",
        "Status",
        "Remarks",
    ]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center" if col_num in (1, 8, 9, 10, 11, 12, 13) else "left",
            vertical="center",
        )

    ws.row_dimensions[1].height = 24

    for r_idx, row in enumerate(rows, start=1):
        qty_val = float(row.planned_quantity) if row.planned_quantity is not None else 0.0
        row_data = [
            row.row_index or r_idx,
            row.customer or "",
            row.customer_code or "",
            row.customer_group or "",
            row.plant,
            row.product_code,
            row.description,
            qty_val,
            row.uom,
            row.target_period,
            row.revision or row.planning_version,
            row.section_type or "STANDARD",
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
            if col_num in (1, 9, 10, 11, 12, 13):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_num == 8:
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
