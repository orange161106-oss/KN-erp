from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.prd_workspace import (
    PRDExcelImportResponse,
    PRDExcelInspectResponse,
    PRDWorkspaceBulkDeleteRequest,
    PRDWorkspaceBulkDeleteResponse,
    PRDWorkspaceRecordResponse,
    PRDWorkspaceSaveRequest,
    PRDWorkspaceSaveResponse,
)
from app.security.permissions import require_feature_flag
from app.services import prd_workspace as service

router = APIRouter(prefix="/prd/workspace", tags=["prd-workspace"])
ViewPlanning = Annotated[CurrentUser, Depends(require_feature_flag("can_access_prd_planning"))]


@router.get("/records", response_model=list[PRDWorkspaceRecordResponse])
def get_prd_workspace_records(
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_prd_records(
        session,
        search=search,
        plant=plant,
        target_period=target_period,
        planning_version=planning_version,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/save", response_model=PRDWorkspaceSaveResponse)
def save_prd_workspace_records(
    data: PRDWorkspaceSaveRequest,
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
):
    return service.save_prd_records(session, data, user.id)


@router.delete("/records/{identity}", status_code=204)
def delete_prd_workspace_record(
    identity: UUID,
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
    reason: str = Query(default="Deleted via PRD workspace"),
):
    service.delete_prd_record(session, identity, user.id, reason=reason)
    return Response(status_code=204)


@router.post("/bulk-delete", response_model=PRDWorkspaceBulkDeleteResponse)
def bulk_delete_prd_workspace(
    data: PRDWorkspaceBulkDeleteRequest,
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
):
    count = service.bulk_delete_prd_records(
        session,
        ids=data.ids,
        delete_all_matching=data.delete_all_matching,
        search=data.search,
        plant=data.plant,
        target_period=data.target_period,
        planning_version=data.planning_version,
        status=data.status,
        actor=user.id,
        reason=data.reason,
    )
    return PRDWorkspaceBulkDeleteResponse(deleted_count=count)


@router.post("/inspect", response_model=PRDExcelInspectResponse)
async def inspect_prd_excel(
    user: ViewPlanning,
    file: UploadFile = File(...),
):
    contents = await file.read()
    return service.inspect_prd_excel(contents, file.filename or "prd.xlsx")


@router.post("/import-sheet", response_model=PRDExcelImportResponse)
async def import_prd_sheet(
    user: ViewPlanning,
    session: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    header_row: int = Form(default=1),
    planning_version: str = Form(default="R0"),
    mode: str = Form(default="replace"),
):
    contents = await file.read()
    return service.import_prd_excel_sheet(
        session,
        contents,
        filename=file.filename or "prd.xlsx",
        sheet_name=sheet_name,
        header_row=header_row,
        planning_version=planning_version,
        mode=mode,
        actor=user.id,
    )
