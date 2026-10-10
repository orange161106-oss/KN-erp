from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.dashboard import DashboardSummaryResponse
from app.schemas.reports import PlannedVsActualReportResponse
from app.security.permissions import require_permissions
from app.services.dashboard import get_dashboard_summary
from app.services.reports import get_planned_vs_actual_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/dashboard-summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get executive dashboard KPI cards and procurement pipeline summary",
)
def get_dashboard_summary_endpoint(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("reports.inventory.read"))],
) -> DashboardSummaryResponse:
    """Aggregates executive KPIs, active alerts, workflow approval queues, and procurement pipeline summary."""
    return get_dashboard_summary(session)


@router.get(
    "/planned-vs-actual",
    response_model=PlannedVsActualReportResponse,
    status_code=status.HTTP_200_OK,
)
def get_planned_vs_actual(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions('reports.inventory.read'))],
    period: Optional[str] = Query(None, description="Planning period in YYYY-MM format"),
    planning_version_id: Optional[UUID] = Query(None, description="Specific planning version ID"),
    plant_id: Optional[UUID] = Query(None, description="Filter by plant ID"),
    consumable_id: Optional[UUID] = Query(None, description="Filter by consumable ID"),
    process_id: Optional[UUID] = Query(None, description="Filter by process ID"),
) -> PlannedVsActualReportResponse:
    """Historical comparison of planned demand vs actual consumption.

    Lineage: Planning Version -> Calculated Requirements + Approved Additions = Final Requirement.
    Actual consumption sourced from confirmed StockTransactions (ISSUE - RETURN).
    Never infers consumption or modifies consumption norms.
    """
    return get_planned_vs_actual_report(
        session,
        period=period,
        planning_version_id=planning_version_id,
        plant_id=plant_id,
        consumable_id=consumable_id,
        process_id=process_id,
    )


