"""FastAPI router for M3.4 — Plant Confirmation & Additional Requirement Workflow.

No business logic here. Routes authenticate, authorise, validate and delegate
to app.services.plant_workflow.

Permissions (TBD-3 resolved):
  plant_workflow:view    — view confirmations and adjustments
  plant_workflow:confirm — confirm/retract (PLANT_INCHARGE + ADMIN only)
  plant_workflow:request — submit/withdraw adjustment (PLANT_INCHARGE + ADMIN only)
  plant_workflow:admin   — assign/remove user↔plant (ADMIN only, uses existing ADMIN permission)
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.plant_workflow import (
    ConfirmRequirementRequest,
    PlantConfirmationResponse,
    RequirementAdjustmentResponse,
    SubmitAdjustmentRequest,
    UserPlantAssignRequest,
    UserPlantResponse,
)
from app.security.permissions import require_permissions
from app.services.plant_workflow import (
    assign_user_to_plant,
    confirm_requirement,
    list_adjustments,
    list_confirmations,
    list_user_plants,
    remove_user_from_plant,
    retract_confirmation,
    submit_adjustment,
    withdraw_adjustment,
)

router = APIRouter(prefix="/plant-workflow", tags=["plant-workflow"])


# ── User↔Plant assignment (ADMIN) ──────────────────────────────────────────────

@router.post(
    "/user-plants",
    response_model=UserPlantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a user to a plant",
)
def post_assign_user_plant(
    req: UserPlantAssignRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("admin:manage"))],
) -> UserPlantResponse:
    return assign_user_to_plant(session, req, current_user)


@router.get(
    "/user-plants/{user_id}",
    response_model=list[UserPlantResponse],
    summary="List plants assigned to a user",
)
def get_user_plants(
    user_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("admin:manage"))],
) -> list[UserPlantResponse]:
    return list_user_plants(session, user_id)


@router.delete(
    "/user-plants/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a user from a plant",
)
def delete_user_plant(
    assignment_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("admin:manage"))],
) -> None:
    remove_user_from_plant(session, assignment_id, current_user)


# ── Plant Confirmations ────────────────────────────────────────────────────────

@router.get(
    "/confirmations",
    response_model=list[PlantConfirmationResponse],
    summary="List plant confirmations",
)
def get_confirmations(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:view"))],
    planning_version_id: Optional[UUID] = Query(None),
    plant_id: Optional[UUID] = Query(None),
) -> list[PlantConfirmationResponse]:
    return list_confirmations(
        session,
        planning_version_id=planning_version_id,
        plant_id=plant_id,
    )


@router.post(
    "/confirmations",
    response_model=PlantConfirmationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm a calculated requirement",
)
def post_confirm_requirement(
    req: ConfirmRequirementRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:confirm"))],
) -> PlantConfirmationResponse:
    return confirm_requirement(session, req, current_user)


@router.delete(
    "/confirmations/{confirmation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retract a plant confirmation",
)
def delete_confirmation(
    confirmation_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:confirm"))],
) -> None:
    retract_confirmation(session, confirmation_id, current_user)


# ── Requirement Adjustments ────────────────────────────────────────────────────

@router.get(
    "/adjustments",
    response_model=list[RequirementAdjustmentResponse],
    summary="List additional requirement adjustments",
)
def get_adjustments(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:view"))],
    planning_version_id: Optional[UUID] = Query(None),
    plant_id: Optional[UUID] = Query(None),
    adjustment_status: Optional[str] = Query(None, alias="status"),
) -> list[RequirementAdjustmentResponse]:
    return list_adjustments(
        session,
        planning_version_id=planning_version_id,
        plant_id=plant_id,
        status=adjustment_status,
    )


@router.post(
    "/adjustments",
    response_model=RequirementAdjustmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an additional requirement adjustment",
)
def post_submit_adjustment(
    req: SubmitAdjustmentRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:request"))],
) -> RequirementAdjustmentResponse:
    return submit_adjustment(session, req, current_user)


@router.delete(
    "/adjustments/{adjustment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw a pending adjustment (requester only)",
)
def delete_adjustment(
    adjustment_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("plant_workflow:request"))],
) -> None:
    withdraw_adjustment(session, adjustment_id, current_user)
