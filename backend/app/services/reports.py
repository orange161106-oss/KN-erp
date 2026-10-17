from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.inventory import StockTransaction
from app.models.inventory_masters import Consumable, Unit
from app.models.plant_workflow import RequirementAdjustment
from app.models.prd import PlanningVersion
from app.models.production import Plant, Process
from app.models.requirements import CalculatedRequirement
from app.schemas.reports import (
    PlannedVsActualItem,
    PlannedVsActualReportResponse,
    PlannedVsActualTotals,
)


def _get_period_date_range(period_str: str) -> tuple[datetime, datetime]:
    """Parse 'YYYY-MM' period into start and end UTC datetime bounds."""
    try:
        parts = period_str.strip().split("-")
        year = int(parts[0])
        month = int(parts[1])
    except (ValueError, IndexError):
        raise ApplicationError(
            "INVALID_PERIOD_FORMAT",
            f"Period '{period_str}' is invalid; expected format YYYY-MM",
            status_code=400,
        )

    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if month == 12:
        next_month = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    end_dt = next_month - timedelta(microseconds=1)
    return start_dt, end_dt


def get_planned_vs_actual_report(
    session: Session,
    *,
    period: Optional[str] = None,
    planning_version_id: Optional[UUID] = None,
    plant_id: Optional[UUID] = None,
    consumable_id: Optional[UUID] = None,
    process_id: Optional[UUID] = None,
) -> PlannedVsActualReportResponse:
    """Generate planned vs actual consumption comparison without AI/ML inferences.

    Strict rules:
    - Never auto-change norms.
    - Never call purchase orders/GRN as consumption.
    - Never infer actual consumption when required stock movements are unavailable.
    """
    # 1. Resolve Target Planning Version
    version: Optional[PlanningVersion] = None
    if planning_version_id:
        version = session.get(PlanningVersion, planning_version_id)
        if not version:
            raise ApplicationError(
                "NOT_FOUND",
                f"Planning version '{planning_version_id}' not found",
                status_code=404,
            )
    elif period:
        stmt_v = (
            select(PlanningVersion)
            .where(PlanningVersion.planning_period == period)
            .order_by(PlanningVersion.version_number.desc())
        )
        version = session.scalars(stmt_v).first()
        if not version:
            raise ApplicationError(
                "NOT_FOUND",
                f"No planning version found for period '{period}'",
                status_code=404,
            )
    else:
        stmt_v = (
            select(PlanningVersion)
            .order_by(PlanningVersion.created_at.desc())
        )
        version = session.scalars(stmt_v).first()
        if not version:
            raise ApplicationError(
                "NOT_FOUND",
                "No planning versions exist in the system",
                status_code=404,
            )

    period_str = version.planning_period
    period_start, period_end = _get_period_date_range(period_str)

    # 2. Query Calculated Requirements for the Version
    calc_stmt = (
        select(
            CalculatedRequirement.consumable_id,
            CalculatedRequirement.plant_id,
            CalculatedRequirement.process_id,
            func.sum(CalculatedRequirement.calculated_qty).label("total_calculated_qty"),
        )
        .where(CalculatedRequirement.planning_version_id == version.id)
    )
    if plant_id:
        calc_stmt = calc_stmt.where(CalculatedRequirement.plant_id == plant_id)
    if consumable_id:
        calc_stmt = calc_stmt.where(CalculatedRequirement.consumable_id == consumable_id)
    if process_id:
        calc_stmt = calc_stmt.where(CalculatedRequirement.process_id == process_id)

    # Grouping depends on filters:
    if process_id:
        calc_stmt = calc_stmt.group_by(
            CalculatedRequirement.consumable_id,
            CalculatedRequirement.plant_id,
            CalculatedRequirement.process_id,
        )
    elif plant_id:
        calc_stmt = calc_stmt.group_by(
            CalculatedRequirement.consumable_id,
            CalculatedRequirement.plant_id,
        )
    else:
        calc_stmt = calc_stmt.group_by(CalculatedRequirement.consumable_id)

    calc_rows = session.execute(calc_stmt).all()

    # Map calculated quantities: consumable_id -> Decimal
    calc_map: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    for row in calc_rows:
        cid = row[0]
        calc_qty = Decimal(str(row.total_calculated_qty or 0))
        calc_map[cid] += calc_qty

    # 3. Query Approved Adjustments (M3.4 / M3.5)
    # Note: RequirementAdjustment is at planning_version × plant × consumable grain (no process_id)
    adj_map: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    if not process_id:
        adj_stmt = (
            select(
                RequirementAdjustment.consumable_id,
                func.sum(RequirementAdjustment.requested_qty).label("total_adj_qty"),
            )
            .where(
                RequirementAdjustment.planning_version_id == version.id,
                RequirementAdjustment.status == "APPROVED",
            )
        )
        if plant_id:
            adj_stmt = adj_stmt.where(RequirementAdjustment.plant_id == plant_id)
        if consumable_id:
            adj_stmt = adj_stmt.where(RequirementAdjustment.consumable_id == consumable_id)

        adj_stmt = adj_stmt.group_by(RequirementAdjustment.consumable_id)
        adj_rows = session.execute(adj_stmt).all()

        for row in adj_rows:
            cid = row[0]
            adj_qty = Decimal(str(row.total_adj_qty or 0))
            adj_map[cid] = adj_qty

    # 4. Query Actual Stock Movements from Central Store (StockTransaction)
    # Movement convention: ISSUE - RETURN in period [period_start, period_end]
    stock_consumed_map: dict[UUID, Decimal] = {}
    has_stock_activity: set[UUID] = set()

    if not plant_id and not process_id:
        # Central store transaction ledger is confirmed at material level
        tx_stmt = (
            select(
                StockTransaction.consumable_id,
                StockTransaction.movement,
                func.sum(StockTransaction.quantity).label("total_movement_qty"),
            )
            .where(
                StockTransaction.event_at >= period_start,
                StockTransaction.event_at <= period_end,
                StockTransaction.movement.in_(["ISSUE", "RETURN"]),
            )
        )
        if consumable_id:
            tx_stmt = tx_stmt.where(StockTransaction.consumable_id == consumable_id)

        tx_stmt = tx_stmt.group_by(
            StockTransaction.consumable_id,
            StockTransaction.movement,
        )
        tx_rows = session.execute(tx_stmt).all()

        # Temporary buckets: {consumable_id: {"ISSUE": Decimal, "RETURN": Decimal}}
        movement_buckets: dict[UUID, dict[str, Decimal]] = defaultdict(
            lambda: {"ISSUE": Decimal("0.0000"), "RETURN": Decimal("0.0000")}
        )

        for row in tx_rows:
            cid = row.consumable_id
            m_type = row.movement
            m_qty = Decimal(str(row.total_movement_qty or 0))
            movement_buckets[cid][m_type] += m_qty
            has_stock_activity.add(cid)

        for cid, b in movement_buckets.items():
            net_issue = b["ISSUE"] - b["RETURN"]
            stock_consumed_map[cid] = max(Decimal("0.0000"), net_issue)

    # 5. Union all distinct consumable IDs (planned, adjusted, or stock active)
    all_consumable_ids: set[UUID] = set(calc_map.keys()) | set(adj_map.keys())
    if not plant_id and not process_id:
        all_consumable_ids |= has_stock_activity

    if consumable_id:
        all_consumable_ids = {consumable_id} if consumable_id in all_consumable_ids else set()

    # Preload master consumable and unit records
    consumables_stmt = (
        select(Consumable, Unit.code)
        .join(Unit, Unit.id == Consumable.unit_id)
        .where(Consumable.id.in_(all_consumable_ids))
    )
    consumables_db = {row[0].id: (row[0], row[1]) for row in session.execute(consumables_stmt).all()}

    # Metadata for filter labels
    plant_obj = session.get(Plant, plant_id) if plant_id else None
    process_obj = session.get(Process, process_id) if process_id else None

    # 6. Assemble Items and Calculate Variances
    items: list[PlannedVsActualItem] = []

    for cid in sorted(all_consumable_ids, key=lambda x: str(x)):
        if cid not in consumables_db:
            continue

        c_obj, unit_code = consumables_db[cid]
        c_calc = calc_map.get(cid, Decimal("0.0000"))
        c_adj = adj_map.get(cid, Decimal("0.0000"))
        c_final = c_calc + c_adj

        # Determine actual consumption based on explicit boundary rules
        c_actual: Optional[Decimal] = None
        variance_amt: Optional[Decimal] = None
        variance_pct: Optional[Decimal] = None

        if plant_id:
            actual_status = "PLANT_GRAIN_UNAVAILABLE"
        elif process_id:
            actual_status = "PROCESS_GRAIN_UNAVAILABLE"
        elif cid in has_stock_activity:
            c_actual = stock_consumed_map.get(cid, Decimal("0.0000"))
            actual_status = "AVAILABLE"
            variance_amt = c_actual - c_final
            if c_final > Decimal("0.0000"):
                variance_pct = (
                    (variance_amt / c_final) * Decimal("100")
                ).quantize(Decimal("0.01"))
            elif c_actual == Decimal("0.0000"):
                variance_pct = Decimal("0.00")
            else:
                variance_pct = None
        else:
            actual_status = "NO_STOCK_DATA"

        items.append(
            PlannedVsActualItem(
                consumable_id=cid,
                consumable_code=c_obj.code,
                consumable_name=c_obj.name,
                uom=unit_code,
                plant_id=plant_id,
                plant_name=plant_obj.name if plant_obj else None,
                process_id=process_id,
                process_name=process_obj.name if process_obj else None,
                calculated_qty=c_calc,
                approved_additions_qty=c_adj,
                final_required_qty=c_final,
                actual_consumed_qty=c_actual,
                variance_amount=variance_amt,
                variance_percentage=variance_pct,
                actual_status=actual_status,
            )
        )

    # Sort alphabetically by code
    items.sort(key=lambda x: x.consumable_code)

    # 7. Compute Totals
    total_calc = sum((it.calculated_qty for it in items), Decimal("0.0000"))
    total_adj = sum((it.approved_additions_qty for it in items), Decimal("0.0000"))
    total_final = sum((it.final_required_qty for it in items), Decimal("0.0000"))

    # Total actual is computed only if at least one item has actual available and none are grain-unavailable
    has_any_actual = any(it.actual_consumed_qty is not None for it in items)
    is_grain_restricted = plant_id is not None or process_id is not None

    total_actual: Optional[Decimal] = None
    total_variance_amt: Optional[Decimal] = None
    total_variance_pct: Optional[Decimal] = None

    if has_any_actual and not is_grain_restricted:
        total_actual = sum((it.actual_consumed_qty or Decimal("0.0000") for it in items), Decimal("0.0000"))
        total_variance_amt = total_actual - total_final
        if total_final > Decimal("0.0000"):
            total_variance_pct = (
                (total_variance_amt / total_final) * Decimal("100")
            ).quantize(Decimal("0.01"))
        elif total_actual == Decimal("0.0000"):
            total_variance_pct = Decimal("0.00")

    totals = PlannedVsActualTotals(
        total_calculated_qty=total_calc,
        total_approved_additions_qty=total_adj,
        total_final_required_qty=total_final,
        total_actual_consumed_qty=total_actual,
        total_variance_amount=total_variance_amt,
        total_variance_percentage=total_variance_pct,
    )

    return PlannedVsActualReportResponse(
        period=period_str,
        planning_version_id=version.id,
        revision_label=version.revision_label,
        version_status=version.status,
        items=items,
        totals=totals,
    )

