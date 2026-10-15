import logging
import traceback
from app.security.permissions import require_permissions
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

logger = logging.getLogger("app.modules.requirements.router")

from app.db.session import get_db
from app.models.requirements import MonthlyRequirementPlan, RequirementLineItem, RequirementStatus
from app.schemas.auth import CurrentUser
from app.schemas.requirements import (
    AggregatedRequirementResponse,
    AggregationRunResponse,
    BulkUploadResponse,
    CalculatedRevisionApprovalResponse,
    CalculatedRequirementResponse,
    CalculationRunRequest,
    MonthlyRequirementPlanCreate,
    MonthlyRequirementPlanResponse,
    RequirementCalculationErrorResponse,
    RequirementCalculationRunResponse,
    RequirementLineItemCreate,
    RequirementLineItemResponse,
)
from app.security.dependencies import get_current_user
from app.services.mrp_calculator import get_aggregated_requirements, run_monthly_aggregation
from app.services.requirements import (
    _to_plan_response,
    bulk_upsert_line_items,
    calculate_planning_version_requirements,
    create_monthly_plan,
    get_calculated_requirements,
    get_calculation_errors,
    get_monthly_plans,
    upsert_single_line_item,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])
plans_router = APIRouter(prefix="/plans", tags=["monthly-requirements-planner"])




@router.post("/planning-versions/{identity}/approve", response_model=CalculatedRevisionApprovalResponse)
def approve_calculated_revision(identity: UUID, session: Annotated[Session, Depends(get_db)],
                                user: Annotated[CurrentUser, Depends(get_current_user)]):
    from app.services.requirement_approval import approve
    return approve(session, identity, user)


@router.post(
    "/calculate",
    response_model=RequirementCalculationRunResponse,
    status_code=status.HTTP_200_OK,
 dependencies=[Depends(require_permissions('requirements.calculate'))])
