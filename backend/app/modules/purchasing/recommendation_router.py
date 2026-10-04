from fastapi import APIRouter

from app.modules.inventory.projection_router import Database, Read
from app.schemas.error import ErrorResponse
from app.schemas.purchase_recommendation import PurchaseReport, PurchaseRequest
from app.services import purchase_recommendation as service

router = APIRouter(prefix='/purchasing/recommendations', tags=['purchase recommendations'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})


@router.post('/assess', response_model=PurchaseReport)
def assess(data: PurchaseRequest, user: Read, session: Database):
    return service.report(session, data)
