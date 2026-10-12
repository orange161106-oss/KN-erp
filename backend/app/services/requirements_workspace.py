import calendar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
from typing import Any, Optional
from uuid import UUID, uuid4

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select, and_, or_, func

from app.core.errors import ApplicationError
from app.domain.rules import (
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
)
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.prd import PlanningVersion
from app.models.production import Plant, Process
from app.models.requirements import (
    CalculatedRequirement,
    MonthlyRequirementRecord,
    RequirementCalculationError,
)
from app.models.rules import ConsumptionNorm
from app.schemas.requirements_workspace import (
    MonthlyPlanMetadata,
    RequirementBatchUpdateRequest,
    RequirementBatchUpdateResponse,
    RequirementExcelInspectResponse,
    RequirementImportRequest,
    RequirementRecalculateResponse,
    RequirementRowError,
    RequirementWorkspaceRecord,
)


def get_monthly_plan_metadata(
    session, month: int, year: int
) -> MonthlyPlanMetadata:
    planning_period = f"{year:04d}-{month:02d}"
    version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )
    if not version:
        return MonthlyPlanMetadata(
            has_plan=False,
            planning_month=month,
            planning_year=year,
            planning_period=planning_period,
            record_count=0,
        )

    creator = session.get(User, version.created_by) if version.created_by else None
    updater = session.get(User, version.updated_by) if version.updated_by else None

    # Count records
    rec_count = session.scalar(
        select(func.count(MonthlyRequirementRecord.id)).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ) or 0

    return MonthlyPlanMetadata(
        has_plan=True,
        plan_id=str(version.id),
        planning_month=month,
        planning_year=year,
        planning_period=planning_period,
        status=version.status,
        revision_label=version.revision_label,
        source_filename=version.source_filename,
        created_at=version.created_at,
        created_by=str(version.created_by) if version.created_by else None,
        created_by_name=creator.full_name or creator.username if creator else None,
        updated_at=version.updated_at,
        updated_by=str(version.updated_by) if version.updated_by else None,
        updated_by_name=updater.full_name or updater.username if updater else None,
        record_count=rec_count,
    )


