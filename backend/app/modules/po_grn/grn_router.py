from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.core.errors import ApplicationError
from app.modules.po_grn.router import Database
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.grn import (
    GRNImport,
    GRNResponse,
    GoodsReceiptRecordResponse,
    WorkspaceSaveRequest,
    WorkspaceSaveResponse,
    WorkspaceBulkDeleteRequest,
    WorkspaceBulkDeleteResponse,
    ExcelInspectResponse,
    ExcelImportSheetResponse,
)
from app.security.dependencies import get_current_user
from app.security.permissions import require_permissions
from app.security.policy import allows
from app.services import grn as service

router = APIRouter(prefix='/grns', tags=['imported GRNs'], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})
Read = Annotated[CurrentUser, Depends(require_permissions('purchase.grns.read'))]
Import = Annotated[CurrentUser, Depends(require_permissions('purchase.grns.import', 'inventory.stock.import'))]


def require_any_permission(*codes: str):
    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.is_super_admin or "ADMIN" in user.roles:
            return user
        if any(getattr(user, f"goods_receipts_{op}", False) for op in ("read", "create", "update", "delete")):
            return user
        if any(code in user.permissions for code in codes):
            return user
        raise ApplicationError("PERMISSION_DENIED", f"Required permission missing. Needs one of: {', '.join(codes)}.", 403)
    return dependency


SaveWorkspace = Annotated[CurrentUser, Depends(require_any_permission('purchase.grns.update', 'purchase.grns.create', 'purchase.grns.import'))]
DeleteWorkspace = Annotated[CurrentUser, Depends(require_any_permission('purchase.grns.delete', 'purchase.grns.update'))]
ExportWorkspace = Annotated[CurrentUser, Depends(require_any_permission('purchase.grns.export', 'purchase.grns.read'))]
ImportWorkspace = Annotated[CurrentUser, Depends(require_any_permission('purchase.grns.import', 'purchase.grns.create'))]


@router.post('/imports', response_model=GRNResponse, status_code=201)
def import_grn(data: GRNImport, request: Request, response: Response, user: Import, session: Database):
    result = service.import_grn(session, data, user.id, enabled=request.app.state.settings.inventory_import_enabled)
    if result.replayed:
        response.status_code = 200
    return result


@router.get('/workspace/records', response_model=list[GoodsReceiptRecordResponse])
def get_workspace_records(
    user: Read,
    session: Database,
    search: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_workspace_records(session, search=search, status=status, limit=limit, offset=offset)


@router.post('/workspace/save', response_model=WorkspaceSaveResponse)
def save_workspace_records(
    data: WorkspaceSaveRequest,
    user: SaveWorkspace,
    session: Database,
):
    return service.save_workspace_records(session, data, user.id)


@router.delete('/workspace/records/{identity}', status_code=204)
def delete_workspace_record(
    identity: UUID,
    user: DeleteWorkspace,
    session: Database,
    reason: str = Query(default='Deleted via Excel workspace'),
):
    service.delete_workspace_record(session, identity, user.id, reason=reason)
    return Response(status_code=204)


@router.post('/workspace/bulk-delete', response_model=WorkspaceBulkDeleteResponse)
def bulk_delete_workspace(
    data: WorkspaceBulkDeleteRequest,
    user: DeleteWorkspace,
    session: Database,
):
    count = service.bulk_delete_workspace_records(
        session,
        ids=data.ids,
        delete_all_matching=data.delete_all_matching,
        search=data.search,
        status=data.status,
        actor=user.id,
        reason=data.reason,
    )
    return WorkspaceBulkDeleteResponse(deleted_count=count)


@router.post('/workspace/inspect', response_model=ExcelInspectResponse)
async def inspect_excel_file(
    user: ImportWorkspace,
    file: UploadFile = File(...),
):
    contents = await file.read()
    return service.inspect_excel_file(contents, file.filename or 'upload.xlsx')


@router.post('/workspace/import-sheet', response_model=ExcelImportSheetResponse)
async def import_workspace_sheet(
    user: ImportWorkspace,
    session: Database,
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    mode: str = Form(default='APPEND'),
    reason: str = Form(default='Excel sheet import'),
):
    contents = await file.read()
    return service.import_excel_sheet(session, contents, file.filename or 'upload.xlsx', sheet_name, user.id, mode=mode, reason=reason)


@router.get('/workspace/export')
def export_workspace_excel(
    user: ExportWorkspace,
    session: Database,
    search: str | None = None,
    status: str | None = None,
    record_ids: Annotated[list[UUID] | None, Query()] = None,
):
    excel_bytes = service.export_workspace_excel(session, search=search, status=status, record_ids=record_ids)
    return Response(
        content=excel_bytes,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="goods_receipts_workspace.xlsx"'},
    )


@router.post('/workspace/export')
def export_workspace_excel_post(
    data: dict[str, list[str]],
    user: ExportWorkspace,
    session: Database,
):
    raw_ids = data.get('record_ids', [])
    ids = [UUID(i) for i in raw_ids if i]
    excel_bytes = service.export_workspace_excel(session, record_ids=ids if ids else None)
    return Response(
        content=excel_bytes,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="goods_receipts_workspace.xlsx"'},
    )


@router.get('', response_model=list[GRNResponse])
def listing(user: Read, session: Database, limit: Annotated[int, Query(ge=1, le=100)] = 25,
            offset: Annotated[int, Query(ge=0)] = 0, purchase_order_id: UUID | None = None):
    return service.listing(session, limit, offset, purchase_order_id)


@router.get('/{identity}', response_model=GRNResponse)
def detail(identity: UUID, user: Read, session: Database):
    return service.get(session, identity)

