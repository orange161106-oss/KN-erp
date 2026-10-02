from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.rules import (
    ConsumptionNormCreate,
    ConsumptionNormResponse,
    ConsumptionNormUpdate,
    EvaluationRequest,
    EvaluationResponse,
)
from app.security.dependencies import get_current_user
from app.services.rules import (
    create_consumption_norm,
    evaluate_consumption_norm,
    get_consumption_norm,
    list_consumption_norms,
    update_consumption_norm,
)

router = APIRouter(prefix="/consumption-norms", tags=["consumption norms"])


@router.get("", response_model=list[ConsumptionNormResponse])
def get_consumption_norms(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    consumable_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
    process_id: Optional[UUID] = Query(None),
    plant_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> list[ConsumptionNormResponse]:
    return list_consumption_norms(
        session,
        consumable_id=consumable_id,
        product_id=product_id,
        process_id=process_id,
        plant_id=plant_id,
        is_active=is_active,
    )


@router.get("/{norm_id}", response_model=ConsumptionNormResponse)
def get_single_consumption_norm(
    norm_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return get_consumption_norm(session, norm_id)


@router.post("", response_model=ConsumptionNormResponse, status_code=status.HTTP_201_CREATED)
def post_consumption_norm(
    data: ConsumptionNormCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return create_consumption_norm(session, data)


@router.put("/{norm_id}", response_model=ConsumptionNormResponse)
def put_consumption_norm(
    norm_id: UUID,
    data: ConsumptionNormUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return update_consumption_norm(session, norm_id, data)


@router.post("/evaluate", response_model=EvaluationResponse)
def post_evaluate_norm(
    req: EvaluationRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> EvaluationResponse:
    return evaluate_consumption_norm(session, req)