def calculate_workspace_requirements(
    session,
    month: Optional[int] = None,
    year: Optional[int] = None,
    planning_period: Optional[str] = None,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> list[RequirementWorkspaceRecord]:
    """Retrieve requirements for the given planning month and year.

    First checks the dedicated monthly_requirement_records for spreadsheet planning.
    Falls back gracefully to existing calculated_requirements if present.
    """
    target_period = planning_period
    if month and year:
        target_period = f"{year:04d}-{month:02d}"

    # 1. Query dedicated monthly planning records
    query = select(MonthlyRequirementRecord).where(MonthlyRequirementRecord.is_deleted == False)  # noqa: E712
    if target_period:
        query = query.where(MonthlyRequirementRecord.planning_period == target_period)

    monthly_rows = session.scalars(query.order_by(MonthlyRequirementRecord.row_index, MonthlyRequirementRecord.created_at)).all()

    results: list[RequirementWorkspaceRecord] = []

    if monthly_rows:
        for r in monthly_rows:
            results.append(
                RequirementWorkspaceRecord(
                    id=str(r.id),
                    plan_id=str(r.planning_version_id) if r.planning_version_id else None,
                    planning_period=r.planning_period,
                    planning_month=r.planning_month,
                    planning_year=r.planning_year,
                    revision=r.planning_version.revision_label if r.planning_version else "R0",
                    # Group 1: Component
                    part_name=r.part_name,
                    part_number=r.part_number,
                    # Group 2: Consumables
                    consumable_code=r.consumable_code,
                    consumable_name=r.consumable_name,
                    process_name=r.process_name,
                    part_thickness=format(r.part_thickness, ".4f"),
                    process_count=r.process_count,
                    production_order_qty=format(r.production_order_qty, ".4f"),
                    scheduled_consumable_qty=format(r.scheduled_consumable_qty, ".4f"),
                    # Group 3: Operational fields
                    plant=r.plant,
                    process=r.process_name,
                    description=r.consumable_name,
                    unit=r.unit,
                    required_qty=format(r.scheduled_consumable_qty, ".4f"),
                    stock_qty=format(r.stock_qty, ".4f"),
                    shortage_qty=format(r.shortage_qty, ".4f"),
                    po_pending_qty=format(r.po_pending_qty, ".4f"),
                    msl=format(r.msl, ".4f"),
                    status=r.status,
                    remarks=r.remarks,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
    else:
        # Fallback to existing CalculatedRequirement records
        versions_query = select(PlanningVersion).order_by(PlanningVersion.planning_period, PlanningVersion.version_number.desc())
        if target_period:
            versions_query = versions_query.where(PlanningVersion.planning_period == target_period)
        versions = session.scalars(versions_query).all()
        latest: dict[str, PlanningVersion] = {}
        for version in versions:
            latest.setdefault(version.planning_period, version)

        for version in latest.values():
            requirements = session.scalars(
                select(CalculatedRequirement).where(CalculatedRequirement.planning_version_id == version.id)
            ).all()
            errors = session.scalars(
                select(RequirementCalculationError).where(RequirementCalculationError.planning_version_id == version.id)
            ).all()

            for row in requirements:
                material = session.get(Consumable, row.consumable_id)
                plant = session.get(Plant, row.plant_id)
                process = session.get(Process, row.process_id)
                product = session.get(Product, row.product_id)

                p_thick = "0.0000"
                p_count = 1
                if isinstance(row.parameters, dict):
                    p_thick = str(row.parameters.get("thickness", "0.0000"))
                    p_count = int(row.parameters.get("processes", 1))

                results.append(
                    RequirementWorkspaceRecord(
                        id=str(row.id),
                        plan_id=str(version.id),
                        planning_period=version.planning_period,
                        revision=version.revision_label,
                        part_name=product.name if product else "Component",
                        part_number=product.code if product else "PROD-ITEM",
                        consumable_code=material.code if material else "",
                        consumable_name=material.name if material else "",
                        process_name=process.name if process else "",
                        part_thickness=p_thick,
                        process_count=p_count,
                        production_order_qty=format(row.source_production_qty, ".4f"),
                        scheduled_consumable_qty=format(row.calculated_qty, ".4f"),
                        plant=plant.name if plant else "Plant 1",
                        process=process.name if process else "",
                        description=material.name if material else "",
                        unit=row.uom,
                        required_qty=format(row.calculated_qty, ".4f"),
                        stock_qty="Unavailable",
                        shortage_qty="Unavailable",
                        po_pending_qty="Unavailable",
                        msl="Unavailable",
                        status="Calculated",
                        remarks=row.rounding_policy,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                )

            for error in errors:
                plant = session.get(Plant, error.plant_id) if error.plant_id else None
                product = session.get(Product, error.product_id) if error.product_id else None
                material = session.get(Consumable, error.consumable_id) if error.consumable_id else None
                results.append(
                    RequirementWorkspaceRecord(
                        id=str(error.id),
                        plan_id=str(version.id),
                        planning_period=version.planning_period,
                        revision=version.revision_label,
                        part_name=product.name if product else "Unresolved",
                        part_number=product.code if product else "Unresolved",
                        consumable_code=material.code if material else "",
                        consumable_name=material.name if material else error.error_message,
                        process_name="Unresolved",
                        part_thickness="0.0000",
                        process_count=1,
                        production_order_qty="0.0000",
                        scheduled_consumable_qty="Unavailable",
                        plant=plant.name if plant else "Unresolved",
                        process="Unresolved",
                        description=error.error_message,
                        unit="",
                        required_qty="Unavailable",
                        stock_qty="Unavailable",
                        shortage_qty="Unavailable",
                        po_pending_qty="Unavailable",
                        msl="Unavailable",
                        status="Configuration required",
                        remarks=error.error_code,
                        created_at=error.created_at,
                    )
                )

    # Filter predicate
    def matches(record: RequirementWorkspaceRecord) -> bool:
        if plant_filter and plant_filter.upper() != "ALL" and plant_filter.lower() not in record.plant.lower():
            return False
        if consumable_filter and consumable_filter.upper() != "ALL":
            if (
                consumable_filter.lower() not in record.consumable_code.lower()
                and consumable_filter.lower() not in record.consumable_name.lower()
            ):
                return False
        if status_filter and status_filter.upper() != "ALL" and status_filter.lower() not in record.status.lower():
            return False
        if search:
            q = search.lower()
            fields = [
                record.part_name,
                record.part_number,
                record.consumable_code,
                record.consumable_name,
                record.process_name,
                record.plant,
                record.status,
                record.remarks or "",
            ]
            if not any(q in f.lower() for f in fields):
                return False
        return True

    return [r for r in results if matches(r)]


def _normalize_header(hdr: Any) -> str:
    if hdr is None:
        return ""
    text = str(hdr).strip().lower()
    import re
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def inspect_excel_file(
    file_bytes: bytes, filename: str, month: int, year: int, session
) -> RequirementExcelInspectResponse:
    planning_period = f"{year:04d}-{month:02d}"

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Could not read Excel file: {str(e)}", 400)

    # Pick the best worksheet (skip chartsheets or empty sheets)
    ws = None
    for sheet in wb.worksheets:
        if getattr(sheet, "sheet_type", "worksheet") == "chartsheet":
            continue
        if sheet.max_row and sheet.max_row > 1:
            ws = sheet
            break
    if ws is None:
        ws = wb.active

    if not ws:
        raise ApplicationError("EMPTY_WORKBOOK", "The Excel workbook has no usable worksheets.", 400)

    # Column mapping aliases (matched against normalized lowercase strings)
    ALIAS_MAP = {
        "part_name": [
            "used for part name",
            "used for part",
            "used for",
            "part name",
            "component name",
            "product name",
        ],
        "part_number": [
            "used part no production order",
            "used part no",
            "used part number",
            "part no",
            "part number",
            "production order",
            "product code",
        ],
        "consumable_code": [
            "consumable item id",
            "consumable item code",
            "consumable code",
            "item id",
            "item code",
            "consumable id",
        ],
        "consumable_name": [
            "consumable name",
            "description",
            "item description",
            "material name",
            "consumable description",
        ],
        "process_name": [
            "process name",
            "process",
            "operation",
            "operation name",
        ],
        "part_thickness": [
            "part thickness mm",
            "part thickness",
            "thickness mm",
            "thickness",
            "thk",
        ],
        "process_count": [
            "number of processes",
            "number of process",
            "no of processes",
            "process count",
            "processes",
        ],
        "production_order_qty": [
            "production order for selected month",
            "production order qty",
            "production order quantity",
            "production order",
            "monthly production order",
            "planned quantity",
            "planned qty",
            "production qty",
        ],
        "scheduled_consumable_qty": [
            "scheduled consumable quantity for selected month",
            "scheduled consumable qty",
            "scheduled quantity",
            "scheduled qty",
            "required qty",
            "calculated qty",
        ],
    }

    # Locate the header row (search rows 1 to 5)
    header_row_idx = None
    col_mapping: dict[str, int] = {}  # field_name -> 0-indexed column

    for r_idx in range(1, min(6, ws.max_row + 1)):
        row_vals = [_normalize_header(cell.value) for cell in ws[r_idx]]
        # Pass 1: exact matches
        matches: dict[str, int] = {}
        for c_idx, val in enumerate(row_vals):
            if not val:
                continue
            for field, aliases in ALIAS_MAP.items():
                if field in matches:
                    continue
                if any(alias == val for alias in aliases):
                    matches[field] = c_idx

        # Pass 2: substring matches for remaining fields
        for c_idx, val in enumerate(row_vals):
            if not val:
                continue
            for field, aliases in ALIAS_MAP.items():
                if field in matches:
                    continue
                if any(alias in val for alias in aliases if len(alias) >= 10):
                    matches[field] = c_idx

        # If we matched at least 2 distinct primary columns, consider this the header row
        if len(matches) >= 3 or ("part_name" in matches and "consumable_code" in matches):
            header_row_idx = r_idx
            col_mapping = matches
            break

    errors: list[RequirementRowError] = []
    if not header_row_idx:
        # Check row 1 directly as fallback with exact then substring
        row_vals = [_normalize_header(cell.value) for cell in ws[1]]
        for c_idx, val in enumerate(row_vals):
            for field, aliases in ALIAS_MAP.items():
                if field not in col_mapping and any(alias == val for alias in aliases):
                    col_mapping[field] = c_idx
        for c_idx, val in enumerate(row_vals):
            for field, aliases in ALIAS_MAP.items():
                if field not in col_mapping and any(alias in val for alias in aliases if len(alias) >= 10):
                    col_mapping[field] = c_idx
        header_row_idx = 1

    # Validate essential headers
    if "part_name" not in col_mapping and "part_number" not in col_mapping:
        errors.append(
            RequirementRowError(
                row_number=header_row_idx,
                column_name="Used For – Part Name / Part Number",
                error_description="Missing component header ('Used For – Part Name' or 'Used Part No.')",
            )
        )
    if "consumable_code" not in col_mapping and "consumable_name" not in col_mapping:
        errors.append(
            RequirementRowError(
                row_number=header_row_idx,
                column_name="Consumable Item ID / Name",
                error_description="Missing consumable header ('Consumable Item ID' or 'Consumable Name')",
            )
        )
    if "production_order_qty" not in col_mapping:
        errors.append(
            RequirementRowError(
                row_number=header_row_idx,
                column_name="Production Order for Selected Month",
                error_description="Missing production order quantity header ('Production Order for Selected Month')",
            )
        )

    # Read and validate rows
    preview_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    total_data_rows = 0
    valid_data_rows = 0

    for r_idx in range(header_row_idx + 1, ws.max_row + 1):
        raw_row = [cell.value for cell in ws[r_idx]]
        if not any(v is not None and str(v).strip() != "" for v in raw_row):
            continue  # skip completely blank rows

        total_data_rows += 1
        row_errors: list[str] = []

        def get_val(field: str, default: Any = "") -> Any:
            c = col_mapping.get(field)
            if c is not None and c < len(raw_row):
                val = raw_row[c]
                return val if val is not None else default
            return default

        p_name = str(get_val("part_name", "")).strip()
        p_num = str(get_val("part_number", "")).strip()
        c_code = str(get_val("consumable_code", "")).strip()
        c_name = str(get_val("consumable_name", "")).strip()
        proc_name = str(get_val("process_name", "")).strip() or "Standard Process"
        raw_thick = get_val("part_thickness", 0)
        raw_proc_count = get_val("process_count", 1)
        raw_prod_qty = get_val("production_order_qty", 0)
        raw_sched_qty = get_val("scheduled_consumable_qty", 0)

        # 1. Component validation
        if not p_name and not p_num:
            row_errors.append("Both Part Name and Part Number are empty.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Used For – Part Name",
                    error_description="Part Name or Part Number is required.",
                )
            )
        if not p_name:
            p_name = p_num
        if not p_num:
            p_num = p_name

        # 2. Consumable validation
        if not c_code and not c_name:
            row_errors.append("Both Consumable ID and Consumable Name are empty.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Consumable Item ID",
                    error_description="Consumable Item ID or Consumable Name is required.",
                )
            )
        if not c_code:
            c_code = c_name
        if not c_name:
            c_name = c_code

        # 3. Production Order Qty validation
        try:
            prod_qty_dec = Decimal(str(raw_prod_qty).replace(",", "").strip() or "0")
            if prod_qty_dec <= Decimal("0"):
                row_errors.append("Production Order quantity must be greater than zero.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Production Order for Selected Month",
                        error_description=f"Quantity must be positive (got '{raw_prod_qty}').",
                    )
                )
        except (InvalidOperation, ValueError):
            prod_qty_dec = Decimal("0")
            row_errors.append(f"Invalid numeric value '{raw_prod_qty}' for Production Order quantity.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Production Order for Selected Month",
                    error_description=f"Cannot parse '{raw_prod_qty}' as a number.",
                )
            )

        # 4. Thickness validation
        try:
            thick_dec = Decimal(str(raw_thick).replace(",", "").strip() or "0")
            if thick_dec < Decimal("0"):
                row_errors.append("Part thickness cannot be negative.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Part Thickness (mm)",
                        error_description="Thickness cannot be negative.",
                    )
                )
        except (InvalidOperation, ValueError):
            thick_dec = Decimal("0")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Part Thickness (mm)",
                    error_description=f"Cannot parse thickness '{raw_thick}' as a number.",
                )
            )

        # 5. Process count validation
        try:
            p_count_int = int(Decimal(str(raw_proc_count).replace(",", "").strip() or "1"))
            if p_count_int < 1:
                row_errors.append("Process count must be at least 1.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Number of Processes",
                        error_description="Number of Processes must be 1 or more.",
                    )
                )
        except (InvalidOperation, ValueError):
            p_count_int = 1
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Number of Processes",
                    error_description=f"Cannot parse '{raw_proc_count}' as an integer.",
                )
            )

        # 6. Scheduled quantity validation (optional)
        try:
            sched_qty_dec = Decimal(str(raw_sched_qty).replace(",", "").strip() or "0")
        except (InvalidOperation, ValueError):
            sched_qty_dec = Decimal("0")

        # 7. Duplicate row check
        dup_key = f"{p_num.upper()}:{c_code.upper()}:{proc_name.upper()}"
        if dup_key in seen_keys:
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Row Duplicate",
                    error_description=f"Duplicate entry for Part '{p_num}', Consumable '{c_code}', and Process '{proc_name}'.",
                )
            )
        else:
            seen_keys.add(dup_key)

        is_valid = len(row_errors) == 0
        if is_valid:
            valid_data_rows += 1

        preview_rows.append(
            {
                "row_index": r_idx,
                "part_name": p_name,
                "part_number": p_num,
                "consumable_code": c_code,
                "consumable_name": c_name,
                "process_name": proc_name,
                "part_thickness": format(thick_dec, ".4f"),
                "process_count": p_count_int,
                "production_order_qty": format(prod_qty_dec, ".4f"),
                "scheduled_consumable_qty": format(sched_qty_dec, ".4f"),
                "is_valid": is_valid,
                "errors": row_errors,
            }
        )

    # Check if plan already exists for this period
    existing_plan = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .limit(1)
    ) if session else None

    return RequirementExcelInspectResponse(
        filename=filename,
        total_rows=total_data_rows,
        valid_rows=valid_data_rows,
        error_count=len(errors),
        planning_month=month,
        planning_year=year,
        planning_period=planning_period,
        plan_already_exists=existing_plan is not None,
        errors=errors,
        preview_rows=preview_rows,
    )


