from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirement_requests import (
    RequirementRequestConfirmRequest,
    RequirementRequestConfirmResponse,
    RequirementRequestPreviewResponse,
)
from app.security.dependencies import get_current_user
from app.services import requirement_requests as service

router = APIRouter(prefix="/requirements/requests", tags=["requirement-requests"])


def require_requests_read(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.is_super_admin or "ADMIN" in [r.upper() for r in user.roles]:
        return user
    if getattr(user, "requests_read", False) or getattr(user, "requirements_read", False):
        return user
    raise ApplicationError("PERMISSION_DENIED", "Permission to read requirement requests is required.", 403)


def require_requests_create(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.is_super_admin or "ADMIN" in [r.upper() for r in user.roles]:
        return user
    if getattr(user, "requests_create", False):
        return user
    raise ApplicationError("PERMISSION_DENIED", "Permission to create requirement requests is required.", 403)


@router.post("/preview", response_model=RequirementRequestPreviewResponse)
async def preview_requirement_requests(
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    sheet_name: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(require_requests_read),
    session: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise ApplicationError("EMPTY_FILE", "The uploaded file is empty.", 422)
    return service.preview_requirement_requests_workbook(
        session=session,
        file_bytes=content,
        filename=file.filename or "unknown.xlsx",
        planning_month=month,
        planning_year=year,
        sheet_name_filter=sheet_name,
    )


@router.post("/confirm", response_model=RequirementRequestConfirmResponse)
async def confirm_requirement_requests(
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    review_token: str = Form(...),
    sheet_name: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(require_requests_create),
    session: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise ApplicationError("EMPTY_FILE", "The uploaded file is empty.", 422)

    preview = service.preview_requirement_requests_workbook(
        session=session,
        file_bytes=content,
        filename=file.filename or "unknown.xlsx",
        planning_month=month,
        planning_year=year,
        sheet_name_filter=sheet_name,
    )

    confirm_req = RequirementRequestConfirmRequest(
        filename=file.filename or "unknown.xlsx",
        planning_month=month,
        planning_year=year,
        file_hash=preview.file_hash,
        review_token=review_token,
    )

    return service.confirm_requirement_requests(
        session=session,
        request=confirm_req,
        preview=preview,
        actor=current_user,
    )


@router.post("/unknown-items/export")
async def export_unknown_items(
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    current_user: CurrentUser = Depends(require_requests_read),
    session: Session = Depends(get_db),
):
    content = await file.read()
    preview = service.preview_requirement_requests_workbook(
        session=session,
        file_bytes=content,
        filename=file.filename or "unknown.xlsx",
        planning_month=month,
        planning_year=year,
    )
    csv_bytes = service.export_unknown_items_csv(preview.unknown_items)
    period = f"{year:04d}_{month:02d}"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="Unknown_Item_IDs_{period}.csv"'},
    )


@router.get("/summary")
def get_requests_summary(
    month: int,
    year: int,
    current_user: CurrentUser = Depends(require_requests_read),
    session: Session = Depends(get_db),
):
    req_map = service.get_active_requirement_requests_map(session, month, year)
    return {
        "planning_month": month,
        "planning_year": year,
        "item_count": len(req_map),
        "requests": {str(cid): data for cid, data in req_map.items()},
    }

