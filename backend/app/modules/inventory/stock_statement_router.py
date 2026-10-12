import io
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.stock_statements import (
    StockStatementConfirmRequest,
    StockStatementHistoryItem,
    StockStatementPreviewResponse,
    StockStatementResponse,
)
from app.security.permissions import require_permissions
from app.services import stock_statement_service as service

router = APIRouter(
    prefix="/inventory/statement",
    tags=["stock-statement"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500)},
)

ReadUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.read", "inventory.read"))]
ImportUser = Annotated[CurrentUser, Depends(require_permissions("inventory.stock.import", "inventory.create", "inventory.update"))]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=StockStatementResponse)
def get_statement(
    session: Database,
    user: ReadUser,
    month: Annotated[int, Query(ge=1, le=12, description="Statement month (1-12)")],
    year: Annotated[int, Query(ge=2000, le=2100, description="Statement year (e.g. 2026)")],
    search: Optional[str] = Query(None, description="Search item id, name, or customer part no"),
    has_warnings_only: bool = Query(False, description="Filter only records with validation warnings"),
) -> StockStatementResponse:
    """Retrieve the active monthly stock statement and aggregated totals."""
    return service.get_stock_statement(
        session,
        month=month,
        year=year,
        search=search,
        has_warnings_only=has_warnings_only,
    )


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
        raise HTTPException(
            status_code=404,
            detail="The requested preview token has expired or is invalid. Please re-upload the file.",
        )
    issues = entry.get("issues", [])
    filename = entry.get("filename", "upload")
    excel_bytes, report_name = service.export_error_report_excel(issues, filename=filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report_name)}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(io.BytesIO(excel_bytes), headers=headers)