def import_monthly_requirements(
    session, current_user_id: UUID, req: RequirementImportRequest
) -> tuple[int, MonthlyPlanMetadata]:
    """Saves inspected monthly requirement records in a single transactional unit."""
    planning_period = f"{req.planning_year:04d}-{req.planning_month:02d}"

    # Check existing version
    existing_version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .with_for_update()
    )

    if existing_version and not req.overwrite:
        raise ApplicationError(
            "PLAN_ALREADY_EXISTS",
            f"A monthly requirement plan already exists for {planning_period}. Please confirm to replace/update.",
            status_code=409,
        )

    # If overwrite/update
    if existing_version and req.overwrite:
        new_version_num = existing_version.version_number + 1
        new_revision_label = f"R{new_version_num}"
        # Archive previous records
        session.query(MonthlyRequirementRecord).filter(
            MonthlyRequirementRecord.planning_version_id == existing_version.id
        ).update({"is_deleted": True}, synchronize_session=False)

        version = PlanningVersion(
            planning_period=planning_period,
            version_number=new_version_num,
            revision_label=new_revision_label,
            source_filename=req.source_filename,
            status="DRAFT",
            created_by=existing_version.created_by,
            created_at=existing_version.created_at,
            updated_at=datetime.now(timezone.utc),
            updated_by=current_user_id,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
        )
        session.add(version)
        session.flush()
    else:
        version = PlanningVersion(
            planning_period=planning_period,
            version_number=0,
            revision_label="R0",
            source_filename=req.source_filename,
            status="DRAFT",
            created_by=current_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            updated_by=None,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
        )
        session.add(version)
        session.flush()

    inserted_count = 0
    for idx, item in enumerate(req.records, start=1):
        p_name = str(item.get("part_name", "")).strip()
        p_num = str(item.get("part_number", "")).strip() or p_name
        c_code = str(item.get("consumable_code", "")).strip()
        c_name = str(item.get("consumable_name", "")).strip() or c_code
        proc_name = str(item.get("process_name", "Standard Process")).strip()

        try:
            prod_qty = Decimal(str(item.get("production_order_qty", "0")).replace(",", ""))
        except Exception:
            prod_qty = Decimal("0")

        try:
            sched_qty = Decimal(str(item.get("scheduled_consumable_qty", "0")).replace(",", ""))
        except Exception:
            sched_qty = Decimal("0")

        try:
            thk = Decimal(str(item.get("part_thickness", "0")).replace(",", ""))
        except Exception:
            thk = Decimal("0")

        try:
            p_cnt = int(str(item.get("process_count", "1")))
        except Exception:
            p_cnt = 1

        rec = MonthlyRequirementRecord(
            planning_version_id=version.id,
            planning_period=planning_period,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
            row_index=idx,
            part_name=p_name,
            part_number=p_num,
            consumable_code=c_code,
            consumable_name=c_name,
            process_name=proc_name,
            part_thickness=thk,
            process_count=p_cnt,
            production_order_qty=prod_qty,
            scheduled_consumable_qty=sched_qty,
            unit=str(item.get("unit", "NOS")),
            plant=str(item.get("plant", "Plant 1")),
            status="DRAFT",
            remarks=item.get("remarks"),
            created_by=current_user_id,
        )
        session.add(rec)
        inserted_count += 1

    # Record Audit Log
    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="IMPORT",
            entity_type="planning_versions",
            entity_id=version.id,
            old_values=None,
            new_values={
                "planning_period": planning_period,
                "filename": req.source_filename,
                "inserted_count": inserted_count,
                "revision": version.revision_label,
            },
            reason="Imported monthly consumable requirement records from Excel",
        )
    )

    session.commit()
    meta = get_monthly_plan_metadata(session, req.planning_month, req.planning_year)
    return inserted_count, meta


