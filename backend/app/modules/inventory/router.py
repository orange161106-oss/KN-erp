from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.inventory_engine.ledger import Movement
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.inventory import Balance, ImportResult, InventoryStatus, SourceImport, Timestamp, TransactionResponse
from app.schemas.inventory_masters import Page
from app.security.permissions import require_permissions
from app.services import inventory as service

router = APIRouter(prefix="/inventory", tags=["central inventory"], responses={
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
})
Read = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.read"))]
Import = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.import"))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/status", response_model=InventoryStatus)
def status(request: Request, user: Read):
    return InventoryStatus(import_enabled=request.app.state.settings.inventory_import_enabled)


@router.get("/balances", response_model=Page[Balance])
def balances(session: Database, user: Read, limit: Annotated[int, Query(ge=1, le=100)] = 25,
             offset: Annotated[int, Query(ge=0)] = 0, q: Annotated[str | None, Query(max_length=100)] = None,
             is_active: bool | None = None):
    return service.list_balances(session, limit=limit, offset=offset, q=q, is_active=is_active)


@router.get("/balances/{consumable_id}", response_model=Balance)
def balance(consumable_id: UUID, session: Database, user: Read):
    return service.get_balance(session, consumable_id)


@router.get("/transactions", response_model=Page[TransactionResponse])
def history(session: Database, user: Read, limit: Annotated[int, Query(ge=1, le=100)] = 25,
            offset: Annotated[int, Query(ge=0)] = 0, consumable_id: UUID | None = None,
            movement: Movement | None = None, since: Timestamp | None = None, until: Timestamp | None = None):
    return service.list_transactions(session, limit=limit, offset=offset, consumable_id=consumable_id,
                                     movement=movement, since=since, until=until)


@router.post("/imports", response_model=ImportResult, status_code=201)
def import_source(data: SourceImport, request: Request, response: Response, session: Database, user: Import):
    result = service.import_source(session, data, user.id, enabled=request.app.state.settings.inventory_import_enabled)
    if result.replayed:
        response.status_code = 200
    return result
