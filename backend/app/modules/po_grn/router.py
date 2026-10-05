from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApplicationError
from app.db.session import session_scope
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.purchase_order import DemandSubmission, DemandSubmissionResponse, EligibleDemand, OrderAction, OrderCreate, OrderResponse
from app.security.permissions import require_permissions
from app.services import purchase_order as service


def order_database(request: Request):
    try:
        with session_scope(request.app.state.session_factory) as session:
            if session.get_bind().dialect.name == 'postgresql':
                session.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
            yield session
    except SQLAlchemyError:
        raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None


Database = Annotated[Session, Depends(order_database)]
Read = Annotated[CurrentUser, Depends(require_permissions('purchase.orders.read'))]
Create = Annotated[CurrentUser, Depends(require_permissions('purchase.orders.create'))]
Issue = Annotated[CurrentUser, Depends(require_permissions('purchase.orders.issue'))]
Cancel = Annotated[CurrentUser, Depends(require_permissions('purchase.orders.cancel'))]
Submit = Annotated[CurrentUser, Depends(require_permissions('purchase.demand.submit', 'inventory.projection.read'))]
router = APIRouter(prefix='/purchase-orders', tags=['purchase orders'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})


@router.post('/demand', status_code=201, response_model=DemandSubmissionResponse)
def submit(data: DemandSubmission, response: Response, user: Submit, session: Database):
    result = service.submit_demand(session, data, user.id)
    if result['replayed']:
        response.status_code = 200
    return result


@router.get('/eligible', response_model=list[EligibleDemand])
def eligible(user: Read, session: Database, limit: Annotated[int, Query(ge=1, le=100)] = 25,
             offset: Annotated[int, Query(ge=0)] = 0):
    return service.eligible(session, limit, offset)


@router.get('', response_model=list[OrderResponse])
def listing(user: Read, session: Database, limit: Annotated[int, Query(ge=1, le=100)] = 25,
            offset: Annotated[int, Query(ge=0)] = 0):
    return service.list_orders(session, limit, offset)


@router.post('', response_model=OrderResponse, status_code=201)
def create(data: OrderCreate, response: Response, user: Create, session: Database):
    result = service.create(session, data, user.id, 'purchase.orders.price' in user.permissions)
    if result.replayed:
        response.status_code = 200
    return result


@router.get('/{identity}', response_model=OrderResponse)
def detail(identity: UUID, user: Read, session: Database):
    return service.get(session, identity)


@router.post('/{identity}/issue', response_model=OrderResponse)
def issue(identity: UUID, data: OrderAction, user: Issue, session: Database):
    return service.transition(session, identity, 'ISSUE', data, user.id)


@router.post('/{identity}/cancel', response_model=OrderResponse)
def cancel(identity: UUID, data: OrderAction, user: Cancel, session: Database):
    return service.transition(session, identity, 'CANCEL', data, user.id)