def batch_update_requirements(
    session, current_user_id: UUID, req: RequirementBatchUpdateRequest
) -> RequirementBatchUpdateResponse:
    """Updates permitted spreadsheet fields in a single database transaction."""
    if not req.records:
        raise ApplicationError("EMPTY_UPDATE", "No records provided for update.", 400)

    updated_count = 0
    affected_version_ids = set()
    sample_version = None

    for item in req.records:
        rec = session.get(MonthlyRequirementRecord, UUID(item.id))
        if not rec or rec.is_deleted:
            continue

        if item.production_order_qty is not None:
            try:
                rec.production_order_qty = Decimal(item.production_order_qty.replace(",", ""))
            except Exception:
                pass

        if item.part_thickness is not None:
            try:
                rec.part_thickness = Decimal(item.part_thickness.replace(",", ""))
            except Exception:
                pass

        if item.process_count is not None:
            rec.process_count = int(item.process_count)

        if item.remarks is not None:
            rec.remarks = item.remarks

        rec.updated_at = datetime.now(timezone.utc)
        if rec.planning_version_id:
            affected_version_ids.add(rec.planning_version_id)
        updated_count += 1

    now = datetime.now(timezone.utc)
    for v_id in affected_version_ids:
        v = session.get(PlanningVersion, v_id)
        if v:
            v.updated_at = now
            v.updated_by = current_user_id
            sample_version = v

    if sample_version:
        session.add(
            AuditLog(
                actor_id=current_user_id,
                action="UPDATE",
                entity_type="planning_versions",
                entity_id=sample_version.id,
                old_values=None,
                new_values={"updated_count": updated_count},
                reason="Batch updated spreadsheet fields in monthly requirements",
            )
        )

    session.commit()

    # Retrieve fresh metadata and records
    month = sample_version.planning_month if sample_version and sample_version.planning_month else None
    year = sample_version.planning_year if sample_version and sample_version.planning_year else None
    period = sample_version.planning_period if sample_version else None

    refreshed_records = calculate_workspace_requirements(session, month=month, year=year, planning_period=period)
    meta = get_monthly_plan_metadata(session, month or 1, year or 2026) if month and year else MonthlyPlanMetadata()

    return RequirementBatchUpdateResponse(
        message=f"Successfully updated {updated_count} record(s).",
        updated_count=updated_count,
        records=refreshed_records,
        plan_metadata=meta,
    )


