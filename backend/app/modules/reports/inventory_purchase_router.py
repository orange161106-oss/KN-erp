from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApplicationError
from app.modules.inventory.projection_router import Database
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.inventory import Balance, Timestamp
from app.schemas.inventory_masters import Page
from app.schemas.inventory_purchase_reports import GRNReportPage, PurchaseFlowPage, ReportOption
from app.schemas.projection import ProjectionReport
from app.schemas.purchase_recommendation import PurchaseReport, PurchaseRequest
from app.schemas.reorder import ReorderReport, ReorderRequest
from app.security.dependencies import get_current_user
from app.security.permissions import require_permissions
from app.services import inventory_purchase_reports as service

router = APIRouter(prefix='/reports', tags=['inventory and purchase reports'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})
InventoryRead = Annotated[CurrentUser, Depends(require_permissions('reports.inventory.read'))]
PurchaseRead = Annotated[CurrentUser, Depends(require_permissions('reports.purchase.read'))]


def any_report_read(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if not {'reports.inventory.read', 'reports.purchase.read'}.intersection(user.permissions):
        raise ApplicationError('PERMISSION_DENIED', 'Required report permission is missing.', 403)
    return user


AnyReportRead = Annotated[CurrentUser, Depends(any_report_read)]


@router.get('/options/materials', response_model=list[ReportOption])
def material_options(session: Database, user: AnyReportRead, q: Annotated[str | None, Query(max_length=100)] = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return service.materials(session, q, limit)


@router.get('/options/suppliers', response_model=list[ReportOption])
def supplier_options(session: Database, user: PurchaseRead, q: Annotated[str | None, Query(max_length=100)] = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return service.suppliers(session, q, limit)


@router.get('/options/planning-versions', response_model=list[ReportOption])
def version_options(session: Database, user: AnyReportRead, q: Annotated[str | None, Query(max_length=100)] = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return service.planning_versions(session, q, limit)


@router.get('/material-stock', response_model=Page[Balance])
def material_stock(session: Database, user: InventoryRead,
                   limit: Annotated[int, Query(ge=1, le=100)] = 25,
                   offset: Annotated[int, Query(ge=0)] = 0,
                   q: Annotated[str | None, Query(max_length=100)] = None,
                   is_active: bool | None = None):
    return service.stock(session, limit=limit, offset=offset, q=q, is_active=is_active)


@router.get('/projected-shortage', response_model=ProjectionReport)
def projected_shortage(session: Database, user: InventoryRead, consumable_id: UUID,
                       planning_version_id: UUID, cutoff: Timestamp,
                       source_set_id: Annotated[str | None, Query(min_length=1, max_length=192)] = None):
    # Return M4.2's entire authoritative timeline/explanation; the report does not
    # re-derive shortage or hide events/limitations from consumers.
    return service.projection_report(session, consumable_id, planning_version_id, cutoff, source_set_id)


@router.post('/msl-reorder-assessment', response_model=ReorderReport)
def msl_reorder(data: ReorderRequest, user: InventoryRead, session: Database):
    return service.reorder_report(session, data)


@router.post('/purchase-recommendation-assessment', response_model=PurchaseReport)
def purchase_assessment(data: PurchaseRequest, user: PurchaseRead, session: Database):
    return service.purchase_assessment(session, data)


def _purchase_flow(session, *, supplier_id, consumable_id, planning_version_id,
                   approval_status, po_status, po_date_from, po_date_until,
                   submitted_from, submitted_until, pending_only, limit, offset):
    if submitted_from and submitted_until and submitted_from >= submitted_until:
        raise ApplicationError('INVALID_DATE_RANGE', 'Submitted-from must precede submitted-until; the upper bound is exclusive.', 422)
    return service.purchase_flow(session, supplier_id=supplier_id, consumable_id=consumable_id,
        planning_version_id=planning_version_id, approval_status=approval_status,
        po_status=po_status, po_date_from=po_date_from, po_date_until=po_date_until,
        submitted_from=submitted_from, submitted_until=submitted_until,
        pending_only=pending_only, limit=limit, offset=offset)


@router.get('/supplier-purchase-plan', response_model=PurchaseFlowPage)
def supplier_purchase_plan(session: Database, user: PurchaseRead,
        supplier_id: UUID | None = None, consumable_id: UUID | None = None,
        planning_version_id: UUID | None = None,
        approval_status: Literal['PENDING', 'APPROVED', 'MODIFIED', 'REJECTED'] | None = None,
        po_status: Literal['DRAFT', 'ISSUED', 'CANCELLED'] | None = None,
        po_date_from: date | None = None, po_date_until: date | None = None,
        submitted_from: Timestamp | None = None, submitted_until: Timestamp | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0)] = 0):
    return _purchase_flow(session, supplier_id=supplier_id, consumable_id=consumable_id,
        planning_version_id=planning_version_id, approval_status=approval_status,
        po_status=po_status, po_date_from=po_date_from, po_date_until=po_date_until,
        submitted_from=submitted_from, submitted_until=submitted_until,
        pending_only=False, limit=limit, offset=offset)


@router.get('/pending-purchase-orders', response_model=PurchaseFlowPage)
def pending_purchase_orders(session: Database, user: PurchaseRead,
        supplier_id: UUID | None = None, consumable_id: UUID | None = None,
        po_date_from: date | None = None, po_date_until: date | None = None,
        submitted_from: Timestamp | None = None, submitted_until: Timestamp | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0)] = 0):
    return _purchase_flow(session, supplier_id=supplier_id, consumable_id=consumable_id,
        planning_version_id=None, approval_status=None, po_status='ISSUED',
        po_date_from=po_date_from, po_date_until=po_date_until, submitted_from=submitted_from,
        submitted_until=submitted_until, pending_only=True, limit=limit, offset=offset)


@router.get('/recommendation-fulfilment', response_model=PurchaseFlowPage)
def recommendation_fulfilment(session: Database, user: PurchaseRead,
        supplier_id: UUID | None = None, consumable_id: UUID | None = None,
        planning_version_id: UUID | None = None,
        approval_status: Literal['PENDING', 'APPROVED', 'MODIFIED', 'REJECTED'] | None = None,
        po_status: Literal['DRAFT', 'ISSUED', 'CANCELLED'] | None = None,
        po_date_from: date | None = None, po_date_until: date | None = None,
        submitted_from: Timestamp | None = None, submitted_until: Timestamp | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0)] = 0):
    return _purchase_flow(session, supplier_id=supplier_id, consumable_id=consumable_id,
        planning_version_id=planning_version_id, approval_status=approval_status,
        po_status=po_status, po_date_from=po_date_from, po_date_until=po_date_until,
        submitted_from=submitted_from, submitted_until=submitted_until,
        pending_only=False, limit=limit, offset=offset)


@router.get('/grns', response_model=GRNReportPage)
def grn_history(session: Database, user: PurchaseRead,
        supplier_id: UUID | None = None, consumable_id: UUID | None = None,
        purchase_order_id: UUID | None = None, event_from: Timestamp | None = None,
        event_until: Timestamp | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0)] = 0):
    return service.grn_history(session, supplier_id=supplier_id, consumable_id=consumable_id,
        purchase_order_id=purchase_order_id, event_from=event_from, event_until=event_until,
        limit=limit, offset=offset)
