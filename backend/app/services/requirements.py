from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import io
import pandas as pd
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import ApplicationError
from app.domain.rules import (
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
)
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.masters import Product
from app.models.prd import PlanningVersion, PRDOrderItem
from app.models.production import Plant, Process
from app.models.requirements import (
    CalculatedRequirement,
    MonthlyRequirementPlan,
    RequirementCalculationError,
    RequirementLineItem,
    RequirementStatus,
)
from app.models.rules import ConsumptionNorm
from app.models.plant_workflow import PlantConfirmation
from app.models.audit import AuditLog
from app.schemas.auth import CurrentUser
from app.schemas.requirements import (
    BulkUploadResponse,
    CalculatedRequirementResponse,
    CalculationRunRequest,
    ConsumableAggregateItem,
    MonthlyRequirementPlanCreate,
    MonthlyRequirementPlanResponse,
    RequirementCalculationErrorResponse,
    RequirementCalculationRunResponse,
    RequirementLineItemCreate,
    RequirementLineItemResponse,
)



def _to_requirement_response(req: CalculatedRequirement) -> CalculatedRequirementResponse:
    return CalculatedRequirementResponse(
        id=req.id,
        planning_version_id=req.planning_version_id,
        prd_order_item_id=req.prd_order_item_id,
        product_id=req.product_id,
        product_code=req.product.code if req.product else None,
        product_name=req.product.name if req.product else None,
        plant_id=req.plant_id,
        plant_name=req.plant.name if req.plant else None,
        process_id=req.process_id,
        process_name=req.process.name if req.process else None,
        consumable_id=req.consumable_id,
        consumable_code=req.consumable.code if req.consumable else None,
        consumable_name=req.consumable.name if req.consumable else None,
        rule_id=req.rule_id,
        rule_type=req.rule_type,
        rule_version=req.rule_version,
        parameters=req.parameters,
        source_production_qty=req.source_production_qty,
        raw_requirement=req.raw_requirement,
        rounding_policy=req.rounding_policy,
        rounding_precision=req.rounding_precision,
        calculated_qty=req.calculated_qty,
        unit_id=req.unit_id,
        uom=req.uom,
        calculation_steps=req.calculation_steps,
        explanation_payload=req.explanation_payload,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def _to_error_response(err: RequirementCalculationError) -> RequirementCalculationErrorResponse:
    return RequirementCalculationErrorResponse(
        id=err.id,
        planning_version_id=err.planning_version_id,
        prd_order_item_id=err.prd_order_item_id,
        product_id=err.product_id,
        product_code=err.product.code if err.product else None,
        plant_id=err.plant_id,
        plant_name=err.plant.name if err.plant else None,
        consumable_id=err.consumable_id,
        consumable_code=err.consumable.code if err.consumable else None,
        error_code=err.error_code,
        error_message=err.error_message,
        context_data=err.context_data,
        created_at=err.created_at,
    )


def calculate_planning_version_requirements(
    db: Session,
    req: CalculationRunRequest,
    current_user_id: UUID,
) -> RequirementCalculationRunResponse:
    # 1. Fetch Planning Version & Validate Status
    version = db.scalar(select(PlanningVersion).where(PlanningVersion.id == req.planning_version_id).with_for_update())
    if not version:
        raise ApplicationError(
            "NOT_FOUND",
            f"Planning version '{req.planning_version_id}' not found",
            status_code=404,
        )
    latest = db.scalar(select(PlanningVersion).where(PlanningVersion.planning_period == version.planning_period)
                       .order_by(PlanningVersion.version_number.desc()).limit(1))
    if latest.id != version.id:
        raise ApplicationError("LATEST_REVISION_REQUIRED", "Calculate the latest revision for this planning period. Older results remain available as history.", 409)

    eligible_statuses = {
        "VALIDATED",
        "CALCULATED",
        "CALCULATED_WITH_ERRORS",
    }
    if version.status not in eligible_statuses:
        raise ApplicationError(
            "INVALID_VERSION_STATUS",
            f"Planning version '{version.id}' is in status '{version.status}', must be VALIDATED, LOCKED, or CALCULATED to run requirements calculation",
            status_code=400,
        )
    if db.scalar(select(PlantConfirmation.id).where(PlantConfirmation.planning_version_id == version.id).limit(1)):
        raise ApplicationError("CALCULATION_HISTORY_PROTECTED", "Confirmed calculations cannot be replaced. Create a new planning revision.", 409)

    # 2. Idempotency & Recalculation Cleanup
    # Atomically purge prior calculation run and error records for this version
    db.execute(
        delete(CalculatedRequirement).where(
            CalculatedRequirement.planning_version_id == req.planning_version_id
        )
    )
    db.execute(
        delete(RequirementCalculationError).where(
            RequirementCalculationError.planning_version_id == req.planning_version_id
        )
    )
    db.flush()

    # 3. Retrieve PRD Order Items
    stmt_items = (
        select(PRDOrderItem)
        .where(PRDOrderItem.planning_version_id == req.planning_version_id)
        .order_by(PRDOrderItem.source_row_number)
    )
    items = db.scalars(stmt_items).all()

    target_date = req.as_of_date or date.today()
    persisted_requirements: list[CalculatedRequirement] = []
    persisted_errors: list[RequirementCalculationError] = []

    # 4. Process Each Item Deterministically
    for item in items:
        if item.planned_quantity == Decimal("0"):
            continue
        # A. Product Resolution
        product = (
            db.get(Product, item.product_id)
            if item.product_id
            else db.scalars(select(Product).where(Product.code == item.product_code)).first()
        )
        if not product or not product.is_active:
            err = RequirementCalculationError(
                planning_version_id=version.id,
                prd_order_item_id=item.id,
                product_id=item.product_id,
                error_code="PRODUCT_NOT_FOUND",
                error_message=f"Product '{item.product_code}' could not be resolved",
            )
            db.add(err)
            persisted_errors.append(err)
            continue

        # B. Plant Resolution via ProductPlant
        plant_mapping_stmt = (
            select(ProductPlant)
            .options(joinedload(ProductPlant.plant))
            .where(ProductPlant.product_id == product.id, ProductPlant.is_active == True)
            .order_by(ProductPlant.is_primary.desc())
        )
        plant_mappings = db.scalars(plant_mapping_stmt).all()

        matched_plant: Optional[Plant] = None
        if plant_mappings:
            # If line specifies plant code, attempt to match plant name/location, else use primary
            if item.plant_code:
                for pm in plant_mappings:
                    if pm.plant and (pm.plant.name == item.plant_code):
                        matched_plant = pm.plant
                        break
            if not item.plant_code:
                candidates = [pm for pm in plant_mappings if pm.is_primary] if len(plant_mappings) > 1 else plant_mappings
                if len(candidates) == 1:
                    matched_plant = candidates[0].plant

        if not matched_plant or not matched_plant.is_active:
            err = RequirementCalculationError(
                planning_version_id=version.id,
                prd_order_item_id=item.id,
                product_id=product.id,
                error_code="MISSING_PLANT_MAPPING",
                error_message=f"No active plant mapping found for product '{product.code}' (plant code: '{item.plant_code}')",
            )
            db.add(err)
            persisted_errors.append(err)
            continue

        # C. Process & Consumable Mappings
        ppc_stmt = (
            select(ProductProcessConsumable)
            .options(
                joinedload(ProductProcessConsumable.process),
                joinedload(ProductProcessConsumable.consumable),
            )
            .where(
                ProductProcessConsumable.product_id == product.id,
                ProductProcessConsumable.is_active == True,
            )
        )
        consumable_mappings = db.scalars(ppc_stmt).all()

        if not consumable_mappings:
            err = RequirementCalculationError(
                planning_version_id=version.id,
                prd_order_item_id=item.id,
                product_id=product.id,
                plant_id=matched_plant.id,
                error_code="MISSING_PROCESS_MAPPING",
                error_message=f"Product '{product.code}' has no active consumable process mappings",
            )
            db.add(err)
            persisted_errors.append(err)
            continue

        # D. Rule Selection & Pure Evaluation for each mapped consumable
        for mapping in consumable_mappings:
            process = mapping.process
            consumable = mapping.consumable
            if not process or not consumable:
                continue

            consumable_unit = db.get(Unit, consumable.unit_id)
            consumable_unit_code = consumable_unit.code if consumable_unit else "PCS"

            candidate_queries = [
                # 1. Exact match
                select(ConsumptionNorm).where(
                    ConsumptionNorm.consumable_id == consumable.id,
                    ConsumptionNorm.product_id == product.id,
                    ConsumptionNorm.process_id == process.id,
                    ConsumptionNorm.plant_id == matched_plant.id,
                ),
                # 2. Plant-independent
                select(ConsumptionNorm).where(
                    ConsumptionNorm.consumable_id == consumable.id,
                    ConsumptionNorm.product_id == product.id,
                    ConsumptionNorm.process_id == process.id,
                    ConsumptionNorm.plant_id == None,
                ),
                # 3. Process-independent
                select(ConsumptionNorm).where(
                    ConsumptionNorm.consumable_id == consumable.id,
                    ConsumptionNorm.product_id == product.id,
                    ConsumptionNorm.process_id == None,
                    ConsumptionNorm.plant_id == None,
                ),
                # 4. Global fallback
                select(ConsumptionNorm).where(
                    ConsumptionNorm.consumable_id == consumable.id,
                    ConsumptionNorm.product_id == None,
                    ConsumptionNorm.process_id == None,
                    ConsumptionNorm.plant_id == None,
                ),
            ]

            selected_norm: Optional[ConsumptionNorm] = None
            for q in candidate_queries:
                q = q.options(joinedload(ConsumptionNorm.unit)).order_by(
                    ConsumptionNorm.version.desc()
                )
                norms = db.scalars(q).all()
                for n in norms:
                    if not n.is_active:
                        continue
                    if n.effective_from <= target_date and (
                        n.effective_to is None or n.effective_to >= target_date
                    ):
                        selected_norm = n
                        break
                if selected_norm:
                    break

            if not selected_norm:
                err = RequirementCalculationError(
                    planning_version_id=version.id,
                    prd_order_item_id=item.id,
                    product_id=product.id,
                    plant_id=matched_plant.id,
                    consumable_id=consumable.id,
                    error_code="MISSING_RULE",
                    error_message=f"No active, effective consumption rule found for consumable '{consumable.code}' on process '{process.name}'",
                )
                db.add(err)
                persisted_errors.append(err)
                continue

            # Pure domain engine calculation
            calc_unit = (
                selected_norm.unit.code
                if selected_norm.unit
                else consumable_unit_code
            )
            rule_input = RuleCalculationInput(
                rule_type=RuleType(selected_norm.rule_type),
                rule_version=selected_norm.version,
                parameters=selected_norm.parameters,
                production_quantity=item.planned_quantity,
                rounding_policy=RoundingPolicy.parse(selected_norm.rounding_policy),
                rounding_precision=selected_norm.rounding_precision,
                unit=calc_unit,
            )

            try:
                calc_result = evaluate_rule(rule_input)
            except RuleDomainError as rde:
                err = RequirementCalculationError(
                    planning_version_id=version.id,
                    prd_order_item_id=item.id,
                    product_id=product.id,
                    plant_id=matched_plant.id,
                    consumable_id=consumable.id,
                    error_code=rde.code,
                    error_message=rde.message,
                )
                db.add(err)
                persisted_errors.append(err)
                continue

            explanation = {
                "planning_version": {
                    "id": str(version.id),
                    "planning_period": version.planning_period,
                    "revision_label": version.revision_label,
                },
                "production_source": {
                    "prd_order_item_id": str(item.id),
                    "source_row_number": item.source_row_number,
                    "planned_quantity": str(item.planned_quantity),
                    "uom": item.uom,
                },
                "product": {
                    "id": str(product.id),
                    "code": product.code,
                    "name": product.name,
                },
                "plant": {
                    "id": str(matched_plant.id),
                    "name": matched_plant.name,
                },
                "process": {
                    "id": str(process.id),
                    "name": process.name,
                },
                "consumable": {
                    "id": str(consumable.id),
                    "code": consumable.code,
                    "name": consumable.name,
                },
                "rule": {
                    "id": str(selected_norm.id),
                    "rule_type": selected_norm.rule_type,
                    "version": selected_norm.version,
                    "parameters": selected_norm.parameters,
                },
                "calculation": {
                    "raw_requirement": str(calc_result.raw_requirement),
                    "rounding_policy": calc_result.rounding_policy.value,
                    "rounding_precision": calc_result.rounding_precision,
                    "calculated_qty": str(calc_result.final_calculated_requirement),
                    "steps": [s.model_dump(mode="json") for s in calc_result.calculation_steps],
                },
            }

            req_obj = CalculatedRequirement(
                planning_version_id=version.id,
                prd_order_item_id=item.id,
                product_id=product.id,
                plant_id=matched_plant.id,
                process_id=process.id,
                consumable_id=consumable.id,
                rule_id=selected_norm.id,
                rule_type=selected_norm.rule_type,
                rule_version=selected_norm.version,
                parameters=selected_norm.parameters,
                source_production_qty=item.planned_quantity,
                raw_requirement=calc_result.raw_requirement,
                rounding_policy=calc_result.rounding_policy.value,
                rounding_precision=calc_result.rounding_precision,
                calculated_qty=calc_result.final_calculated_requirement,
                unit_id=consumable.unit_id,
                uom=calc_unit,
                calculation_steps=[s.model_dump(mode="json") for s in calc_result.calculation_steps],
                explanation_payload=explanation,
            )
            db.add(req_obj)
            persisted_requirements.append(req_obj)

    # 5. Aggregate by Consumable using exact Decimal arithmetic
    consumable_totals: dict[UUID, dict[str, Any]] = defaultdict(
        lambda: {
            "raw_total": Decimal("0.0000"),
            "calculated_total": Decimal("0.0000"),
            "count": 0,
            "code": "",
            "name": "",
            "uom": "",
        }
    )

    for r in persisted_requirements:
        cid = r.consumable_id
        consumable_totals[cid]["raw_total"] += r.raw_requirement
        consumable_totals[cid]["calculated_total"] += r.calculated_qty
        consumable_totals[cid]["count"] += 1
        if not consumable_totals[cid]["code"]:
            cons = db.get(Consumable, cid)
            if cons:
                consumable_totals[cid]["code"] = cons.code
                consumable_totals[cid]["name"] = cons.name
            consumable_totals[cid]["uom"] = r.uom

    summary_list: list[ConsumableAggregateItem] = [
        ConsumableAggregateItem(
            consumable_id=cid,
            consumable_code=data["code"],
            consumable_name=data["name"],
            uom=data["uom"],
            total_raw_requirement=data["raw_total"],
            total_calculated_qty=data["calculated_total"],
            line_items_count=data["count"],
        )
        for cid, data in consumable_totals.items()
    ]

    # 6. Update Planning Version Status and Timestamp
    version.calculated_at = datetime.now(timezone.utc)
    if persisted_errors:
        version.status = "CALCULATED_WITH_ERRORS"
    else:
        version.status = "CALCULATED"

    db.add(AuditLog(actor_id=current_user_id, action="CALCULATE", entity_type="planning_version", entity_id=version.id,
        old_values=None, new_values={"status": version.status, "requirement_ids": [str(r.id) for r in persisted_requirements],
                                    "error_count": len(persisted_errors)}, reason="Explicit requirement calculation for validated revision"))
    db.commit()

    # Load relationships for error responses
    error_responses = [get_calculation_error_by_id(db, err.id) for err in persisted_errors]

    return RequirementCalculationRunResponse(
        planning_version_id=version.id,
        planning_period=version.planning_period,
        revision_label=version.revision_label,
        status=version.status,
        total_items_processed=len(items),
        successful_requirements_count=len(persisted_requirements),
        error_count=len(persisted_errors),
        summary_by_consumable=summary_list,
        errors=error_responses,
    )


def get_calculation_error_by_id(db: Session, error_id: UUID) -> RequirementCalculationErrorResponse:
    stmt = (
        select(RequirementCalculationError)
        .options(
            joinedload(RequirementCalculationError.product),
            joinedload(RequirementCalculationError.plant),
            joinedload(RequirementCalculationError.consumable),
        )
        .where(RequirementCalculationError.id == error_id)
    )
    err = db.scalars(stmt).first()
    if not err:
        raise ApplicationError("NOT_FOUND", f"Calculation error '{error_id}' not found", 404)
    return _to_error_response(err)


def get_calculated_requirements(
    db: Session,
    planning_version_id: UUID,
    plant_id: Optional[UUID] = None,
    consumable_id: Optional[UUID] = None,
) -> list[CalculatedRequirementResponse]:
    stmt = (
        select(CalculatedRequirement)
        .options(
            joinedload(CalculatedRequirement.product),
            joinedload(CalculatedRequirement.plant),
            joinedload(CalculatedRequirement.process),
            joinedload(CalculatedRequirement.consumable),
        )
        .where(CalculatedRequirement.planning_version_id == planning_version_id)
        .order_by(CalculatedRequirement.created_at.asc())
    )
    if plant_id is not None:
        stmt = stmt.where(CalculatedRequirement.plant_id == plant_id)
    if consumable_id is not None:
        stmt = stmt.where(CalculatedRequirement.consumable_id == consumable_id)

    records = db.scalars(stmt).all()
    return [_to_requirement_response(r) for r in records]


def get_calculation_errors(
    db: Session,
    planning_version_id: UUID,
) -> list[RequirementCalculationErrorResponse]:
    stmt = (
        select(RequirementCalculationError)
        .options(
            joinedload(RequirementCalculationError.product),
            joinedload(RequirementCalculationError.plant),
            joinedload(RequirementCalculationError.consumable),
        )
        .where(RequirementCalculationError.planning_version_id == planning_version_id)
        .order_by(RequirementCalculationError.created_at.asc())
    )
    errors = db.scalars(stmt).all()
    return [_to_error_response(e) for e in errors]


def is_admin_user(user: CurrentUser) -> bool:
    if user.is_super_admin or getattr(user, "is_superuser", False):
        return True
    roles_normalized = [str(r).upper().strip() for r in (user.roles or [])]
    return any(r in ("SUPER ADMIN", "SUPER_ADMIN", "ADMIN") for r in roles_normalized)


def is_admin_or_planner_user(user: CurrentUser) -> bool:
    if is_admin_user(user):
        return True
    roles_normalized = [str(r).upper().strip() for r in (user.roles or [])]
    return any(r in ("PLANNER",) for r in roles_normalized)


def auto_get_or_create_consumable(
    db: Session,
    item_id_or_code: str,
    name_or_desc: Optional[str] = None,
    unit_str: Optional[str] = None,
) -> Consumable:
    """Finds existing consumable by item_id (case-insensitive) or auto-creates it."""
    clean_code = item_id_or_code.strip()
    existing = db.execute(
        select(Consumable).where(
            or_(
                func.upper(Consumable.item_id) == clean_code.upper(),
                Consumable.item_id == clean_code,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # Find or create a matching Unit
    clean_unit = (unit_str or "NOS").strip().upper()
    if not clean_unit or clean_unit.lower() == "nan":
        clean_unit = "NOS"
    unit_obj = db.execute(
        select(Unit).where(
            or_(
                func.upper(Unit.code) == clean_unit,
                func.upper(Unit.name) == clean_unit,
            )
        )
    ).scalar_one_or_none()
    if not unit_obj:
        # Fallback to standard NOS
        unit_obj = db.execute(select(Unit).where(func.upper(Unit.code) == "NOS")).scalar_one_or_none()
        if not unit_obj:
            unit_obj = Unit(code="NOS", name="Numbers")
            db.add(unit_obj)
            db.flush()

    display_name = (name_or_desc or clean_code).strip()
    new_consumable = Consumable(
        item_id=clean_code,
        name=display_name,
        description=display_name,
        output_unit=unit_str or unit_obj.code,
        unit_id=unit_obj.id,
    )
    db.add(new_consumable)
    db.flush()
    return new_consumable


def _to_line_item_response(item: RequirementLineItem) -> RequirementLineItemResponse:
    item_id = None
    item_code = None
    consumable_name = None
    unit = None
    description = None
    if item.consumable:
        item_id = getattr(item.consumable, "item_id", None)
        item_code = item_id
        consumable_name = getattr(item.consumable, "name", None)
        unit = getattr(item.consumable, "output_unit", None)
        description = getattr(item.consumable, "description", None) or consumable_name

    return RequirementLineItemResponse(
        id=item.id,
        plan_id=item.plan_id,
        consumable_id=item.consumable_id,
        serial_no=item.serial_no,
        part_no=item.part_no,
        requested_qty=item.requested_qty,
        item_id=item_id,
        item_code=item_code,
        consumable_name=consumable_name,
        unit=unit,
        description=description,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_plan_response(plan: MonthlyRequirementPlan) -> MonthlyRequirementPlanResponse:
    status_str = plan.status.value if hasattr(plan.status, "value") else str(plan.status)
    items = sorted(
        [_to_line_item_response(it) for it in (plan.line_items or [])],
        key=lambda x: (x.serial_no is None, x.serial_no or 0, str(x.id or ""))
    )
    return MonthlyRequirementPlanResponse(
        id=plan.id,
        plant_id=plan.plant_id,
        month=plan.month,
        year=plan.year,
        status=status_str,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        line_items=items,
    )


def get_monthly_plans(
    db: Session,
    user: CurrentUser,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> list[MonthlyRequirementPlanResponse]:
    """Fetch monthly requirement plans.
    Auto-provisions missing plant plans in DRAFT status when month and year are specified.
    """
    ALL_PLANTS = ["PLANT_I", "PLANT_II", "PLANT_III", "PLANT_IV", "PLANT_V"]

    # Auto-provision plans if month and year are provided
    if month is not None and year is not None:
        if is_admin_or_planner_user(user):
            target_plants = ALL_PLANTS
        else:
            assigned = getattr(user, "assigned_plant", None)
            target_plants = [assigned] if assigned else []

        for p_id in target_plants:
            existing = db.execute(
                select(MonthlyRequirementPlan).where(
                    MonthlyRequirementPlan.plant_id == p_id,
                    MonthlyRequirementPlan.month == month,
                    MonthlyRequirementPlan.year == year,
                )
            ).scalar_one_or_none()
            if not existing:
                new_plan = MonthlyRequirementPlan(
                    plant_id=p_id,
                    month=month,
                    year=year,
                    status=RequirementStatus.DRAFT,
                )
                db.add(new_plan)
        db.commit()

    stmt = (
        select(MonthlyRequirementPlan)
        .options(
            selectinload(MonthlyRequirementPlan.line_items).joinedload(RequirementLineItem.consumable)
        )
        .order_by(MonthlyRequirementPlan.year.desc(), MonthlyRequirementPlan.month.desc())
    )
    if month is not None:
        stmt = stmt.where(MonthlyRequirementPlan.month == month)
    if year is not None:
        stmt = stmt.where(MonthlyRequirementPlan.year == year)

    if not is_admin_or_planner_user(user):
        assigned_plant = getattr(user, "assigned_plant", None)
        stmt = stmt.where(MonthlyRequirementPlan.plant_id == assigned_plant)

    plans = db.scalars(stmt).all()
    return [_to_plan_response(p) for p in plans]


def create_monthly_plan(
    db: Session,
    payload: MonthlyRequirementPlanCreate,
    user: CurrentUser,
) -> MonthlyRequirementPlanResponse:
    existing = db.execute(
        select(MonthlyRequirementPlan).where(
            MonthlyRequirementPlan.plant_id == payload.plant_id,
            MonthlyRequirementPlan.month == payload.month,
            MonthlyRequirementPlan.year == payload.year,
        )
    ).scalar_one_or_none()
    if existing:
        raise ApplicationError(
            "DUPLICATE_PLAN",
            f"Monthly requirement plan already exists for plant '{payload.plant_id}', month {payload.month}, year {payload.year}.",
            409,
        )

    plan = MonthlyRequirementPlan(
        plant_id=payload.plant_id,
        month=payload.month,
        year=payload.year,
        status=RequirementStatus.DRAFT,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _to_plan_response(plan)


def upsert_single_line_item(
    db: Session,
    plan_id: UUID,
    payload: RequirementLineItemCreate,
    user: CurrentUser,
) -> RequirementLineItemResponse:
    plan = db.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise ApplicationError("NOT_FOUND", "Monthly requirement plan not found.", 404)

    # Resolve or create Consumable
    consumable = None
    if payload.consumable_id:
        consumable = db.get(Consumable, payload.consumable_id)

    raw_item_code = (payload.item_code or payload.item_id or "").strip()
    if not consumable and raw_item_code:
        consumable = auto_get_or_create_consumable(
            db=db,
            item_id_or_code=raw_item_code,
            name_or_desc=payload.item_description,
            unit_str=payload.unit,
        )

    if not consumable:
        raise ApplicationError("NOT_FOUND", "Consumable not found and no valid item_code provided.", 400)

    # If payload provided part_no, update consumable if not set
    if payload.part_no and hasattr(consumable, "part_number") and not consumable.part_number:
        consumable.part_number = payload.part_no

    existing = db.execute(
        select(RequirementLineItem)
        .options(joinedload(RequirementLineItem.consumable))
        .where(
            RequirementLineItem.plan_id == plan_id,
            RequirementLineItem.consumable_id == consumable.id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.requested_qty = payload.requested_qty
        if payload.serial_no is not None:
            existing.serial_no = payload.serial_no
        if payload.part_no is not None:
            existing.part_no = payload.part_no
        item = existing
    else:
        # Determine serial_no if not provided
        serial_no = payload.serial_no
        if serial_no is None:
            max_sno = db.execute(
                select(func.max(RequirementLineItem.serial_no)).where(RequirementLineItem.plan_id == plan_id)
            ).scalar() or 0
            serial_no = max_sno + 1

        item = RequirementLineItem(
            plan_id=plan_id,
            consumable_id=consumable.id,
            serial_no=serial_no,
            part_no=payload.part_no,
            requested_qty=payload.requested_qty,
        )
        db.add(item)

    db.commit()
    db.refresh(item)
    if not item.consumable:
        item.consumable = consumable

    # Automatic background aggregation
    try:
        from app.services.mrp_calculator import run_monthly_aggregation
        run_monthly_aggregation(db, plan.month, plan.year)
    except Exception:
        pass

    return _to_line_item_response(item)


def update_single_line_item(
    db: Session,
    plan_id: UUID,
    item_id: UUID,
    payload: Any,  # RequirementLineItemUpdate
    user: CurrentUser,
) -> RequirementLineItemResponse:
    plan = db.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise ApplicationError("NOT_FOUND", "Monthly requirement plan not found.", 404)

    item = db.execute(
        select(RequirementLineItem)
        .options(joinedload(RequirementLineItem.consumable))
        .where(
            RequirementLineItem.id == item_id,
            RequirementLineItem.plan_id == plan_id,
        )
    ).scalar_one_or_none()

    if not item:
        raise ApplicationError("NOT_FOUND", "Requirement line item not found in this plan.", 404)

    if payload.requested_qty is not None:
        item.requested_qty = payload.requested_qty
    if payload.serial_no is not None:
        item.serial_no = payload.serial_no
    if payload.part_no is not None:
        item.part_no = payload.part_no

    if item.consumable:
        if payload.unit is not None:
            item.consumable.output_unit = payload.unit
        if payload.item_description is not None:
            item.consumable.description = payload.item_description
            if not item.consumable.name:
                item.consumable.name = payload.item_description

    db.commit()
    db.refresh(item)

    # Automatic background aggregation
    try:
        from app.services.mrp_calculator import run_monthly_aggregation
        run_monthly_aggregation(db, plan.month, plan.year)
    except Exception:
        pass

    return _to_line_item_response(item)


def delete_single_line_item(
    db: Session,
    plan_id: UUID,
    item_id: UUID,
    user: CurrentUser,
) -> dict[str, Any]:
    plan = db.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise ApplicationError("NOT_FOUND", "Monthly requirement plan not found.", 404)

    item = db.execute(
        select(RequirementLineItem).where(
            RequirementLineItem.id == item_id,
            RequirementLineItem.plan_id == plan_id,
        )
    ).scalar_one_or_none()

    if not item:
        raise ApplicationError("NOT_FOUND", "Requirement line item not found in this plan.", 404)

    db.delete(item)
    db.commit()

    # Automatic background aggregation
    try:
        from app.services.mrp_calculator import run_monthly_aggregation
        run_monthly_aggregation(db, plan.month, plan.year)
    except Exception:
        pass

    return {"message": "Line item deleted successfully", "id": str(item_id)}


def _normalize_plant_key(name: str) -> Optional[str]:
    """Map plant sheet name variations (e.g. 'Plant 1', 'PLANT I', 'Plant-1') to standard ID."""
    clean = name.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "PLANT1": "PLANT_I",
        "PLANTI": "PLANT_I",
        "PLANT2": "PLANT_II",
        "PLANTII": "PLANT_II",
        "PLANT3": "PLANT_III",
        "PLANTIII": "PLANT_III",
        "PLANT4": "PLANT_IV",
        "PLANTIV": "PLANT_IV",
        "PLANT5": "PLANT_V",
        "PLANTV": "PLANT_V",
    }
    if clean in mapping:
        return mapping[clean]
    # Check if string contains plant variations
    for plant_num, std_id in [
        ("1", "PLANT_I"),
        ("I", "PLANT_I"),
        ("2", "PLANT_II"),
        ("II", "PLANT_II"),
        ("3", "PLANT_III"),
        ("III", "PLANT_III"),
        ("4", "PLANT_IV"),
        ("IV", "PLANT_IV"),
        ("5", "PLANT_V"),
        ("V", "PLANT_V"),
    ]:
        if f"PLANT{plant_num}" in clean or f"PLANT-{plant_num}" in clean:
            return std_id
    return None


def _find_matching_sheet_name(sheet_names: list[str], target_plant_id: str) -> Optional[str]:
    """Find sheet name matching target_plant_id from sheet_names."""
    # Direct candidate matching
    plant_candidates_map = {
        "PLANT_I": ["Plant 1", "Plant I", "PLANT_I", "Plant-1", "PLANT1", "PLANTI", "Plant1", "PlantI"],
        "PLANT_II": ["Plant 2", "Plant II", "PLANT_II", "Plant-2", "PLANT2", "PLANTII", "Plant2", "PlantII"],
        "PLANT_III": ["Plant 3", "Plant III", "PLANT_III", "Plant-3", "PLANT3", "PLANTIII", "Plant3", "PlantIII"],
        "PLANT_IV": ["Plant 4", "Plant IV", "PLANT_IV", "Plant-4", "PLANT4", "PLANTIV", "Plant4", "PlantIV"],
        "PLANT_V": ["Plant 5", "Plant V", "PLANT_V", "Plant-5", "PLANT5", "PLANTV", "Plant5", "PlantV"],
    }
    candidates = plant_candidates_map.get(target_plant_id, [target_plant_id])
    for s in sheet_names:
        s_clean = s.strip()
        for cand in candidates:
            if s_clean.lower() == cand.lower():
                return s

    # Normalized comparison fallback
    for s in sheet_names:
        norm = _normalize_plant_key(s)
        if norm == target_plant_id:
            return s

    return None


def _parse_and_ingest_sheet(
    db: Session,
    target_plan: MonthlyRequirementPlan,
    df_raw: pd.DataFrame,
    errors: list[str],
    auto_create_consumables: bool = False,
) -> tuple[list[RequirementLineItem], int]:
    if df_raw.empty:
        return [], 0

    num_rows = len(df_raw)
    num_cols = len(df_raw.columns)
    scan_limit = min(10, num_rows)

    # 1. Dynamic Header & Month Row Detection in the first 10 rows
    header_row_idx: Optional[int] = None
    month_row_idx: Optional[int] = None

    for r_idx in range(scan_limit):
        row_raw_vals = [str(v).strip() for v in df_raw.iloc[r_idx] if pd.notna(v)]
        row_clean_vals = [
            str(v).strip().lower().replace(" ", "").replace(".", "").replace("_", "").replace("-", "")
            for v in df_raw.iloc[r_idx]
            if pd.notna(v)
        ]

        # Check for header row containing 'Item Id.' or 'Item Code'
        if header_row_idx is None:
            if any(term in row_clean_vals for term in ["itemid", "itemcode", "consumableid", "itemdescription", "sno", "serialno"]):
                header_row_idx = r_idx

        # Check for month row containing 'Month'
        if month_row_idx is None:
            if any("month" in term for term in row_clean_vals):
                month_row_idx = r_idx

    # If header_row_idx not found, fallback to row 0 if it has content, or find row with most non-nulls
    if header_row_idx is None:
        header_row_idx = 0

    # 2. Dynamic QTY Column Detection
    target_month_num = target_plan.month
    try:
        month_abbr = date(2000, target_month_num, 1).strftime("%b").lower()  # e.g., 'oct'
        month_full = date(2000, target_month_num, 1).strftime("%B").lower()  # e.g., 'october'
    except Exception:
        month_abbr = "oct"
        month_full = "october"

    qty_col_idx: Optional[int] = None

    # Search month_row_idx if present
    if month_row_idx is not None:
        for c_idx in range(num_cols):
            val = str(df_raw.iat[month_row_idx, c_idx]).strip().lower() if pd.notna(df_raw.iat[month_row_idx, c_idx]) else ""
            val_clean = val.replace(" ", "").replace("'", "")
            if month_abbr in val_clean or month_full in val_clean or f"m{target_month_num}" in val_clean:
                qty_col_idx = c_idx
                break

    # If no match in month_row_idx, search header_row_idx for month-specific label
    if qty_col_idx is None and header_row_idx is not None:
        for c_idx in range(num_cols):
            val = str(df_raw.iat[header_row_idx, c_idx]).strip().lower() if pd.notna(df_raw.iat[header_row_idx, c_idx]) else ""
            val_clean = val.replace(" ", "").replace("'", "")
            if month_abbr in val_clean or month_full in val_clean:
                qty_col_idx = c_idx
                break

    # Fallback to the first column containing 'QTY' or 'Qty'
    if qty_col_idx is None:
        # Check header_row_idx first
        if header_row_idx is not None:
            for c_idx in range(num_cols):
                val = str(df_raw.iat[header_row_idx, c_idx]).strip().lower() if pd.notna(df_raw.iat[header_row_idx, c_idx]) else ""
                val_clean = val.replace(" ", "").replace(".", "")
                if "qty" in val_clean or "quantity" in val_clean or "requestedqty" in val_clean:
                    qty_col_idx = c_idx
                    break

        # Check across the entire scan range if still not found
        if qty_col_idx is None:
            for r_idx in range(scan_limit):
                for c_idx in range(num_cols):
                    val = str(df_raw.iat[r_idx, c_idx]).strip().lower() if pd.notna(df_raw.iat[r_idx, c_idx]) else ""
                    val_clean = val.replace(" ", "").replace(".", "")
                    if "qty" in val_clean or "quantity" in val_clean:
                        qty_col_idx = c_idx
                        break
                if qty_col_idx is not None:
                    break

    # 3. Detect column indices for serial_no, item_code, item_description, part_no, unit
    sno_col_idx: Optional[int] = None
    item_col_idx: Optional[int] = None
    desc_col_idx: Optional[int] = None
    part_col_idx: Optional[int] = None
    unit_col_idx: Optional[int] = None

    if header_row_idx is not None:
        for c_idx in range(num_cols):
            val = str(df_raw.iat[header_row_idx, c_idx]).strip().lower().replace(" ", "").replace(".", "").replace("_", "").replace("-", "") if pd.notna(df_raw.iat[header_row_idx, c_idx]) else ""
            if not val:
                continue
            if sno_col_idx is None and any(cand in val for cand in ["sno", "serialno", "slno", "srno"]):
                sno_col_idx = c_idx
            elif item_col_idx is None and any(cand in val for cand in ["itemid", "itemcode", "consumableid", "consumablecode", "partnumber", "item", "code"]):
                item_col_idx = c_idx
            elif desc_col_idx is None and any(cand in val for cand in ["itemdescription", "description", "itemname", "name", "desc"]):
                desc_col_idx = c_idx
            elif part_col_idx is None and any(cand in val for cand in ["partno", "partnum", "partnumber"]):
                part_col_idx = c_idx
            elif unit_col_idx is None and any(cand in val for cand in ["unit", "uom", "outputunit"]):
                unit_col_idx = c_idx

    # Positional fallback if named detection didn't match:
    # Factory standard: Col 0/1: S.no., Col 1/2: Item Id., Col 2/3: Description, Col 3/4: Part No., Col 4/5: Unit
    if item_col_idx is None:
        if num_cols >= 2:
            item_col_idx = 1
        else:
            item_col_idx = 0

    if sno_col_idx is None and item_col_idx > 0:
        sno_col_idx = 0
    if desc_col_idx is None and item_col_idx + 1 < num_cols:
        desc_col_idx = item_col_idx + 1
    if part_col_idx is None and item_col_idx + 2 < num_cols:
        part_col_idx = item_col_idx + 2
    if unit_col_idx is None and item_col_idx + 3 < num_cols:
        unit_col_idx = item_col_idx + 3

    if qty_col_idx is None:
        raise ApplicationError(
            "PARSING_FAILED",
            f"Excel Parsing Failed: Could not identify QTY column for Month {target_plan.month} in sheet for plant '{target_plan.plant_id}'.",
            400,
        )

    # 4. Data Extraction from header_row_idx + 1 to the end
    existing_items_stmt = (
        select(RequirementLineItem)
        .options(joinedload(RequirementLineItem.consumable))
        .where(RequirementLineItem.plan_id == target_plan.id)
    )
    existing_items = {it.consumable_id: it for it in db.execute(existing_items_stmt).scalars().all()}
    upserted_dict: dict[UUID, RequirementLineItem] = {}

    start_row = (header_row_idx + 1) if header_row_idx is not None else 0
    total_processed_rows = 0

    for r_idx in range(start_row, num_rows):
        total_processed_rows += 1
        raw_item_val = df_raw.iat[r_idx, item_col_idx] if item_col_idx < num_cols else None
        if pd.isna(raw_item_val):
            continue
        raw_item = str(raw_item_val).strip()
        if not raw_item or raw_item.lower() in ("nan", "none", "total", "subtotal", "item id.", "item id", "item code"):
            continue

        raw_desc_val = df_raw.iat[r_idx, desc_col_idx] if desc_col_idx is not None and desc_col_idx < num_cols else None
        raw_desc = str(raw_desc_val).strip() if pd.notna(raw_desc_val) and str(raw_desc_val).strip().lower() not in ("nan", "none") else None

        raw_part_val = df_raw.iat[r_idx, part_col_idx] if part_col_idx is not None and part_col_idx < num_cols else None
        raw_part = str(raw_part_val).strip() if pd.notna(raw_part_val) and str(raw_part_val).strip().lower() not in ("nan", "none") else None

        raw_unit_val = df_raw.iat[r_idx, unit_col_idx] if unit_col_idx is not None and unit_col_idx < num_cols else None
        raw_unit = str(raw_unit_val).strip() if pd.notna(raw_unit_val) and str(raw_unit_val).strip().lower() not in ("nan", "none") else "NOS"

        sno_val = None
        if sno_col_idx is not None and sno_col_idx < num_cols:
            raw_sno = df_raw.iat[r_idx, sno_col_idx]
            if pd.notna(raw_sno):
                try:
                    sno_val = int(float(raw_sno))
                except Exception:
                    sno_val = None

        raw_qty = df_raw.iat[r_idx, qty_col_idx] if qty_col_idx < num_cols else None
        try:
            if pd.isna(raw_qty) or str(raw_qty).strip() in ("-", "", "nan", "none"):
                qty_val = 0.0
            else:
                qty_val = float(raw_qty)
            if qty_val < 0:
                qty_val = 0.0
        except Exception:
            qty_val = 0.0

        consumable = db.execute(
            select(Consumable).where(
                or_(
                    func.upper(Consumable.item_id) == raw_item.upper(),
                    Consumable.item_id == raw_item,
                )
            )
        ).scalar_one_or_none()

        if not consumable:
            if auto_create_consumables:
                consumable = auto_get_or_create_consumable(
                    db=db,
                    item_id_or_code=raw_item,
                    name_or_desc=raw_desc,
                    unit_str=raw_unit,
                )
            else:
                row_num = r_idx + 1
                errors.append(f"Row {row_num}: Item ID '{raw_item}' not found in Product Master.")
                continue

        if consumable.id in existing_items:
            item = existing_items[consumable.id]
            item.requested_qty = qty_val
            if sno_val is not None:
                item.serial_no = sno_val
            if raw_part is not None:
                item.part_no = raw_part
            item.consumable = consumable
            upserted_dict[consumable.id] = item
        elif consumable.id in upserted_dict:
            item = upserted_dict[consumable.id]
            item.requested_qty = qty_val
            if sno_val is not None:
                item.serial_no = sno_val
            if raw_part is not None:
                item.part_no = raw_part
            item.consumable = consumable
        else:
            new_item = RequirementLineItem(
                plan_id=target_plan.id,
                consumable_id=consumable.id,
                serial_no=sno_val or (len(upserted_dict) + 1),
                part_no=raw_part,
                requested_qty=qty_val,
            )
            new_item.consumable = consumable
            db.add(new_item)
            existing_items[consumable.id] = new_item
            upserted_dict[consumable.id] = new_item

    db.flush()
    return list(upserted_dict.values()), total_processed_rows


def bulk_upsert_line_items(
    db: Session,
    plan_id: UUID,
    file_bytes: bytes,
    filename: str,
    user: CurrentUser,
    upload_all_plants: bool = False,
    auto_create_consumables: bool = False,
) -> BulkUploadResponse:
    plan = db.get(MonthlyRequirementPlan, plan_id)
    if not plan:
        raise ApplicationError("NOT_FOUND", "Monthly requirement plan not found.", 404)

    if not file_bytes:
        raise ApplicationError("INVALID_FILE", "Uploaded file is empty.", 400)

    filename_lower = filename.lower()
    is_excel = filename_lower.endswith((".xlsx", ".xls"))

    errors: list[str] = []
    total_rows = 0
    all_upserted_items: list[RequirementLineItem] = []
    plants_affected = [plan.plant_id]

    try:
        if is_excel:
            # Safe Sheet Matching using header=None
            sheets_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, header=None)
            sheet_names = list(sheets_dict.keys())

            recognized_sheets: dict[str, str] = {}
            for s in sheet_names:
                pkey = _normalize_plant_key(s)
                if pkey:
                    recognized_sheets[pkey] = s

            CANONICAL_PLANTS = ["PLANT_I", "PLANT_II", "PLANT_III", "PLANT_IV", "PLANT_V"]

            if upload_all_plants and is_admin_user(user):
                plants_affected = []
                for pkey in CANONICAL_PLANTS:
                    sname = _find_matching_sheet_name(sheet_names, pkey)
                    if not sname and pkey in recognized_sheets:
                        sname = recognized_sheets[pkey]
                    if not sname:
                        continue

                    df_sheet = sheets_dict[sname]
                    # Get or create plan for this plant
                    p_plan = db.execute(
                        select(MonthlyRequirementPlan).where(
                            MonthlyRequirementPlan.plant_id == pkey,
                            MonthlyRequirementPlan.month == plan.month,
                            MonthlyRequirementPlan.year == plan.year,
                        )
                    ).scalar_one_or_none()

                    if not p_plan:
                        p_plan = MonthlyRequirementPlan(
                            plant_id=pkey,
                            month=plan.month,
                            year=plan.year,
                            status=RequirementStatus.DRAFT,
                        )
                        db.add(p_plan)
                        db.flush()

                    try:
                        items, sheet_rows = _parse_and_ingest_sheet(db, p_plan, df_sheet, errors, auto_create_consumables=True)
                        total_rows += sheet_rows
                        all_upserted_items.extend(items)
                        plants_affected.append(pkey)
                    except Exception as sheet_err:
                        raise ApplicationError("PARSING_FAILED", f"Failed parsing {sname}: {str(sheet_err)}", 400)
            else:
                # Single plant mode: find matching sheet for target plan
                matched_sheet = _find_matching_sheet_name(sheet_names, plan.plant_id)
                if not matched_sheet:
                    matched_sheet = sheet_names[0]

                df_sheet = sheets_dict[matched_sheet]
                try:
                    items, sheet_rows = _parse_and_ingest_sheet(db, plan, df_sheet, errors, auto_create_consumables=auto_create_consumables)
                    total_rows += sheet_rows
                    all_upserted_items.extend(items)
                except Exception as sheet_err:
                    raise ApplicationError("PARSING_FAILED", f"Failed parsing {matched_sheet}: {str(sheet_err)}", 400)
        else:
            # CSV parsing
            try:
                df_csv = pd.read_csv(io.BytesIO(file_bytes), header=None)
            except Exception:
                df_csv = pd.read_excel(io.BytesIO(file_bytes), header=None)

            try:
                items, sheet_rows = _parse_and_ingest_sheet(db, plan, df_csv, errors, auto_create_consumables=auto_create_consumables)
                total_rows += sheet_rows
                all_upserted_items.extend(items)
            except Exception as sheet_err:
                raise ApplicationError("PARSING_FAILED", f"Failed parsing {filename}: {str(sheet_err)}", 400)

        db.commit()

        # Automatic background aggregation
        try:
            from app.services.mrp_calculator import run_monthly_aggregation
            run_monthly_aggregation(db, plan.month, plan.year)
        except Exception:
            pass

        results = [_to_line_item_response(it) for it in all_upserted_items]
        return BulkUploadResponse(
            total_rows=total_rows,
            upserted=len(results),
            errors=errors,
            items=results,
            plants_affected=list(set(plants_affected)),
        )
    except ApplicationError:
        raise
    except Exception as exc:
        raise ApplicationError("PARSING_FAILED", f"Excel Parsing Failed: {str(exc)}", 400)



