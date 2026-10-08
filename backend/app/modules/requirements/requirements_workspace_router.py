from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirements_workspace import (
    RequirementRecalculateResponse,
    RequirementWorkspaceRecord,
)
from app.security.permissions import require_feature_flag
from app.services import requirements_workspace as service

router = APIRouter(prefix="/requirements/workspace", tags=["requirements-workspace"])
ViewPlanning = Annotated[CurrentUser, Depends(require_feature_flag("can_access_requirements"))]
RunCalculations = Annotated[CurrentUser, Depends(require_feature_flag("can_access_requirements"))]


@router.get("/records", response_model=list[RequirementWorkspaceRecord])
def get_requirements_workspace_records(
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
    plant: Optional[str] = None,
    consumable: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    return service.calculate_workspace_requirements(
        session,
        plant_filter=plant,
        consumable_filter=consumable,
        status_filter=status,
        search=search,
    )


@router.post("/recalculate", response_model=RequirementRecalculateResponse)
def post_recalculate_requirements(
    user: RunCalculations,
    session: Annotated[Session, Depends(get_db)],
):
    return service.recalculate_requirements(session)


@router.get("/export")
def export_requirements_workspace(
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
    plant: Optional[str] = None,
    consumable: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    record_ids: Annotated[list[str] | None, Query()] = None,
):
    excel_bytes = service.export_requirements_excel(
        session,
        plant_filter=plant,
        consumable_filter=consumable,
        status_filter=status,
        search=search,
        record_ids=record_ids,
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="consumable_requirements_workspace.xlsx"'},
    )


@router.post("/export")
def export_requirements_workspace_post(
    data: dict[str, list[str]],
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
):
    raw_ids = data.get("record_ids", [])
    excel_bytes = service.export_requirements_excel(session, record_ids=raw_ids if raw_ids else None)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="consumable_requirements_workspace.xlsx"'},
    )
