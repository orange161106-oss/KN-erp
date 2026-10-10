from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirements_workspace import (
    MonthlyPlanMetadata,
    RequirementBatchUpdateRequest,
    RequirementBatchUpdateResponse,
    RequirementExcelInspectResponse,
    RequirementImportRequest,
    RequirementRecalculateResponse,
    RequirementWorkspaceRecord,
)
from app.security.permissions import require_feature_flag
from app.services import requirements_workspace as service

router = APIRouter(prefix="/requirements/workspace", tags=["requirements-workspace"])
CanReadRequirements = Annotated[CurrentUser, Depends(require_feature_flag("requirements_read"))]
CanUpdateRequirements = Annotated[CurrentUser, Depends(require_feature_flag("requirements_update"))]


@router.get("/plan-metadata", response_model=MonthlyPlanMetadata)
def get_monthly_plan_metadata(
    user: CanReadRequirements,
    session: Annotated[Session, Depends(get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2050),
):
    """Retrieve saved monthly requirement plan metadata and modification timestamps."""
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
async def post_inspect_excel(
    user: CanUpdateRequirements,
    session: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
):
    """Parses and validates an uploaded Excel sheet against KNL consumable planning columns."""
    content = await file.read()
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
