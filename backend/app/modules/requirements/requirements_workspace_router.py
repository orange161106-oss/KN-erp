from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirement_loading import MonthlyWorkspace
from app.schemas.requirements_workspace import (
    MonthlyPlanMetadata,
    RequirementBatchUpdateRequest,
    RequirementBatchUpdateResponse,
    RequirementBulkDeleteRequest,
    RequirementBulkDeleteResponse,
    RequirementExcelInspectResponse,
    RequirementImportRequest,
    RequirementRecalculateResponse,
    RequirementWorkspaceRecord,
)
from app.security.dependencies import get_current_user
from app.security.permissions import require_feature_flag
from app.core.errors import ApplicationError
from app.services import requirements_workspace as service
from app.models.prd import ImportBatch, PlanningVersion


def _check_central_scope(session, user, month=None, year=None, planning_period=None):
    """Keep the central router's access boundary on the monthly compatibility view."""
    if user.is_super_admin or not user.plant_ids:
        return
    period = f'{year:04d}-{month:02d}' if month and year else planning_period
    query = select(ImportBatch.validation_summary).join(PlanningVersion,
        ImportBatch.planning_version_id == PlanningVersion.id)
    if period:
        query = query.where(PlanningVersion.planning_period == period)
    if any((value or {}).get('workflow') == 'BASIC_CENTRAL_V1' for value in session.scalars(query)):
        raise ApplicationError('CENTRAL_REVIEW_REQUIRED', 'Central plans are reviewed by Super Admin.', 403)

router = APIRouter(prefix="/requirements/workspace", tags=["requirements-workspace"])
CanReadRequirements = Annotated[CurrentUser, Depends(require_feature_flag("requirements_read"))]
CanUpdateRequirements = Annotated[CurrentUser, Depends(require_feature_flag("requirements_update"))]


def require_requirements_delete(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.is_super_admin or "ADMIN" in user.roles or getattr(user, "requirements_delete", False) or getattr(user, "requirements_update", False):
        return user
    raise ApplicationError("PERMISSION_DENIED", "Permission to delete requirements is required.", 403)


CanDeleteRequirements = Annotated[CurrentUser, Depends(require_requirements_delete)]


@router.get('/view', response_model=MonthlyWorkspace)
def get_workspace_view(user: CanReadRequirements, session: Annotated[Session, Depends(get_db)],
    month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=2020, le=2050),
    plant: str | None = None, consumable: str | None = None,
    status: str | None = None, search: str | None = None):
    _check_central_scope(session, user, month, year)
    return service.load_workspace_view(session, month, year, plant=plant,
        consumable=consumable, status=status, search=search)


@router.get("/plan-metadata", response_model=MonthlyPlanMetadata)
def get_monthly_plan_metadata(
    user: CanReadRequirements,
    session: Annotated[Session, Depends(get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2050),
):
    """Retrieve saved monthly requirement plan metadata and modification timestamps."""
    _check_central_scope(session, user, month, year)
    return service.get_monthly_plan_metadata(session, month=month, year=year)


@router.get("/records", response_model=list[RequirementWorkspaceRecord])
def get_requirements_workspace_records(
    user: CanReadRequirements,
    session: Annotated[Session, Depends(get_db)],
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2050),
    planning_period: Optional[str] = None,
    plant: Optional[str] = None,
    consumable: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """Retrieve monthly requirement records for the selected planning period."""
    _check_central_scope(session, user, month, year, planning_period)
    return service.calculate_workspace_requirements(
        session,
        month=month,
        year=year,
        planning_period=planning_period,
        plant_filter=plant,
        consumable_filter=consumable,
        status_filter=status,
        search=search,
    )


@router.post("/inspect-excel", response_model=RequirementExcelInspectResponse)
def post_inspect_excel(
    user: CanUpdateRequirements,
    session: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
):
    """Parses and validates an uploaded Excel sheet against KNL consumable planning columns."""
    content = file.file.read()
    return service.inspect_excel_file(
        file_bytes=content,
        filename=file.filename or "uploaded.xlsx",
        month=month,
        year=year,
        session=session,
    )


@router.post("/import")
def post_import_monthly_requirements(
    req: RequirementImportRequest,
    user: CanUpdateRequirements,
    session: Annotated[Session, Depends(get_db)],
):
    """Transactionally saves validated Excel records for the selected month and year."""
    count, meta = service.import_monthly_requirements(
        session=session,
        current_user_id=user.id,
        req=req,
    )
    return {
        "message": f"Successfully imported {count} requirement records for {meta.planning_period}.",
        "inserted_count": count,
        "plan_metadata": meta,
    }


@router.put("/records", response_model=RequirementBatchUpdateResponse)
def put_update_requirements(
    req: RequirementBatchUpdateRequest,
    user: CanUpdateRequirements,
    session: Annotated[Session, Depends(get_db)],
):
    """Batch-updates permitted editable spreadsheet fields and records modification timestamps."""
    return service.batch_update_requirements(
        session=session,
        current_user_id=user.id,
        req=req,
    )


@router.post("/recalculate", response_model=RequirementRecalculateResponse)
def post_recalculate_requirements(
    user: CanUpdateRequirements,
    session: Annotated[Session, Depends(get_db)],
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2050),
):
    """Deterministically recalculates consumable requirements using approved formulas."""
    _check_central_scope(session, user, month, year)
    if month and year:
        return service.recalculate_monthly_requirements(
            session=session, current_user_id=user.id, month=month, year=year
        )
    # Fallback to general workspace recalculate
    return RequirementRecalculateResponse(
        message="Authoritative calculation refreshed.",
        record_count=0,
        critical_shortages=0,
        low_stock=0,
        records=service.calculate_workspace_requirements(session),
    )


