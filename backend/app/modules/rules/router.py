from app.security.permissions import require_permissions
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.rules import (
    ConsumptionNormCreate,
    ConsumptionNormResponse,
    ConsumptionNormUpdate,
    EvaluationRequest,
    EvaluationResponse,
    ItemCalculationRequest,
    SingleRequirementCalculationResponse,
    ConsumptionNormBatchUpdate,
    ConsumptionNormBatchResponse,
)
from app.schemas.norm_imports import NormImportCorrections, NormImportReview, NormImportPreview, NormImportResult
from app.core.errors import ApplicationError
from app.services import norm_imports
from app.security.dependencies import get_current_user
from app.services.rules import (
    calculate_single_item_requirement,
    create_consumption_norm,
    evaluate_consumption_norm,
    get_consumption_norm,
    list_consumption_norms,
    update_consumption_norm,
    bulk_update_consumption_norms,
)

router = APIRouter(prefix="/consumption-norms", tags=["consumption norms"])


def require_norm_permission(operation):
    """A read flag cannot authorize a write; keep this fix local to norms."""
    def permission(user: Annotated[CurrentUser, Depends(get_current_user)]):
        if user.is_super_admin or getattr(user, f"consumption_norms_{operation}", False):
            return user
        raise ApplicationError("PERMISSION_DENIED", f"Consumption norms {operation} permission is required.", 403)
    return permission


def _review(model, raw):
    try:
        return model.model_validate_json(raw)
    except (ValueError, ValidationError):
        raise ApplicationError("INVALID_NORM_REVIEW", "Review data is invalid. Reload the preview and review every source row.", 422) from None


@router.get("/template", dependencies=[Depends(require_norm_permission("read"))])
def download_norm_template(format: str = Query("xlsx")):
    content, media = norm_imports.export_file(format=format, template=True)
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="consumption-norms-template.{format}"'})


@router.get("/export", dependencies=[Depends(require_norm_permission("read"))])
def export_norms(session: Annotated[Session, Depends(get_db)], format: str = Query("xlsx")):
    content, media = norm_imports.export_file(session, format)
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="consumption-norms.{format}"'})


@router.post("/import-preview", response_model=NormImportPreview, dependencies=[Depends(require_norm_permission("create"))])
async def preview_norm_import(session: Annotated[Session, Depends(get_db)], file: UploadFile = File(...), review: Optional[str] = Form(None)):
    content = await file.read(norm_imports.MAX_BYTES + 1)
    corrections = _review(NormImportCorrections, review) if review else None
    return norm_imports.preview(session, file.filename or "", content, corrections)


@router.post("/import-confirm", response_model=NormImportResult, dependencies=[Depends(require_norm_permission("create"))])
async def confirm_norm_import(session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)], file: UploadFile = File(...), review: str = Form(...)):
    checked = _review(NormImportReview, review)
    if checked.mode == "SUPERSEDE":
        require_norm_permission("update")(current_user)
    return norm_imports.confirm(session, file.filename or "", await file.read(norm_imports.MAX_BYTES + 1), checked, current_user.id)


@router.post("/bulk-update", response_model=ConsumptionNormBatchResponse, dependencies=[Depends(require_norm_permission("update"))])
def update_norm_batch(data: ConsumptionNormBatchUpdate, session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    return bulk_update_consumption_norms(session, data, current_user.id)


@router.get("", response_model=list[ConsumptionNormResponse], dependencies=[Depends(require_norm_permission("read"))])
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


@router.get("/{norm_id}", response_model=ConsumptionNormResponse, dependencies=[Depends(require_norm_permission("read"))])
def get_single_consumption_norm(
    norm_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return get_consumption_norm(session, norm_id)


@router.post("", response_model=ConsumptionNormResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_norm_permission("create"))])
def post_consumption_norm(
    data: ConsumptionNormCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return create_consumption_norm(session, data, actor_id=current_user.id)


@router.put("/{norm_id}", response_model=ConsumptionNormResponse, dependencies=[Depends(require_norm_permission("update"))])
def put_consumption_norm(
    norm_id: UUID,
    data: ConsumptionNormUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConsumptionNormResponse:
    return update_consumption_norm(session, norm_id, data, actor_id=current_user.id)


@router.post("/evaluate", response_model=EvaluationResponse, dependencies=[Depends(require_permissions('requirements.calculate'))])
def post_evaluate_norm(
    req: EvaluationRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> EvaluationResponse:
    return evaluate_consumption_norm(session, req)


@router.post("/calculate-item", response_model=SingleRequirementCalculationResponse, dependencies=[Depends(require_permissions('requirements.calculate'))])
def post_calculate_item(
    req: ItemCalculationRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SingleRequirementCalculationResponse:
    return calculate_single_item_requirement(session, req)

