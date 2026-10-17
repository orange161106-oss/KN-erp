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
    StockManagementResponse,
    StockParameterDeleteRequest,
    StockParameterDeleteResponse,
    StockParameterBatchUpdateRequest,
    StockParameterConfirmRequest,
    StockParameterHistoryItem,
    StockParameterPreviewResponse,
)
from app.security.permissions import require_feature_flag, require_permissions
from app.services import stock_management_service as service

router = APIRouter(
    prefix="/inventory/management",
    tags=["stock-management"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500)},
)

ReadUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.read", "inventory.read"))]
ImportUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.import", "inventory.create", "inventory.update"))]
DeleteUser = Annotated[CurrentUser, Depends(require_feature_flag("inventory_delete"))]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=StockManagementResponse)
@router.get("/", response_model=StockManagementResponse, include_in_schema=False)
def get_management(
    session: Database,
    user: ReadUser,
    month: Annotated[int, Query(ge=1, le=12, description="Target month (1-12)")],
    year: Annotated[int, Query(ge=2000, le=2100, description="Target year (e.g. 2026)")],
    search: Optional[str] = Query(None, description="Search item id, description, or category"),
    category: Optional[str] = Query(None, description="Filter by category"),
    multi_category_only: bool = Query(False, description="Filter items appearing in multiple categories"),
) -> StockManagementResponse:
    """Retrieve the stock control parameters (MSL, Max, MOQ, Lead Time) for the selected month."""
    return service.get_stock_management(
        session,
        month=month,
        year=year,
        search=search,
        category_filter=category,
        multi_category_only=multi_category_only,
    )


@router.delete("", response_model=StockParameterDeleteResponse)
def delete_parameters(
    session: Database,
    user: DeleteUser,
    payload: StockParameterDeleteRequest,
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> StockParameterDeleteResponse:
    return service.delete_stock_parameters(session, month=month, year=year, payload=payload, user=user)


@router.post("/preview", response_model=StockParameterPreviewResponse)
def preview_parameters(
    session: Database,
    user: ImportUser,
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
) -> StockParameterPreviewResponse:
    """Upload and validate an Excel file for Stock Management parameters without saving to DB."""
    content = file.file.read()
    filename = file.filename or "stock_management.xlsx"
    return service.parse_and_preview_stock_parameters(
        session,
        content=content,
        filename=filename,
        month=month,
        year=year,
    )


@router.post("/confirm", response_model=StockManagementResponse, status_code=status.HTTP_201_CREATED)
def confirm_parameters(
    session: Database,
    user: ImportUser,
    payload: StockParameterConfirmRequest,
) -> StockManagementResponse:
    """Confirm a previously previewed stock management import and commit in a single transaction."""
    return service.confirm_stock_parameters_import(
        session,
        payload=payload,
        user=user,
    )


@router.patch("/batch-update", response_model=StockManagementResponse)
def batch_update_parameters(
    session: Database,
    user: Annotated[CurrentUser, Depends(require_feature_flag("inventory_update"))],
    payload: StockParameterBatchUpdateRequest,
) -> StockManagementResponse:
    """Save inline edits to stock parameters (MSL, Max, MOQ, Lead Time) for the month."""
    return service.batch_update_stock_parameters(
        session,
        request=payload,
        current_user=user,
    )


@router.get("/history", response_model=list[StockParameterHistoryItem])
def list_history(
    session: Database,
    user: ReadUser,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    limit: int = Query(50, ge=1, le=200),
) -> list[StockParameterHistoryItem]:
    """List historical stock parameter upload batches."""
    return service.list_stock_parameter_history(session, month=month, year=year, limit=limit)


@router.get("/export")
def export_parameters(
    session: Database,
    user: ReadUser,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Download the active stock management parameters for the month as a formatted Excel spreadsheet."""
    excel_bytes, filename = service.export_stock_management_excel(session, month=month, year=year)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)


@router.get("/preview-errors")
def export_preview_errors(
    user: ReadUser,
    file_token: str = Query(..., description="File token from preview response"),
):
    """Download an Excel report listing all validation errors, warnings, row contents, and hints for a previewed upload."""
    entry = service._PARAM_PREVIEW_STORE.get(file_token)
    if not entry:
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The requested preview token has expired or is invalid. Please re-upload the file.",
            404,
        )
    if time.time() - entry.get("created_at", 0) > service.PARAM_PREVIEW_TTL_SECONDS:
        service._PARAM_PREVIEW_STORE.pop(file_token, None)
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The requested preview token has expired. Please re-upload the file.",
            404,
        )
    issues = entry.get("issues", [])
    filename = entry.get("filename", "stock_management.xlsx")
    excel_bytes, report_name = service.export_parameter_error_report_excel(issues, filename=filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report_name)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)


@router.get("/import-summary")
def export_import_summary(
    session: Database,
    user: ReadUser,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Download the Excel import summary including all skipped and resolved rows for the month."""
    excel_bytes, filename = service.export_parameter_import_summary_excel(session, month=month, year=year)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)