@router.get("/export")
def export_requirements_workspace(
    user: CanReadRequirements,
    session: Annotated[Session, Depends(get_db)],
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2050),
    planning_period: Optional[str] = None,
    plant: Optional[str] = None,
    consumable: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    record_ids: Annotated[list[str] | None, Query()] = None,
):
    _check_central_scope(session, user, month, year, planning_period)
    excel_bytes = service.export_requirements_excel(
        session,
        month=month,
        year=year,
        planning_period=planning_period,
        plant_filter=plant,
        consumable_filter=consumable,
        status_filter=status,
        search=search,
        record_ids=record_ids,
    )
    period_label = planning_period or (f"{year:04d}_{month:02d}" if month and year else "all")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="consumable_requirements_{period_label}.xlsx"'},
    )


@router.post("/export")
def export_requirements_workspace_post(
    data: dict[str, Any],
    user: CanReadRequirements,
    session: Annotated[Session, Depends(get_db)],
):
    raw_ids = data.get("record_ids", [])
    month = data.get("month")
    year = data.get("year")
    planning_period = data.get("planning_period")
    _check_central_scope(session, user, month, year, planning_period)
    excel_bytes = service.export_requirements_excel(
        session,
        month=month,
        year=year,
        planning_period=planning_period,
        record_ids=raw_ids if raw_ids else None,
    )
    period_label = planning_period or (f"{year}_{month}" if month and year else "workspace")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="consumable_requirements_{period_label}.xlsx"'},
    )


@router.delete("/records/{identity}", status_code=204)
def delete_workspace_record(
    identity: UUID,
    user: CanDeleteRequirements,
    session: Annotated[Session, Depends(get_db)],
    reason: Optional[str] = Query(None),
):
    """Soft-deletes a single requirement record and writes to audit log."""
    service.delete_requirement_record(session, identity, user.id, reason=reason)


@router.post("/bulk-delete", response_model=RequirementBulkDeleteResponse)
def bulk_delete_workspace(
    data: RequirementBulkDeleteRequest,
    user: CanDeleteRequirements,
    session: Annotated[Session, Depends(get_db)],
):
    """Soft-deletes multiple requirement records in one atomic transaction."""
    record_uuids = []
    for r_id in data.record_ids:
        try:
            record_uuids.append(UUID(r_id))
        except (ValueError, TypeError):
            continue

    count, meta = service.bulk_delete_requirement_records(
        session,
        record_ids=record_uuids,
        current_user_id=user.id,
        reason=data.reason,
    )
    return RequirementBulkDeleteResponse(
        message=f"Successfully deleted {count} requirement record(s).",
        deleted_count=count,
        plan_metadata=meta,
    )
