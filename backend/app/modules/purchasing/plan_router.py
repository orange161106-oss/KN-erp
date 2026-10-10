"""FastAPI router for Monthly Purchase Planning (Normal View & MD View)."""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.purchase_plan import (
    PlanImportConfirmRequest,
    PlanInspectResult,
    PurchasePlanResponse,
    RecalculatePlanRequest,
    SavePurchasePlanRequest,
    SendToApprovalRequest,
    UpdatePlanParametersRequest,
)
from app.security.dependencies import get_current_user
from app.security.permissions import require_permissions
from app.services import purchase_plan as service

router = APIRouter(prefix="/purchasing/plan", tags=["purchasing-plan"])


@router.get("", response_model=Optional[PurchasePlanResponse])
def get_plan(
    planning_period: Annotated[str, Query(description="Period in YYYY-MM format, e.g. 2026-10")],
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Retrieve the monthly purchase plan for a specific month and year."""
    return service.get_purchase_plan(session, planning_period)


@router.post("/init", response_model=PurchasePlanResponse)
def init_or_update_plan(
    req: UpdatePlanParametersRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Initialize or update plan parameters (MSL days, working days) for the month."""
    return service.save_or_init_plan(session, req.planning_period, user.id, req)


@router.post("/recalculate", response_model=PurchasePlanResponse)
def post_recalculate_plan(
    req: RecalculatePlanRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Recalculate order quantities using approved deterministic formulas."""
    return service.recalculate_plan(session, req, user.id)


@router.post("/save", response_model=PurchasePlanResponse)
def post_save_plan(
    req: SavePurchasePlanRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Save user edits to permitted plan fields."""
    return service.save_plan_items(session, req, user.id)


@router.post("/send-to-approval")
def post_send_to_approval(
    req: SendToApprovalRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Submit recommended purchase plan items into the Approval Queue."""
    return service.send_to_approval_queue(session, req, user.id)


@router.post("/inspect", response_model=PlanInspectResult)
async def post_inspect_excel(
    file: Annotated[UploadFile, File()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Inspect uploaded Excel file and auto-detect MD View vs Normal View."""
    file_bytes = await file.read()
    return service.inspect_purchase_excel(file_bytes, file.filename or "upload.xlsx")


@router.post("/import-sheet", response_model=PurchasePlanResponse)
def post_import_sheet(
    confirm_req: PlanImportConfirmRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Import and merge purchase plan records from inspected Excel sheet."""
    return service.import_purchase_plan_sheet(session, confirm_req, user.id)


@router.get("/export")
def get_export_excel(
    planning_period: Annotated[str, Query()],
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    view_type: Annotated[str, Query()] = "NORMAL_VIEW",
    search: Optional[str] = None,
):
    """Export the monthly purchase plan to Excel formatted in MD View or Normal View."""
    excel_bytes = service.export_purchase_plan_excel(
        session, planning_period, view_type=view_type, search=search
    )
    filename = f"KNL_Purchase_Plan_{planning_period}_{view_type}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