def recalculate_monthly_requirements(
    session, current_user_id: UUID, month: int, year: int
) -> RequirementRecalculateResponse:
    """Deterministically recalculates consumable requirements using approved formulas."""
    planning_period = f"{year:04d}-{month:02d}"

    version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .with_for_update()
    )

    if not version:
        raise ApplicationError(
            "PLAN_NOT_FOUND",
            f"No monthly requirement plan exists for {planning_period}. Please upload an Excel sheet first.",
            404,
        )

    records = session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ).all()

    if not records:
        raise ApplicationError(
            "NO_RECORDS_TO_CALCULATE",
            f"No records found in plan for {planning_period}.",
            400,
        )

    # Deterministic calculation using approved rules
    critical_count = 0
    low_count = 0

    for rec in records:
        # Find approved consumption norm by consumable_code
        norm = session.scalar(
            select(ConsumptionNorm)
            .join(Consumable, ConsumptionNorm.consumable_id == Consumable.id)
            .where(
                func.upper(Consumable.code) == rec.consumable_code.strip().upper(),
                ConsumptionNorm.is_active == True,  # noqa: E712
            )
            .limit(1)
        )

        if norm:
            rule_type = RuleType(norm.rule_type)
            params = dict(norm.parameters)

            if rule_type == RuleType.PRODUCTION_RATE:
                if "rate" not in params and "usage_rate" in params:
                    params["rate"] = params["usage_rate"]
                elif "rate" not in params and "consumption_rate" in params:
                    params["rate"] = params["consumption_rate"]
            elif rule_type == RuleType.AREA_COVERAGE:
                if "coverage" not in params and "coverage_sqft_per_unit" in params:
                    params["coverage"] = params["coverage_sqft_per_unit"]
                if "area_per_unit" not in params and "area_per_unit_sqft" in params:
                    params["area_per_unit"] = params["area_per_unit_sqft"]
            elif rule_type == RuleType.TOOL_LIFE:
                if "tool_life" not in params and "tool_life_strokes" in params:
                    params["tool_life"] = params["tool_life_strokes"]
                params.setdefault("number_of_operations", Decimal(str(rec.process_count or 1)))

            # Injected variables for formulas requiring thickness or process count
            if rec.part_thickness and rec.part_thickness > Decimal("0"):
                params.setdefault("thickness", float(rec.part_thickness))
            if rec.process_count and rec.process_count > 1:
                params.setdefault("processes", rec.process_count)

            rule_input = RuleCalculationInput(
                rule_type=rule_type,
                rule_version=norm.version,
                production_quantity=rec.production_order_qty,
                parameters=params,
                rounding_policy=RoundingPolicy.parse(norm.rounding_policy),
                rounding_precision=norm.rounding_precision,
                unit=rec.unit,
            )

            try:
                calc_res = evaluate_rule(rule_input)
                rec.scheduled_consumable_qty = calc_res.final_calculated_requirement
                rec.status = "Calculated"
                rec.remarks = f"Calculated: {rule_type.value}"
            except (RuleDomainError, Exception) as e:
                rec.status = "Configuration required"
                rec.remarks = f"Calculation error: {str(e)}"
        else:
            # Fallback: if no explicit norm configured in consumption_norms, flag for review
            rec.status = "Configuration required"
            rec.remarks = f"No active Consumption Norm configured for '{rec.consumable_code}'"

        # Calculate shortage
        shortage = max(Decimal("0"), rec.scheduled_consumable_qty - (rec.stock_qty + rec.po_pending_qty))
        rec.shortage_qty = shortage
        if shortage > Decimal("0"):
            if rec.stock_qty <= Decimal("0"):
                rec.status = "Critical shortage"
                critical_count += 1
            else:
                rec.status = "Low"
                low_count += 1

        rec.updated_at = datetime.now(timezone.utc)

    # Touch version status & modified timestamps
    now = datetime.now(timezone.utc)
    version.calculated_at = now
    version.status = "CALCULATED"
    version.updated_at = now
    version.updated_by = current_user_id

    # Record Audit Log
    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="CALCULATE",
            entity_type="planning_versions",
            entity_id=version.id,
            old_values=None,
            new_values={
                "planning_period": planning_period,
                "recalculated_count": len(records),
                "critical_shortages": critical_count,
            },
            reason="Recalculated monthly requirements with deterministic rules",
        )
    )

    session.commit()

    refreshed = calculate_workspace_requirements(session, month=month, year=year)
    meta = get_monthly_plan_metadata(session, month, year)

    return RequirementRecalculateResponse(
        message=f"Recalculation complete for {planning_period}. Processed {len(records)} records.",
        record_count=len(records),
        critical_shortages=critical_count,
        low_stock=low_count,
        records=refreshed,
        plan_metadata=meta,
    )


