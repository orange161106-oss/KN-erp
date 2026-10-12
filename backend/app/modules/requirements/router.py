from app.security.permissions import require_permissions
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirements import (
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
from app.services.requirements import (
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
) -> list[MonthlyRequirementPlanResponse]:
    """Fetch monthly requirement plans.

    Admins/Super Admins see all plans. Standard users (Plant Incharge)
    are automatically filtered to their assigned plant.
    """
    return get_monthly_plans(session, current_user)


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


async def handle_bulk_upload_items(
    plan_id: UUID,
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> BulkUploadResponse:
    """Accept a CSV or Excel file, extract Item ID and QTY, and bulk upsert records."""
    content = await file.read()
    return bulk_upsert_line_items(
        session,
        plan_id=plan_id,
        file_bytes=content,
        filename=file.filename or "",
        user=current_user,
    )


# Register endpoints on /requirements/plans
router.add_api_route("/plans", handle_get_plans, methods=["GET"], response_model=list[MonthlyRequirementPlanResponse])
router.add_api_route("/plans", handle_create_plan, methods=["POST"], response_model=MonthlyRequirementPlanResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/plans/{plan_id}/items/single", handle_upsert_single_item, methods=["POST"], response_model=RequirementLineItemResponse)
router.add_api_route("/plans/{plan_id}/items/bulk", handle_bulk_upload_items, methods=["POST"], response_model=BulkUploadResponse)

# Register endpoints on /plans directly
plans_router.add_api_route("", handle_get_plans, methods=["GET"], response_model=list[MonthlyRequirementPlanResponse])
plans_router.add_api_route("", handle_create_plan, methods=["POST"], response_model=MonthlyRequirementPlanResponse, status_code=status.HTTP_201_CREATED)
plans_router.add_api_route("/{plan_id}/items/single", handle_upsert_single_item, methods=["POST"], response_model=RequirementLineItemResponse)
plans_router.add_api_route("/{plan_id}/items/bulk", handle_bulk_upload_items, methods=["POST"], response_model=BulkUploadResponse)

