from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user
from app.services import product_master_service as service

router = APIRouter(prefix="/masters/product-master", tags=["product-master"])


# ---------------------------------------------------------------------------
# Tab 1: List of Consumables
# ---------------------------------------------------------------------------

@router.post("/consumables/single", status_code=status.HTTP_201_CREATED)
def create_single_consumable(
    data: service.ConsumableSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.upsert_single_consumable(session, data, current_user.id)


@router.post("/consumables/bulk")
async def bulk_upload_consumables(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    return service.bulk_upsert_consumables(session, contents, current_user.id)


@router.get("/consumables")
def get_consumables(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_consumables_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Tab 2: List of Sales Parts
# ---------------------------------------------------------------------------

@router.post("/sales-parts/single", status_code=status.HTTP_201_CREATED)
def create_single_sales_part(
    data: service.SalesPartSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.upsert_single_sales_part(session, data, current_user.id)


@router.post("/sales-parts/bulk")
async def bulk_upload_sales_parts(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    return service.bulk_upsert_sales_parts(session, contents, current_user.id)


@router.get("/sales-parts")
def get_sales_parts(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_sales_parts_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Tab 3: Consumable for Assemble (BOM)
# ---------------------------------------------------------------------------

@router.post("/assemble/single", status_code=status.HTTP_201_CREATED)
def create_single_assemble(
    data: service.AssembleSingleCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.upsert_single_assemble(session, data, current_user.id)


@router.post("/assemble/bulk")
async def bulk_upload_assemble(
    file: UploadFile = File(...),
    session: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    contents = await file.read(15 * 1024 * 1024 + 1)
    return service.bulk_upsert_assemble(session, contents, current_user.id)


@router.get("/assemble")
def get_assemble_mappings(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return service.list_assemble_table(session, q=q, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Item Update & Soft-Delete (Deactivate) Endpoints
# ---------------------------------------------------------------------------

@router.put("/{category}/{item_id}")
def update_master_item(
    category: str,
    item_id: UUID,
    payload: dict,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.update_product_master_item(session, category, item_id, payload, current_user.id)


@router.patch("/{category}/{item_id}/deactivate")
def deactivate_master_item(
    category: str,
    item_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.deactivate_product_master_item(session, category, item_id, current_user.id)


@router.delete("/{category}/{item_id}")
def delete_master_item(
    category: str,
    item_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    return service.deactivate_product_master_item(session, category, item_id, current_user.id)