def export_requirements_excel(
    session,
    month: Optional[int] = None,
    year: Optional[int] = None,
    planning_period: Optional[str] = None,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    record_ids: Optional[list[str]] = None,
) -> bytes:
    records = calculate_workspace_requirements(
        session,
        month=month,
        year=year,
        planning_period=planning_period,
        plant_filter=plant_filter,
        consumable_filter=consumable_filter,
        status_filter=status_filter,
        search=search,
    )
    if record_ids:
        records = [r for r in records if r.id in record_ids]

    period_str = planning_period or (f"{year:04d}-{month:02d}" if month and year else "All Periods")
    month_name = calendar.month_name[month] if month and 1 <= month <= 12 else ""
    period_label = f"{month_name} {year}" if month_name and year else period_str

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Consumable Requirements"

    # Color palette
    navy_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    steel_fill = PatternFill(start_color="2E5B88", end_color="2E5B88", fill_type="solid")
    gray_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    title_font = Font(name="Calibri", size=14, bold=True, color="1B3A5C")
    meta_font = Font(name="Calibri", size=10, italic=True, color="475569")
    group_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    col_header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # Row 1: Title
    ws.cell(row=1, column=1, value="KNL CONSUMABLE REQUIREMENTS PLANNING").font = title_font
    # Row 2: Planning Period Metadata
    ws.cell(
        row=2,
        column=1,
        value=f"Planning Period: {period_label}  |  Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Records: {len(records)}",
    ).font = meta_font

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 18

    # Row 4: Group Headers
    # Col 1: #
    # Col 2-3: FOR COMPONENT (Used For - Part Name, Used Part No.)
    # Col 4-10: FOR CONSUMABLES (Consumable Item ID, Consumable Name, Process Name, Part Thickness, Number of Processes, Production Order Qty, Scheduled Consumable Qty)
    # Col 11-15: INVENTORY & STATUS (Unit, Stock Qty, Shortage Qty, Status, Remarks)

    group_row = 4
    col_row = 5

    ws.row_dimensions[group_row].height = 22
    ws.row_dimensions[col_row].height = 24

    ws.cell(row=group_row, column=1, value="")
    ws.merge_cells(start_row=group_row, start_column=2, end_row=group_row, end_column=3)
    ws.cell(row=group_row, column=2, value="FOR COMPONENT").fill = navy_fill
    ws.cell(row=group_row, column=2).font = group_header_font
    ws.cell(row=group_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(start_row=group_row, start_column=4, end_row=group_row, end_column=10)
    ws.cell(row=group_row, column=4, value="FOR CONSUMABLES").fill = steel_fill
    ws.cell(row=group_row, column=4).font = group_header_font
    ws.cell(row=group_row, column=4).alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(start_row=group_row, start_column=11, end_row=group_row, end_column=15)
    ws.cell(row=group_row, column=11, value="INVENTORY & STATUS").fill = navy_fill
    ws.cell(row=group_row, column=11).font = group_header_font
    ws.cell(row=group_row, column=11).alignment = Alignment(horizontal="center", vertical="center")

    headers = [
        "#",
        "Used For – Part Name",
        "Used Part No. (Production Order)",
        "Consumable Item ID",
        "Consumable Name",
        "Process Name",
        "Part Thickness (mm)",
        "Number of Processes",
        "Production Order for Selected Month",
        "Scheduled Consumable Quantity for Selected Month",
        "Unit",
        "Stock Qty",
        "Shortage Qty",
        "Status",
        "Remarks",
    ]

    for col_num, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=col_row, column=col_num, value=h_text)
        cell.fill = navy_fill if col_num in (1, 2, 3, 11, 12, 13, 14, 15) else steel_fill
        cell.font = col_header_font
        cell.border = thin_border
        cell.alignment = Alignment(
            horizontal="center" if col_num in (1, 8, 11, 14) else "right" if col_num in (7, 9, 10, 12, 13) else "left",
            vertical="center",
            wrap_text=True,
        )

    # Data Rows
    for r_idx, row in enumerate(records, start=1):
        current_row = col_row + r_idx
        ws.row_dimensions[current_row].height = 20

        # Numeric conversions for Excel
        def to_num(val: str) -> float:
            try:
                return float(val.replace(",", "").strip())
            except Exception:
                return 0.0

        row_data = [
            r_idx,
            row.part_name,
            row.part_number,
            row.consumable_code,
            row.consumable_name,
            row.process_name,
            to_num(row.part_thickness),
            row.process_count,
            to_num(row.production_order_qty),
            to_num(row.scheduled_consumable_qty),
            row.unit,
            to_num(row.stock_qty),
            to_num(row.shortage_qty),
            row.status,
            row.remarks or "",
        ]

        for col_num, val in enumerate(row_data, start=1):
            cell = ws.cell(row=current_row, column=col_num, value=val)
            cell.font = data_font
            cell.border = thin_border

            if col_num == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_num in (7, 9, 10, 12, 13):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0.0000"
            elif col_num in (8, 11, 14):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col if cell.row >= col_row)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
