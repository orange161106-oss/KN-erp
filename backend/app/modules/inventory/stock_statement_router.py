import io
import time
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.stock_statements import (
    DemoteConsumableRequest,
    DemoteConsumableResponse,
    MissingConsumablesResponse,
    PromoteConsumablesRequest,
    PromoteConsumablesResponse,
    StockStatementConfirmRequest,
    StockStatementBatchUpdateRequest,
    StockStatementDeleteRequest,
    StockStatementDeleteResponse,
    StockStatementHistoryItem,
    StockStatementPreviewResponse,
    StockStatementResponse,
)
from app.security.permissions import require_feature_flag, require_permissions
from app.services import stock_statement_service as service

router = APIRouter(
    prefix="/inventory/statement",
    tags=["stock-statement"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500)},
)

ReadUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.read", "inventory.read"))]
ImportUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.import", "inventory.create", "inventory.update"))]
PromoteUser = Annotated[CurrentUser, Depends(require_permissions("masters.consumable.create", "masters.create", "inventory.update"))]
DeleteUser = Annotated[CurrentUser, Depends(require_feature_flag("inventory_delete"))]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=StockStatementResponse)
@router.get("/", response_model=StockStatementResponse, include_in_schema=False)
def get_statement(
    session: Database,
    user: ReadUser,
    month: Annotated[int, Query(ge=1, le=12, description="Statement month (1-12)")],
    year: Annotated[int, Query(ge=2000, le=2100, description="Statement year (e.g. 2026)")],
    search: Optional[str] = Query(None, description="Search item id, name, or customer part no"),
    store_group: Optional[str] = Query(None, description="Filter by store group"),
    item_class: Optional[str] = Query("CONSUMABLE", description="Filter by item class ('CONSUMABLE', 'OTHER_ITEM', or 'ALL')"),
    has_warnings_only: bool = Query(False, description="Filter only records with validation warnings"),
) -> StockStatementResponse:
    """Retrieve the active monthly stock statement and aggregated totals."""
    return service.get_stock_statement(
        session,
        month=month,
        year=year,
        search=search,
        store_group_filter=store_group,
        item_class_filter=item_class,
        has_warnings_only=has_warnings_only,
    )


@router.get("/missing", response_model=MissingConsumablesResponse)
def get_missing(
    session: Database,
    user: ReadUser,
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> MissingConsumablesResponse:
    """List active consumables in Product Master that have no entry in the selected month's statement."""
    return service.get_missing_consumables(session, month=month, year=year)


@router.get("/missing/export")
def export_missing(
    session: Database,
    user: ReadUser,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Download active consumables missing from the stock statement as an Excel spreadsheet."""
    excel_bytes, filename = service.export_missing_consumables_excel(session, month=month, year=year)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)


@router.post("/promote", response_model=PromoteConsumablesResponse)
def promote_items(
    session: Database,
    user: PromoteUser,
    payload: PromoteConsumablesRequest,
) -> PromoteConsumablesResponse:
    """Promote one or more statement other items into the Consumable Master."""
    return service.promote_statement_items_to_consumables(session, payload=payload, user=user)


@router.post("/demote", response_model=DemoteConsumableResponse)
def demote_item(
    session: Database,
    user: PromoteUser,
    payload: DemoteConsumableRequest,
) -> DemoteConsumableResponse:
    """Move a consumable back to other items if it has no downstream dependencies."""
    return service.demote_consumable_item(session, payload=payload, user=user)


@router.post("/preview", response_model=StockStatementPreviewResponse)
async def preview_statement(
    session: Database,
    user: ImportUser,
    file: UploadFile = File(...),
    statement_month: int = Form(...),
    statement_year: int = Form(...),
) -> StockStatementPreviewResponse:
    """Upload and validate an Excel file for Stock Statement without committing to DB."""
    content = await file.read()
    filename = file.filename or "stock_statement.xlsx"
    return service.parse_and_preview_stock_statement(
        session,
        content=content,
        filename=filename,
        month=statement_month,
        year=statement_year,
    )


@router.patch("/batch-update", response_model=StockStatementResponse)
def update_statement(session: Database,
                     user: Annotated[CurrentUser, Depends(require_feature_flag("inventory_update"))],
                     payload: StockStatementBatchUpdateRequest) -> StockStatementResponse:
    return service.batch_update_stock_statement(session, payload=payload, user=user)


@router.delete("", response_model=StockStatementDeleteResponse)
def delete_statement(
    session: Database,
    user: DeleteUser,
    payload: StockStatementDeleteRequest,
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> StockStatementDeleteResponse:
    """Remove only the reviewed active upload for the selected month/year."""
    return service.delete_stock_statement(session, month=month, year=year, payload=payload, user=user)


@router.post("/confirm", response_model=StockStatementResponse, status_code=status.HTTP_201_CREATED)
def confirm_statement(
    session: Database,
    user: ImportUser,
    payload: StockStatementConfirmRequest,
) -> StockStatementResponse:
    """Confirm a previously previewed stock statement and commit in a single transaction."""
    return service.confirm_stock_statement_import(
        session,
        payload=payload,
        user=user,
    )


@router.get("/history", response_model=list[StockStatementHistoryItem])
def list_history(
    session: Database,
    user: ReadUser,
    limit: int = Query(50, ge=1, le=200),
) -> list[StockStatementHistoryItem]:
    """List historical stock statement upload batches."""
    return service.list_stock_statement_history(session, limit=limit)


@router.get("/export")
def export_statement(
    session: Database,
    user: ReadUser,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Download the active stock statement for the month as a formatted Excel spreadsheet."""
    excel_bytes, filename = service.export_stock_statement_excel(session, month=month, year=year)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)


@router.get("/preview-errors")
def export_errors(
    user: ReadUser,
    file_token: str = Query(..., description="File token from preview response"),
):
    """Download an Excel report listing all validation errors and warnings for a previewed upload."""
    entry = service._PREVIEW_STORE.get(file_token)
    if not entry:
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The requested preview token has expired or is invalid. Please re-upload the file.",
            404,
        )
    if time.time() - entry.get("created_at", 0) > service.PREVIEW_TTL_SECONDS:
        service._PREVIEW_STORE.pop(file_token, None)
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The requested preview token has expired. Please re-upload the file.",
            404,
        )
    issues = entry.get("issues", [])
    filename = entry.get("filename", "upload")
    excel_bytes, report_name = service.export_error_report_excel(issues, filename=filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report_name)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)

