import io
from typing import Annotated, Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require_admin_role
from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user
from app.services import product_master_service as service

router = APIRouter(prefix="/masters/product-master", tags=["product-master"])


# ---------------------------------------------------------------------------
# Tab 1: List of Consumables
# ---------------------------------------------------------------------------

@router.post("/consumables/single", status_code=status.HTTP_201_CREATED)
def create_single_consumable(
    data: service.ConsumableSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.upsert_single_consumable(session, data, current_user.id, username=current_user.username)


@router.post("/consumables/bulk")
def bulk_upload_consumables(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_admin_role)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    return service.bulk_upsert_consumables(session, contents, current_user.id, username=current_user.username)


@router.get("/consumables")
def get_consumables(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_consumables_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Tab 2: List of Sales Parts
# ---------------------------------------------------------------------------

@router.post("/sales-parts/single", status_code=status.HTTP_201_CREATED)
def create_single_sales_part(
    data: service.SalesPartSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.upsert_single_sales_part(session, data, current_user.id, username=current_user.username)


@router.post("/sales-parts/bulk")
def bulk_upload_sales_parts(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_admin_role)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    return service.bulk_upsert_sales_parts(session, contents, current_user.id, username=current_user.username)


@router.get("/sales-parts")
def get_sales_parts(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_sales_parts_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Tab 3: Consumable for Assemble (BOM)
# ---------------------------------------------------------------------------

@router.post("/assemble/single", status_code=status.HTTP_201_CREATED)
def create_single_assemble(
    data: service.AssembleSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.upsert_single_assemble(session, data, current_user.id, username=current_user.username)


@router.post("/assemble/preview", response_model=service.AssembleImportPreviewResponse)
async def preview_assemble_upload(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> service.AssembleImportPreviewResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise ApplicationError("INVALID_FILE_TYPE", "Only .xlsx Excel files are supported.", 422)
    contents = await file.read(15 * 1024 * 1024 + 1)
    if len(contents) > 15 * 1024 * 1024:
        raise ApplicationError("FILE_TOO_LARGE", "File size exceeds the 15 MB limit.", 413)
    return service.execute_with_db_retry(
        lambda: service.preview_assemble_import(session, contents, file.filename, current_user.id)
    )


@router.post("/assemble/confirm", response_model=service.AssembleImportJobResponse)
def confirm_assemble_upload(
    payload: service.AssembleImportConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> service.AssembleImportJobResponse:
    session_factory = getattr(request.app.state, "session_factory", None)
    return service.confirm_assemble_import(
        db=session,
        file_token=payload.file_token,
        actor_id=current_user.id,
        session_factory=session_factory,
        background_tasks=background_tasks,
    )


@router.get("/assemble/jobs/{job_id}", response_model=service.AssembleImportJobResponse)
def get_assemble_job(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> service.AssembleImportJobResponse:
    return service.get_assemble_job_status(job_id)


@router.get("/assemble/preview-errors")
def export_assemble_preview_errors(
    file_token: str = Query(..., description="File token from preview response"),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    entry = service._ASSEMBLE_PREVIEW_STORE.get(file_token)
    if not entry:
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The requested preview token has expired or is invalid. Please re-upload the file.",
            404,
        )
    excel_bytes = service.export_assemble_errors_excel(entry["issues"])
    filename = f"assemble_import_errors_{file_token[:8]}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)


@router.post("/assemble/bulk")
def bulk_upload_assemble(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_admin_role)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    if len(contents) > 15 * 1024 * 1024:
        raise ApplicationError("FILE_TOO_LARGE", "File size exceeds the 15 MB limit.", 413)
    return service.bulk_upsert_assemble(session, contents, current_user.id, username=current_user.username)


@router.get("/assemble")
def get_assemble_mappings(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_assemble_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Item Update & Soft-Delete (Deactivate) Endpoints (Destructive - Admin Only)
# ---------------------------------------------------------------------------

@router.put("/{category}/{item_id}")
def update_master_item(
    category: str,
    item_id: UUID,
    payload: dict,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.update_product_master_item(session, category, item_id, payload, current_user.id, username=current_user.username)


@router.patch("/{category}/{item_id}/deactivate")
def deactivate_master_item(
    category: str,
    item_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.deactivate_product_master_item(session, category, item_id, current_user.id, username=current_user.username)


@router.delete("/{category}/{item_id}")
def delete_master_item(
    category: str,
    item_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_admin_role)],
):
    return service.deactivate_product_master_item(session, category, item_id, current_user.id, username=current_user.username)
