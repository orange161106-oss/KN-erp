from fastapi import APIRouter

from app.modules.inventory.projection_router import Database, Read
from app.schemas.error import ErrorResponse
from app.schemas.reorder import ReorderReport, ReorderRequest
from app.services import reorder as service

router = APIRouter(prefix='/inventory/reorder', tags=['reorder timing'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})


@router.post('/assess', response_model=ReorderReport)
def assess(data: ReorderRequest, user: Read, session: Database):
    return service.report(session, data)
