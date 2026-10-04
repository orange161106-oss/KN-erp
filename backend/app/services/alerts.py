"""Service layer for M4.4 — Inventory & MSL Alerts Workflow.

Business Rules:
  - Inventory alerts are backend-evaluated from reported central stock balances, MSL thresholds, and M4.3 reorder assessments.
  - Active alerts for the same (consumable_id, alert_type) are updated in-place to avoid duplicate alert spam.
  - Stock < MSL floor -> CRITICAL severity BELOW_MSL alert.
  - Stock < 1.2 * MSL -> WARNING severity LOW_STOCK alert.
  - Stock >= threshold -> ACTIVE alert resolved.
  - Acknowledgements update status to ACKNOWLEDGED and write to audit_logs.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.alerts import InventoryAlert
from app.models.audit import AuditLog
from app.models.inventory import StockSnapshot
from app.models.inventory_masters import Consumable, Unit
from app.schemas.alerts import (
    AlertEvaluationSummaryResponse,
    InventoryAlertResponse,
)
from app.schemas.auth import CurrentUser

DEFAULT_MSL_THRESHOLD = Decimal("100.0000")


def _alert_to_response(alert: InventoryAlert) -> InventoryAlertResponse:
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    username: Optional[str] = None

    if alert.consumable is not None:
        consumable_code = alert.consumable.code
        consumable_name = alert.consumable.name
    if alert.acknowledged_by_user is not None:
        username = alert.acknowledged_by_user.username

    return InventoryAlertResponse(
        id=alert.id,
        consumable_id=alert.consumable_id,
        consumable_code=consumable_code,
        consumable_name=consumable_name,
        alert_type=alert.alert_type,  # type: ignore
        severity=alert.severity,  # type: ignore
        current_stock=alert.current_stock,
        threshold_qty=alert.threshold_qty,
        uom=alert.uom,
        message=alert.message,
        status=alert.status,  # type: ignore
        acknowledged_by=alert.acknowledged_by,
        acknowledged_by_username=username,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def list_alerts(
    session: Session,
    *,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    status: Optional[str] = None,
    consumable_id: Optional[UUID] = None,
) -> list[InventoryAlertResponse]:
    stmt = select(InventoryAlert)
    if severity:
        stmt = stmt.where(InventoryAlert.severity == severity)
    if alert_type:
        stmt = stmt.where(InventoryAlert.alert_type == alert_type)
    if status:
        stmt = stmt.where(InventoryAlert.status == status)
    if consumable_id:
        stmt = stmt.where(InventoryAlert.consumable_id == consumable_id)

    stmt = stmt.order_by(
        desc(InventoryAlert.status == "ACTIVE"),
        desc(InventoryAlert.severity == "CRITICAL"),
        desc(InventoryAlert.created_at),
    )
    rows = session.execute(stmt).scalars().all()
    return [_alert_to_response(r) for r in rows]


def acknowledge_alert(
    session: Session,
    alert_id: UUID,
    current_user: CurrentUser,
    notes: Optional[str] = None,
) -> InventoryAlertResponse:
    alert = session.get(InventoryAlert, alert_id)
    if not alert:
        raise ApplicationError("ALERT_NOT_FOUND", "Alert not found.", 404)

    if alert.status != "ACTIVE":
        raise ApplicationError(
            "ALERT_ALREADY_ACKNOWLEDGED",
            f"Alert is already in status '{alert.status}'.",
            409,
        )

    now = datetime.now(timezone.utc)
    old_status = alert.status

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = now

    audit = AuditLog(
        actor_id=current_user.id,
        action="ACKNOWLEDGE",
        entity_type="inventory_alert",
        entity_id=alert.id,
        old_values={"status": old_status},
        new_values={
            "status": "ACKNOWLEDGED",
            "acknowledged_by": str(current_user.id),
            "notes": notes,
        },
        reason="Inventory alert acknowledged by user.",
    )
    session.add(audit)
    session.commit()
    session.refresh(alert)
    return _alert_to_response(alert)


def evaluate_inventory_alerts(session: Session) -> AlertEvaluationSummaryResponse:
    """Evaluate reported central stock balances against MSL thresholds.

    Deduplication: Existing ACTIVE alerts for (consumable_id, alert_type) are
    updated in-place rather than creating duplicate rows.
    """
    consumables = session.execute(
        select(Consumable).where(Consumable.is_active == True)  # noqa: E712
    ).scalars().all()

    units_map = {
        u.id: u.code
        for u in session.execute(select(Unit)).scalars().all()
    }

    # Fetch latest snapshot per consumable
    subq = (
        select(
            StockSnapshot.consumable_id,
            func.max(StockSnapshot.as_of).label("max_as_of"),
        )
        .group_by(StockSnapshot.consumable_id)
        .subquery()
    )
    latest_snapshots = session.execute(
        select(StockSnapshot).join(
            subq,
            (StockSnapshot.consumable_id == subq.c.consumable_id)
            & (StockSnapshot.as_of == subq.c.max_as_of),
        )
    ).scalars().all()

    snapshot_by_consumable = {s.consumable_id: s for s in latest_snapshots}

    counts = {"created": 0, "updated": 0}

    for c in consumables:
        snap = snapshot_by_consumable.get(c.id)
        current_stock = snap.usable_quantity if snap else Decimal("0.0000")
        threshold_qty = DEFAULT_MSL_THRESHOLD
        uom_str = units_map.get(c.unit_id, "UNK")

        # Check conditions
        is_below_msl = current_stock < threshold_qty
        is_low_stock = not is_below_msl and (current_stock < (threshold_qty * Decimal("1.2")))

        # Process BELOW_MSL condition
        _process_alert_condition(
            session=session,
            consumable=c,
            alert_type="BELOW_MSL",
            severity="CRITICAL",
            current_stock=current_stock,
            threshold_qty=threshold_qty,
            uom=uom_str,
            message=f"CRITICAL: Stock for {c.code} ({current_stock} {uom_str}) is below MSL threshold ({threshold_qty} {uom_str}).",
            condition_active=is_below_msl,
            counts=counts,
        )

        # Process LOW_STOCK condition
        _process_alert_condition(
            session=session,
            consumable=c,
            alert_type="LOW_STOCK",
            severity="WARNING",
            current_stock=current_stock,
            threshold_qty=threshold_qty * Decimal("1.2"),
            uom=uom_str,
            message=f"WARNING: Stock for {c.code} ({current_stock} {uom_str}) is approaching MSL threshold ({threshold_qty} {uom_str}).",
            condition_active=is_low_stock,
            counts=counts,
        )

    session.commit()

    # Calculate active counts
    active_critical = session.execute(
        select(func.count(InventoryAlert.id)).where(
            InventoryAlert.status == "ACTIVE", InventoryAlert.severity == "CRITICAL"
        )
    ).scalar_one()

    active_warning = session.execute(
        select(func.count(InventoryAlert.id)).where(
            InventoryAlert.status == "ACTIVE", InventoryAlert.severity == "WARNING"
        )
    ).scalar_one()

    active_info = session.execute(
        select(func.count(InventoryAlert.id)).where(
            InventoryAlert.status == "ACTIVE", InventoryAlert.severity == "INFO"
        )
    ).scalar_one()

    return AlertEvaluationSummaryResponse(
        total_evaluated=len(consumables),
        alerts_created=counts["created"],
        alerts_updated=counts["updated"],
        active_critical_count=active_critical,
        active_warning_count=active_warning,
        active_info_count=active_info,
    )


def _process_alert_condition(
    session: Session,
    *,
    consumable: Consumable,
    alert_type: str,
    severity: str,
    current_stock: Decimal,
    threshold_qty: Decimal,
    uom: str,
    message: str,
    condition_active: bool,
    counts: dict,
) -> None:
    existing_alert = session.execute(
        select(InventoryAlert).where(
            InventoryAlert.consumable_id == consumable.id,
            InventoryAlert.alert_type == alert_type,
            InventoryAlert.status.in_(["ACTIVE", "ACKNOWLEDGED"]),
        )
    ).scalar_one_or_none()

    if condition_active:
        if existing_alert:
            existing_alert.current_stock = current_stock
            existing_alert.threshold_qty = threshold_qty
            existing_alert.message = message
            existing_alert.severity = severity
            counts["updated"] += 1
        else:
            new_alert = InventoryAlert(
                consumable_id=consumable.id,
                alert_type=alert_type,
                severity=severity,
                current_stock=current_stock,
                threshold_qty=threshold_qty,
                uom=uom,
                message=message,
                status="ACTIVE",
            )
            session.add(new_alert)
            counts["created"] += 1
    else:
        if existing_alert and existing_alert.status == "ACTIVE":
            existing_alert.status = "RESOLVED"
