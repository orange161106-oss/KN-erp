from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.purchase_workspace import (
    PurchaseSubmitRequest,
    PurchaseSubmitResponse,
    PurchaseWorkspaceResponse,
    PurchasePlanSave,
)
from app.security.permissions import require_permissions
from app.services import purchase_workspace as service

router = APIRouter(prefix="/purchasing/workspace", tags=["purchasing-workspace"])


@router.post('/save', response_model=PurchaseWorkspaceResponse)
def save_purchase_workspace(req: PurchasePlanSave,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions('purchasing:view'))],
    month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=2020, le=2050)):
    return service.save_purchase_plan(session, month=month, year=year, request=req, current_user=current_user)


@router.get("", response_model=PurchaseWorkspaceResponse)
def get_purchase_workspace(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2050),
    search: Optional[str] = None,
    status: Optional[str] = Query(None),
    view: str = Query('normal', pattern='^(normal|md)$'),
    treat_missing_as_zero: bool = Query(True, description="Treat missing stock statement items as zero stock"),
):
    return service.list_purchase_workspace(
        session,
        month=month,
        year=year,
        search=search,
        status_filter=status,
        current_user=current_user,
        view=view,
        treat_missing_as_zero=treat_missing_as_zero,
    )


@router.post("/submit", response_model=PurchaseSubmitResponse)
def post_submit_purchase_workspace(
    req: PurchaseSubmitRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2050),
):
    return service.submit_purchase_workspace_records(
        session,
        month=month,
        year=year,
        record_ids=req.record_ids,
        reason=req.reason,
        current_user=current_user,
    )


@router.get("/export")
def export_purchase_workspace(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2050),
    search: Optional[str] = None,
    status: Optional[str] = Query(None),
    record_ids: Annotated[list[str] | None, Query()] = None,
    view: str = Query('normal', pattern='^(normal|md)$'),
    treat_missing_as_zero: bool = Query(True, description="Treat missing stock statement items as zero stock"),
):
    excel_bytes = service.export_purchase_workspace_excel(
        session,
        month=month,
        year=year,
        search=search,
        status_filter=status,
        record_ids=record_ids,
        current_user=current_user,
        view=view,
        treat_missing_as_zero=treat_missing_as_zero,
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="purchase_{view}_view_{year:04d}_{month:02d}.xlsx"'},
    )
