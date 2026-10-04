"""FastAPI router for M4.4 — Inventory Stock & MSL Alerts Workflow.

No business logic in routes. All calls delegate to app.services.alerts.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alerts import (
    AcknowledgeAlertRequest,
    AlertEvaluationSummaryResponse,
    InventoryAlertResponse,
)
from app.schemas.auth import CurrentUser
from app.security.permissions import require_permissions
from app.services.alerts import (
    acknowledge_alert,
    evaluate_inventory_alerts,
    list_alerts,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=list[InventoryAlertResponse],
    summary="List inventory alerts",
)
def get_alerts(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("alerts:view"))],
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    consumable_id: Optional[UUID] = Query(None),
) -> list[InventoryAlertResponse]:
    return list_alerts(
        session,
        severity=severity,
        alert_type=alert_type,
        status=status,
        consumable_id=consumable_id,
    )


@router.post(
    "/evaluate",
    response_model=AlertEvaluationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate stock balances against MSL thresholds to generate/update alerts",
)
def post_evaluate_alerts(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("alerts:view"))],
) -> AlertEvaluationSummaryResponse:
    return evaluate_inventory_alerts(session)


@router.patch(
    "/{alert_id}/acknowledge",
    response_model=InventoryAlertResponse,
    summary="Acknowledge an active inventory alert",
)
def patch_acknowledge_alert(
    alert_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("alerts:acknowledge"))],
    req: Optional[AcknowledgeAlertRequest] = None,
) -> InventoryAlertResponse:
    notes = req.notes if req else None
    return acknowledge_alert(session, alert_id, current_user, notes=notes)
