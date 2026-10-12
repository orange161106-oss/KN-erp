from datetime import datetime
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.inventory_masters import Consumable
from app.models.requirements import AggregatedRequirement, MonthlyRequirementPlan, RequirementLineItem, RequirementStatus
from app.schemas.requirements import AggregatedRequirementResponse, AggregationRunResponse


def _to_aggregated_response(record: AggregatedRequirement) -> AggregatedRequirementResponse:
    item_id = None
    consumable_name = None
    if record.consumable:
        item_id = getattr(record.consumable, "item_id", None)
        consumable_name = getattr(record.consumable, "name", None)
    return AggregatedRequirementResponse(
        id=record.id,
        month=record.month,
        year=record.year,
        consumable_id=record.consumable_id,
        total_gross_qty=record.total_gross_qty,
        net_purchase_qty=record.net_purchase_qty,
        consumable_name=consumable_name,
        item_id=item_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def run_monthly_aggregation(db: Session, month: int, year: int) -> AggregationRunResponse:
    """Groups identical consumables across multiple approved plant plans to calculate the total company-wide requirement.

    1. Query all MonthlyRequirementPlan records for (month, year) where status == APPROVED.
    2. If no approved plans exist, raise HTTPException(400).
    3. Join with RequirementLineItem and group by consumable_id.
    4. Calculate sum(requested_qty) for each consumable.
    5. Upsert grouped records into AggregatedRequirement table.
    """
    approved_plans = db.execute(
        select(MonthlyRequirementPlan).where(
            MonthlyRequirementPlan.month == month,
            MonthlyRequirementPlan.year == year,
            MonthlyRequirementPlan.status == RequirementStatus.APPROVED,
        )
    ).scalars().all()

    if not approved_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No approved monthly requirement plans found for period {month}/{year} to aggregate.",
        )

    approved_plan_ids = [plan.id for plan in approved_plans]

    stmt = (
        select(
            RequirementLineItem.consumable_id,
            func.sum(RequirementLineItem.requested_qty).label("total_gross_qty"),
        )
        .where(RequirementLineItem.plan_id.in_(approved_plan_ids))
        .group_by(RequirementLineItem.consumable_id)
    )
    grouped_rows = db.execute(stmt).all()

    # Pre-fetch existing aggregated records for this month and year
    existing_records = {
        rec.consumable_id: rec
        for rec in db.execute(
            select(AggregatedRequirement)
            .options(joinedload(AggregatedRequirement.consumable))
            .where(
                AggregatedRequirement.month == month,
                AggregatedRequirement.year == year,
            )
        ).scalars().all()
    }

    consumables_map = {
        c.id: c
        for c in db.execute(
            select(Consumable).where(Consumable.id.in_([row.consumable_id for row in grouped_rows]))
        ).scalars().all()
    }

    upserted_records = []
    for row in grouped_rows:
        consumable_id = row.consumable_id
        gross_qty = float(row.total_gross_qty or 0.0)
        net_qty = gross_qty  # Default to total_gross_qty for now

        if consumable_id in existing_records:
            existing = existing_records[consumable_id]
            existing.total_gross_qty = gross_qty
            existing.net_purchase_qty = net_qty
            if not existing.consumable and consumable_id in consumables_map:
                existing.consumable = consumables_map[consumable_id]
            upserted_records.append(existing)
        else:
            new_record = AggregatedRequirement(
                month=month,
                year=year,
                consumable_id=consumable_id,
                total_gross_qty=gross_qty,
                net_purchase_qty=net_qty,
            )
            if consumable_id in consumables_map:
                new_record.consumable = consumables_map[consumable_id]
            db.add(new_record)
            existing_records[consumable_id] = new_record
            upserted_records.append(new_record)

    db.commit()

    final_records = db.execute(
        select(AggregatedRequirement)
        .options(joinedload(AggregatedRequirement.consumable))
        .where(
            AggregatedRequirement.month == month,
            AggregatedRequirement.year == year,
        )
        .order_by(AggregatedRequirement.total_gross_qty.desc())
    ).scalars().all()

    return AggregationRunResponse(
        month=month,
        year=year,
        total_approved_plans=len(approved_plans),
        total_aggregated_consumables=len(final_records),
        records=[_to_aggregated_response(r) for r in final_records],
    )
