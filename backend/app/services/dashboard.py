"""Service layer for M6.3 — Executive Management Dashboard."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alerts import InventoryAlert
from app.models.grn import GRNItem
from app.models.inventory_masters import Consumable
from app.models.plant_workflow import RequirementAdjustment
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.requirements import CalculatedRequirement
from app.schemas.dashboard import DashboardSummaryResponse, PipelineSummarySchema


def get_dashboard_summary(session: Session) -> DashboardSummaryResponse:
    """Compute executive KPI cards and procurement pipeline summary metrics.

    All counts and aggregates strictly source from backend ORM models.
    Zero React-side formula calculations or invented fallback metrics.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Alert Counts
    active_critical = session.execute(
        select(func.count(InventoryAlert.id)).where(
            InventoryAlert.status == "ACTIVE",
            InventoryAlert.severity == "CRITICAL",
        )
    ).scalar_one()

    active_warning = session.execute(
        select(func.count(InventoryAlert.id)).where(
            InventoryAlert.status == "ACTIVE",
            InventoryAlert.severity == "WARNING",
        )
    ).scalar_one()

    # 2. Workflow Pending Approval Queue
    pending_approvals = session.execute(
        select(func.count(PurchaseApproval.id)).where(
            PurchaseApproval.status == "PENDING"
        )
    ).scalar_one()

    pending_adjustments = session.execute(
        select(func.count(RequirementAdjustment.id)).where(
            RequirementAdjustment.status == "PENDING"
        )
    ).scalar_one()

    # 3. POs & Inventory Status
    issued_pos = session.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.status == "ISSUED"
        )
    ).scalar_one()

    active_consumables = session.execute(
        select(func.count(Consumable.id)).where(
            Consumable.is_active == True  # noqa: E712
        )
    ).scalar_one()

    # 4. Pipeline Summary Metrics
    tot_calc_qty = session.execute(
        select(func.coalesce(func.sum(CalculatedRequirement.calculated_qty), Decimal("0.0000")))
    ).scalar_one()

    tot_approved_adj_qty = session.execute(
        select(func.coalesce(func.sum(RequirementAdjustment.requested_qty), Decimal("0.0000"))).where(
            RequirementAdjustment.status == "APPROVED"
        )
    ).scalar_one()

    tot_final_req_qty = tot_calc_qty + tot_approved_adj_qty

    tot_recommended_qty = session.execute(
        select(func.coalesce(func.sum(PurchaseApproval.system_recommended_qty), Decimal("0.0000")))
    ).scalar_one()

    tot_approved_purchase_qty = session.execute(
        select(func.coalesce(func.sum(PurchaseApproval.approved_qty), Decimal("0.0000"))).where(
            PurchaseApproval.status == "APPROVED"
        )
    ).scalar_one()

    tot_ordered_qty = session.execute(
        select(func.coalesce(func.sum(PurchaseOrderItem.ordered_quantity), Decimal("0.0000")))
    ).scalar_one()

    tot_grn_accepted_qty = session.execute(
        select(func.coalesce(func.sum(GRNItem.accepted_quantity), Decimal("0.0000")))
    ).scalar_one()

    pipeline_summary = PipelineSummarySchema(
        total_calculated_quantity=tot_calc_qty,
        total_approved_additions=tot_approved_adj_qty,
        total_final_requirement=tot_final_req_qty,
        total_recommended_quantity=tot_recommended_qty,
        total_approved_purchase_quantity=tot_approved_purchase_qty,
        total_ordered_quantity=tot_ordered_qty,
        total_accepted_grn_quantity=tot_grn_accepted_qty,
    )

    return DashboardSummaryResponse(
        active_critical_alerts=active_critical,
        active_warning_alerts=active_warning,
        pending_purchase_approvals=pending_approvals,
        pending_plant_adjustments=pending_adjustments,
        issued_pending_pos=issued_pos,
        total_active_consumables=active_consumables,
        pipeline_summary=pipeline_summary,
        as_of=now_utc,
    )
