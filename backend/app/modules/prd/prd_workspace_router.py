from app.security.permissions import require_permissions
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.errors import ApplicationError
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
from app.security.dependencies import get_current_user
from app.services import prd_workspace as service

router = APIRouter(prefix="/prd/workspace", tags=["prd-workspace"])


@router.get("/records", response_model=list[PRDWorkspaceRecordResponse], dependencies=[Depends(require_permissions('planning.read'))])
def get_prd_workspace_records(
    user: Annotated[CurrentUser, Depends(get_current_user)],
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


@router.post("/save", response_model=PRDWorkspaceSaveResponse, dependencies=[Depends(require_permissions('planning.write'))])
def save_prd_workspace_records(
    data: PRDWorkspaceSaveRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
):
    return service.save_prd_records(session, data, user.id)


@router.delete("/records/{identity}", status_code=204, dependencies=[Depends(require_permissions('planning.write'))])
def delete_prd_workspace_record(
    identity: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    reason: str = Query(default="Deleted via PRD workspace"),
):
    service.delete_prd_record(session, identity, user.id, reason=reason)
    return Response(status_code=204)


@router.post("/bulk-delete", response_model=PRDWorkspaceBulkDeleteResponse, dependencies=[Depends(require_permissions('planning.write'))])
def bulk_delete_prd_workspace(
    data: PRDWorkspaceBulkDeleteRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
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


@router.post("/inspect", response_model=PRDExcelInspectResponse, dependencies=[Depends(require_permissions('planning.read'))])
async def inspect_prd_excel(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise ApplicationError('SOURCE_TOO_LARGE', 'Use a workbook of at most 10 MB.', 422)
    return service.inspect_prd_excel(contents, file.filename or "prd.xlsx")


@router.post("/import-sheet", response_model=PRDExcelImportResponse, dependencies=[Depends(require_permissions('planning.write'))])
async def import_prd_sheet(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    mode: str = Form(default="APPEND"),
    reason: str = Form(default="Excel PRD import"),
    target_period: str | None = Form(default=None),
    revision_label: str | None = Form(default=None),
):
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise ApplicationError('SOURCE_TOO_LARGE', 'Use a workbook of at most 10 MB.', 422)
    return service.import_prd_excel(
        session,
        contents,
        file.filename or "prd.xlsx",
        sheet_name,
        user.id,
        mode=mode,
        reason=reason,
        target_period=target_period,
        revision_label=revision_label,
    )


@router.get("/export", dependencies=[Depends(require_permissions('planning.read'))])
def export_prd_workspace(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    search: Optional[str] = None,
    plant: Optional[str] = None,
    target_period: Optional[str] = None,
    planning_version: Optional[str] = None,
    status: Optional[str] = None,
    record_ids: Annotated[list[UUID] | None, Query()] = None,
):
    excel_bytes = service.export_prd_excel(
        session,
        search=search,
        plant=plant,
        target_period=target_period,
        planning_version=planning_version,
        status=status,
        record_ids=record_ids,
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="prd_planning_workspace.xlsx"'},
    )


@router.post("/export", dependencies=[Depends(require_permissions('planning.read'))])
def export_prd_workspace_post(
    data: dict[str, list[str]],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
):
    raw_ids = data.get("record_ids", [])
    ids = [UUID(i) for i in raw_ids if i]
    excel_bytes = service.export_prd_excel(session, record_ids=ids if ids else None)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="prd_planning_workspace.xlsx"'},
    )