def post_calculate_requirements(
    req: CalculationRunRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RequirementCalculationRunResponse:
    return calculate_planning_version_requirements(session, req, current_user.id)


@router.get(
    "/planning-versions/{planning_version_id}",
    response_model=list[CalculatedRequirementResponse],
 dependencies=[Depends(require_permissions('requirements.read'))])
def get_version_calculated_requirements(
    planning_version_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    plant_id: Optional[UUID] = Query(None),
    consumable_id: Optional[UUID] = Query(None),
) -> list[CalculatedRequirementResponse]:
    return get_calculated_requirements(
        session,
        planning_version_id=planning_version_id,
        plant_id=plant_id,
        consumable_id=consumable_id,
    )


@router.get(
    "/planning-versions/{planning_version_id}/errors",
    response_model=list[RequirementCalculationErrorResponse],
 dependencies=[Depends(require_permissions('requirements.read'))])
def get_version_calculation_errors(
    planning_version_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[RequirementCalculationErrorResponse]:
    return get_calculation_errors(session, planning_version_id=planning_version_id)


# =========================================================================
# Phase 1: Monthly Requirement Planner & Bulk Ingestion Endpoints
# =========================================================================

def handle_get_plans(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
) -> list[MonthlyRequirementPlanResponse]:
    """Fetch monthly requirement plans.

    Admins/Super Admins see all plans. Standard users (Plant Incharge)
    are automatically filtered to their assigned plant.
    When month and year are specified, automatically auto-provisions missing plant plans in DRAFT.
    """
    return get_monthly_plans(session, current_user, month=month, year=year)


def handle_create_plan(
    payload: MonthlyRequirementPlanCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MonthlyRequirementPlanResponse:
    """Create a new blank monthly requirement plan."""
    return create_monthly_plan(session, payload, current_user)


def handle_upsert_single_item(
    plan_id: UUID,
    payload: RequirementLineItemCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RequirementLineItemResponse:
    """Upsert a single consumable into the grid."""
    return upsert_single_line_item(session, plan_id, payload, current_user)


from app.schemas.requirements import RequirementLineItemUpdate
from app.services.requirements import (
    _to_plan_response,
    bulk_upsert_line_items,
    calculate_planning_version_requirements,
    create_monthly_plan,
    delete_single_line_item,
    get_calculated_requirements,
    get_calculation_errors,
    get_monthly_plans,
    update_single_line_item,
    upsert_single_line_item,
)


def handle_update_line_item(
    plan_id: UUID,
    item_id: UUID,
    payload: RequirementLineItemUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RequirementLineItemResponse:
    """Update an existing line item in the plan."""
    return update_single_line_item(session, plan_id, item_id, payload, current_user)


def handle_delete_line_item(
    plan_id: UUID,
    item_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Delete a line item from the plan."""
    return delete_single_line_item(session, plan_id, item_id, current_user)


async def handle_bulk_upload_items(
    plan_id: UUID,
    file: UploadFile = File(...),
    upload_all_plants: bool = Query(False),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> BulkUploadResponse:
    """Accept a CSV or Excel file, extract Item ID and QTY, and bulk upsert records. Supports upload_all_plants."""
    try:
        content = await file.read()
        return bulk_upsert_line_items(
            session,
            plan_id=plan_id,
            file_bytes=content,
            filename=file.filename or "",
            user=current_user,
            upload_all_plants=upload_all_plants,
        )
    except HTTPException:
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        raise
    except Exception as e:
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        trace_str = traceback.format_exc()
        logger.error(
            "Bulk upload failed for plan_id=%s, file=%s: %s\n%s",
            plan_id,
            getattr(file, "filename", "unknown"),
            str(e),
            trace_str,
        )
        print(
            f"[BULK UPLOAD ERROR] plan_id={plan_id}, file={getattr(file, 'filename', 'unknown')}: {str(e)}\n{trace_str}",
            flush=True,
        )
        detail_msg = getattr(e, "message", None) or str(e)
        if "Trace:" not in detail_msg:
            detail_msg = f"{detail_msg} | Trace: {trace_str}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail_msg,
        )


def require_admin_or_planner_role(user: CurrentUser) -> CurrentUser:
    if user.is_super_admin or getattr(user, "is_superuser", False):
        return user
    roles_normalized = [str(r).upper().strip() for r in (user.roles or [])]
    if any(r in ("ADMIN", "SUPER ADMIN", "SUPER_ADMIN", "PLANNER") for r in roles_normalized):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or Planner role required for this action.",
    )


def handle_submit_plan(
    plan_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MonthlyRequirementPlanResponse:
    """Transition status from DRAFT to SUBMITTED. Accessible by Plant Incharge."""
    plan = session.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly requirement plan not found.")

    # Authorization: Admin can submit any plan; standard users can submit for their assigned plant
    if not (current_user.is_super_admin or any(r.upper() in ("ADMIN", "SUPER ADMIN", "SUPER_ADMIN") for r in (current_user.roles or []))):
        assigned_plant = getattr(current_user, "assigned_plant", None)
        if assigned_plant and assigned_plant.upper() != plan.plant_id.upper():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You are only authorized to submit plans for assigned plant '{assigned_plant}'.",
            )

    if plan.status != RequirementStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit plan in '{plan.status.value}' status. Only DRAFT plans can be submitted.",
        )

    plan.status = RequirementStatus.SUBMITTED
    session.commit()
    session.refresh(plan)
    return _to_plan_response(plan)


def handle_approve_plan(
    plan_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MonthlyRequirementPlanResponse:
    """Transition status to APPROVED (directly from DRAFT or SUBMITTED). Strictly protected: Admin or Planner."""
    require_admin_or_planner_role(current_user)

    plan = session.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly requirement plan not found.")

    if plan.status not in (RequirementStatus.SUBMITTED, RequirementStatus.DRAFT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve plan in '{plan.status.value}' status. Plan is already {plan.status.value}.",
        )

    # Empty plan validation: must have at least one line item
    item_count = session.scalar(
        select(func.count(RequirementLineItem.id)).where(RequirementLineItem.plan_id == plan.id)
    ) or 0
    if item_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve an empty plan. Add at least one requirement line item before approving.",
        )

    plan.status = RequirementStatus.APPROVED
    session.commit()
    session.refresh(plan)

    # Automatic background aggregation upon plan approval
    try:
        run_monthly_aggregation(session, month=plan.month, year=plan.year)
    except Exception:
        pass

    return _to_plan_response(plan)


def handle_reopen_plan(
    plan_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MonthlyRequirementPlanResponse:
    """Transition status from APPROVED back to DRAFT for corrections or additions. Strictly protected: Admin or Planner."""
    require_admin_or_planner_role(current_user)

    plan = session.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly requirement plan not found.")

    if plan.status != RequirementStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reopen plan in '{plan.status.value}' status. Only APPROVED plans can be reopened.",
        )

    plan.status = RequirementStatus.DRAFT
    session.commit()
    session.refresh(plan)

    # Re-run monthly aggregation to update company-wide totals
    try:
        run_monthly_aggregation(session, month=plan.month, year=plan.year)
    except Exception:
        pass

    return _to_plan_response(plan)


def handle_run_aggregation(
    month: int,
    year: int,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AggregationRunResponse:
    """Group identical consumables across multiple approved plans for company-wide gross requirement."""
    require_admin_or_planner_role(current_user)
    return run_monthly_aggregation(session, month=month, year=year)


def handle_get_aggregated_requirements(
    month: int,
    year: int,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[AggregatedRequirementResponse]:
    """Query company-wide aggregated consumable requirements for a month and year.
    Requires Admin or Planner role."""
    require_admin_or_planner_role(current_user)
    return get_aggregated_requirements(session, month=month, year=year)


# Register endpoints on /requirements/plans and /requirements/aggregate
router.add_api_route("/plans", handle_get_plans, methods=["GET"], response_model=list[MonthlyRequirementPlanResponse])
router.add_api_route("/plans", handle_create_plan, methods=["POST"], response_model=MonthlyRequirementPlanResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/plans/{plan_id}/items/single", handle_upsert_single_item, methods=["POST"], response_model=RequirementLineItemResponse)
router.add_api_route("/plans/{plan_id}/items/{item_id}", handle_update_line_item, methods=["PUT"], response_model=RequirementLineItemResponse)
router.add_api_route("/plans/{plan_id}/items/{item_id}", handle_delete_line_item, methods=["DELETE"])
router.add_api_route("/plans/{plan_id}/items/bulk", handle_bulk_upload_items, methods=["POST"], response_model=BulkUploadResponse)
router.add_api_route("/plans/{plan_id}/submit", handle_submit_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
router.add_api_route("/plans/{plan_id}/approve", handle_approve_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
router.add_api_route("/plans/{plan_id}/reopen", handle_reopen_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
router.add_api_route("/aggregate/{month}/{year}", handle_get_aggregated_requirements, methods=["GET"], response_model=list[AggregatedRequirementResponse])
router.add_api_route("/aggregate/{month}/{year}", handle_run_aggregation, methods=["POST"], response_model=AggregationRunResponse)

# Register endpoints on /plans directly
plans_router.add_api_route("", handle_get_plans, methods=["GET"], response_model=list[MonthlyRequirementPlanResponse])
plans_router.add_api_route("", handle_create_plan, methods=["POST"], response_model=MonthlyRequirementPlanResponse, status_code=status.HTTP_201_CREATED)
plans_router.add_api_route("/{plan_id}/items/single", handle_upsert_single_item, methods=["POST"], response_model=RequirementLineItemResponse)
plans_router.add_api_route("/{plan_id}/items/{item_id}", handle_update_line_item, methods=["PUT"], response_model=RequirementLineItemResponse)
plans_router.add_api_route("/{plan_id}/items/{item_id}", handle_delete_line_item, methods=["DELETE"])
plans_router.add_api_route("/{plan_id}/items/bulk", handle_bulk_upload_items, methods=["POST"], response_model=BulkUploadResponse)
plans_router.add_api_route("/{plan_id}/submit", handle_submit_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
plans_router.add_api_route("/{plan_id}/approve", handle_approve_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
plans_router.add_api_route("/{plan_id}/reopen", handle_reopen_plan, methods=["PATCH"], response_model=MonthlyRequirementPlanResponse)
plans_router.add_api_route("/aggregate/{month}/{year}", handle_get_aggregated_requirements, methods=["GET"], response_model=list[AggregatedRequirementResponse])
plans_router.add_api_route("/aggregate/{month}/{year}", handle_run_aggregation, methods=["POST"], response_model=AggregationRunResponse)


