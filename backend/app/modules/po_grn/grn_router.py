from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.modules.po_grn.router import Database
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.grn import GRNImport, GRNResponse
from app.security.permissions import require_permissions
from app.services import grn as service

router = APIRouter(prefix='/grns', tags=['imported GRNs'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})
Read = Annotated[CurrentUser, Depends(require_permissions('purchase.grns.read'))]
Import = Annotated[CurrentUser, Depends(require_permissions('purchase.grns.import', 'inventory.stock.import'))]


@router.post('/imports', response_model=GRNResponse, status_code=201)
def import_grn(data: GRNImport, request: Request, response: Response, user: Import, session: Database):
    result = service.import_grn(session, data, user.id, enabled=request.app.state.settings.inventory_import_enabled)
    if result.replayed:
        response.status_code = 200
    return result


@router.get('', response_model=list[GRNResponse])
def listing(user: Read, session: Database, limit: Annotated[int, Query(ge=1, le=100)] = 25,
            offset: Annotated[int, Query(ge=0)] = 0, purchase_order_id: UUID | None = None):
    return service.listing(session, limit, offset, purchase_order_id)


@router.get('/{identity}', response_model=GRNResponse)
def detail(identity: UUID, user: Read, session: Database):
    return service.get(session, identity)
