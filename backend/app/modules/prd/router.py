from app.security.permissions import require_permissions
from typing import Annotated, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.prd import (
    ImportBatchResponse,
    ImportErrorResponse,
    PlanningVersionResponse,
    PRDOrderItemResponse,
    PRDPromoteResponse,
)
from app.security.dependencies import get_current_user
from app.services.prd import (
    get_import_batch,
    get_planning_version_items,
    list_import_batches,
    list_import_errors,
    list_planning_versions,
    promote_batch_to_planning_version,
    stage_and_validate_prd_file,
)

router = APIRouter(prefix="/prd", tags=["prd"])


@router.post("/upload", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('planning.write'))])
async def upload_prd_file(
    file: UploadFile = File(...),
    planning_period: str = Form("2026-10"),
    session: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ImportBatchResponse:
    contents = await file.read()
    filename = file.filename or "unknown.xlsx"
    batch = stage_and_validate_prd_file(
        db=session,
        file_bytes=contents,
        filename=filename,
        planning_period=planning_period,
        user_id=current_user.id,
    )
    return batch


@router.get("/batches", response_model=list[ImportBatchResponse], dependencies=[Depends(require_permissions('planning.read'))])
def get_batches(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[ImportBatchResponse]:
    return list_import_batches(session)


@router.get("/batches/{batch_id}", response_model=ImportBatchResponse, dependencies=[Depends(require_permissions('planning.read'))])
def get_batch(
    batch_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ImportBatchResponse:
    batch = get_import_batch(session, batch_id)
    if not batch:
        raise ApplicationError("NOT_FOUND", "Import batch not found", status_code=404)
    return batch


@router.get("/batches/{batch_id}/errors", response_model=list[ImportErrorResponse], dependencies=[Depends(require_permissions('planning.read'))])
def get_batch_errors(
    batch_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[ImportErrorResponse]:
    batch = get_import_batch(session, batch_id)
    if not batch:
        raise ApplicationError("NOT_FOUND", "Import batch not found", status_code=404)
    return list_import_errors(session, batch_id)


@router.post("/batches/{batch_id}/promote", response_model=PRDPromoteResponse, dependencies=[Depends(require_permissions('planning.write'))])
def promote_batch(
    batch_id: UUID,
    planning_period: str = Form("2026-10"),
    revision_label: str = Form("R0"),
    session: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PRDPromoteResponse:
    version, header, line_count = promote_batch_to_planning_version(
        db=session,
        batch_id=batch_id,
        user_id=current_user.id,
        planning_period=planning_period,
        revision_label=revision_label,
    )
    return PRDPromoteResponse(
        planning_version_id=version.id,
        revision_label=version.revision_label,
        status=version.status,
        total_planned_qty=header.total_planned_qty,
        total_line_items=header.total_line_items,
    )


@router.get("/planning-versions", response_model=list[PlanningVersionResponse], dependencies=[Depends(require_permissions('planning.read'))])
def get_planning_versions(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[PlanningVersionResponse]:
    return list_planning_versions(session)


@router.get("/planning-versions/{version_id}/items", response_model=list[PRDOrderItemResponse], dependencies=[Depends(require_permissions('planning.read'))])
def get_version_items(
    version_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[PRDOrderItemResponse]:
    return get_planning_version_items(session, version_id)
