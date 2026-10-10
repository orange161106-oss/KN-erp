from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApplicationError
from app.db.session import session_scope
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.inventory import Timestamp
from app.schemas.projection import ProjectionCapability, ProjectionImportResult, ProjectionInputs, ProjectionReport
from app.security.permissions import require_permissions
from app.services import projection as service


def projection_database(request: Request):
    # Separate from the authentication transaction: establish isolation before any
    # source reads, so totals, approval evidence and stock form one consistent view.
    try:
        with session_scope(request.app.state.session_factory) as session:
            if session.get_bind().dialect.name == 'postgresql':
                session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            yield session
    except SQLAlchemyError:
        raise ApplicationError('DATABASE_UNAVAILABLE', 'Database is unavailable.', 503) from None


router = APIRouter(prefix='/inventory/projections', tags=['projected inventory'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})
Read = Annotated[CurrentUser, Depends(require_permissions('inventory.projection.read'))]
Import = Annotated[CurrentUser, Depends(require_permissions('inventory.projection.import'))]
Database = Annotated[Session, Depends(projection_database)]


@router.get('/status', response_model=ProjectionCapability)
def capability(request: Request, user: Read):
    return ProjectionCapability(import_enabled=request.app.state.settings.projection_import_enabled)


@router.get('', response_model=ProjectionReport)
def project(consumable_id: UUID, planning_version_id: UUID, cutoff: Timestamp, user: Read, session: Database,
            source_set_id: Annotated[str | None, Query(min_length=1, max_length=192)] = None):
    return service.report(session, consumable_id, planning_version_id, cutoff, source_set_id)


@router.post('/inputs', response_model=ProjectionImportResult, status_code=201)
def import_inputs(data: ProjectionInputs, request: Request, response: Response, user: Import, session: Database):
    result = service.import_inputs(session, data, user.id, enabled=request.app.state.settings.projection_import_enabled)
    if result.replayed:
        response.status_code = 200
    return result
