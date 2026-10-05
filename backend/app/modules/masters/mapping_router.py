from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.mappings import (
    BulkMappingResponse,
    BulkProductPlantCreate,
    BulkProductProcessConsumableCreate,
    MappingValidationReport,
    ProductPlantCreate,
    ProductPlantResponse,
    ProductPlantUpdate,
    ProductProcessConsumableCreate,
    ProductProcessConsumableResponse,
    ProductProcessConsumableUpdate,
    ProductResolutionResponse,
)
from app.security.dependencies import get_current_user
from app.services.mappings import (
    bulk_create_product_plants,
    bulk_create_product_process_consumables,
    create_product_plant_mapping,
    create_product_process_consumable_mapping,
    get_product_plant_mapping,
    get_product_process_consumable_mapping,
    list_product_plant_mappings,
    list_product_process_consumable_mappings,
    resolve_product_mapping,
    update_product_plant_mapping,
    update_product_process_consumable_mapping,
    validate_mappings,
)

router = APIRouter(prefix="/mappings", tags=["mappings"])


# ==========================================
# Product-Plant Endpoints
# ==========================================

@router.get("/product-plants", response_model=list[ProductPlantResponse])
def get_product_plants(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    product_id: Optional[UUID] = Query(None),
    plant_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> list[ProductPlantResponse]:
    return list_product_plant_mappings(
        session, product_id=product_id, plant_id=plant_id, is_active=is_active
    )


@router.get("/product-plants/{mapping_id}", response_model=ProductPlantResponse)
def get_product_plant(
    mapping_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductPlantResponse:
    return get_product_plant_mapping(session, mapping_id)


@router.post(
    "/product-plants",
    response_model=ProductPlantResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product_plant(
    data: ProductPlantCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductPlantResponse:
    return create_product_plant_mapping(session, data)


@router.post(
    "/product-plants/bulk",
    response_model=BulkMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product_plants_bulk(
    data: BulkProductPlantCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BulkMappingResponse:
    return bulk_create_product_plants(session, data)


@router.put("/product-plants/{mapping_id}", response_model=ProductPlantResponse)
def put_product_plant(
    mapping_id: UUID,
    data: ProductPlantUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductPlantResponse:
    return update_product_plant_mapping(session, mapping_id, data)


# ==========================================
# Product-Process-Consumable Endpoints
# ==========================================

@router.get(
    "/product-process-consumables",
    response_model=list[ProductProcessConsumableResponse],
)
def get_product_process_consumables(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    product_id: Optional[UUID] = Query(None),
    process_id: Optional[UUID] = Query(None),
    consumable_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> list[ProductProcessConsumableResponse]:
    return list_product_process_consumable_mappings(
        session,
        product_id=product_id,
        process_id=process_id,
        consumable_id=consumable_id,
        is_active=is_active,
    )


@router.get(
    "/product-process-consumables/{mapping_id}",
    response_model=ProductProcessConsumableResponse,
)
def get_product_process_consumable(
    mapping_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductProcessConsumableResponse:
    return get_product_process_consumable_mapping(session, mapping_id)


@router.post(
    "/product-process-consumables",
    response_model=ProductProcessConsumableResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product_process_consumable(
    data: ProductProcessConsumableCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductProcessConsumableResponse:
    return create_product_process_consumable_mapping(session, data)


@router.post(
    "/product-process-consumables/bulk",
    response_model=BulkMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product_process_consumables_bulk(
    data: BulkProductProcessConsumableCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BulkMappingResponse:
    return bulk_create_product_process_consumables(session, data)


@router.put(
    "/product-process-consumables/{mapping_id}",
    response_model=ProductProcessConsumableResponse,
)
def put_product_process_consumable(
    mapping_id: UUID,
    data: ProductProcessConsumableUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductProcessConsumableResponse:
    return update_product_process_consumable_mapping(session, mapping_id, data)


# ==========================================
# Phase 2 Gate Resolution & Validation Endpoints
# ==========================================

@router.get("/resolve/{product_id}", response_model=ProductResolutionResponse)
def get_resolve_product_mapping(
    product_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    plant_id: Optional[UUID] = Query(None),
) -> ProductResolutionResponse:
    return resolve_product_mapping(session, product_id=product_id, plant_id=plant_id)


@router.get("/validate", response_model=MappingValidationReport)
def get_validate_mappings(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    product_id: Optional[UUID] = Query(None),
) -> MappingValidationReport:
    return validate_mappings(session, product_id=product_id)
