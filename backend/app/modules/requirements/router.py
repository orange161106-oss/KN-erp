from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirements import (
    CalculatedRequirementResponse,
    CalculationRunRequest,
    RequirementCalculationErrorResponse,
    RequirementCalculationRunResponse,
)
from app.security.dependencies import get_current_user
from app.services.requirements import (
    calculate_planning_version_requirements,
    get_calculated_requirements,
    get_calculation_errors,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.post(
    "/calculate",
    response_model=RequirementCalculationRunResponse,
    status_code=status.HTTP_200_OK,
)
def post_calculate_requirements(
    req: CalculationRunRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RequirementCalculationRunResponse:
    return calculate_planning_version_requirements(session, req, current_user.id)


@router.get(
    "/planning-versions/{planning_version_id}",
    response_model=list[CalculatedRequirementResponse],
)
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
)
def get_version_calculation_errors(
    planning_version_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[RequirementCalculationErrorResponse]:
    return get_calculation_errors(session, planning_version_id=planning_version_id)

