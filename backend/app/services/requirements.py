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
        key=lambda x: (x.serial_no is None, x.serial_no or 0, str(x.item_id or ""))
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
) -> list[MonthlyRequirementPlanResponse]:
    stmt = (
        select(MonthlyRequirementPlan)
        .options(
            selectinload(MonthlyRequirementPlan.line_items).joinedload(RequirementLineItem.consumable)
        )
        .order_by(MonthlyRequirementPlan.year.desc(), MonthlyRequirementPlan.month.desc())
    )
    if not is_admin_user(user):
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
    return mapping.get(clean)


def _parse_and_ingest_sheet(
    db: Session,
    target_plan: MonthlyRequirementPlan,
    df_raw: pd.DataFrame,
    errors: list[str],
    auto_create_consumables: bool = False,
) -> tuple[list[RequirementLineItem], int]:
    if df_raw.empty:
        return [], 0

    # Look for the header row containing item id / item code / part
    header_row_idx = None
    for r_idx in range(min(15, len(df_raw))):
        row_vals = [str(v).strip().lower().replace(" ", "").replace(".", "") for v in df_raw.iloc[r_idx].dropna()]
        if any(c in row_vals for c in ["itemid", "itemcode", "partno", "itemdescription", "sno"]):
            header_row_idx = r_idx
            break

    if header_row_idx is not None:
        df = df_raw.iloc[header_row_idx + 1:].copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[header_row_idx]]
    else:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df.columns]

    norm_cols = {
        str(c).strip().lower().replace(" ", "").replace("_", "").replace("-", "").replace(".", ""): c
        for c in df.columns
    }

    sno_candidates = ["sno", "serialno", "slno", "sno.", "srno"]
    item_candidates = ["itemid", "itemcode", "consumableid", "consumablecode", "partnumber", "item", "code"]
    desc_candidates = ["itemdescription", "description", "itemname", "name", "desc"]
    part_candidates = ["partno", "partnum", "partnumber"]
    unit_candidates = ["unit", "uom", "outputunit"]
    qty_candidates = ["qty", "quantity", "requestedqty", "reqqty", "planqty", "orderqty", "monthlyqty"]

    sno_col = next((norm_cols[c] for c in sno_candidates if c in norm_cols), None)
    item_col = next((norm_cols[c] for c in item_candidates if c in norm_cols), None)
    desc_col = next((norm_cols[c] for c in desc_candidates if c in norm_cols), None)
    part_col = next((norm_cols[c] for c in part_candidates if c in norm_cols), None)
    unit_col = next((norm_cols[c] for c in unit_candidates if c in norm_cols), None)
    qty_col = next((norm_cols[c] for c in qty_candidates if c in norm_cols), None)

    # If no generic QTY column, check for month header match (e.g. 'Oct', 'Oct 26', '10')
    if not qty_col:
        target_month_name = date(2000, target_plan.month, 1).strftime("%b").lower()
        for c in df.columns:
            c_clean = str(c).strip().lower().replace(" ", "").replace("'", "")
            if target_month_name in c_clean or f"m{target_plan.month}" in c_clean:
                qty_col = c
                break

    if not item_col or not qty_col:
        errors.append(f"Sheet for plant '{target_plan.plant_id}' is missing required columns (Item ID and QTY). Found: {list(df.columns)}")
        return [], len(df)

    # Fetch existing items for this plan
    existing_items_stmt = (
        select(RequirementLineItem)
        .options(joinedload(RequirementLineItem.consumable))
        .where(RequirementLineItem.plan_id == target_plan.id)
    )
    existing_items = {it.consumable_id: it for it in db.execute(existing_items_stmt).scalars().all()}
    upserted_dict: dict[UUID, RequirementLineItem] = {}

    for idx, row in df.iterrows():
        raw_item = str(row[item_col]).strip() if pd.notna(row[item_col]) else ""
        if not raw_item or raw_item.lower() in ("nan", "none", "total", "subtotal"):
            continue

        raw_desc = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else None
        raw_part = str(row[part_col]).strip() if part_col and pd.notna(row[part_col]) else None
        raw_unit = str(row[unit_col]).strip() if unit_col and pd.notna(row[unit_col]) else "NOS"

        sno_val = None
        if sno_col and pd.notna(row[sno_col]):
            try:
                sno_val = int(float(row[sno_col]))
            except Exception:
                sno_val = None

        raw_qty = row[qty_col]
        try:
            if pd.isna(raw_qty) or str(raw_qty).strip() in ("-", "", "nan"):
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
                row_num = idx + 2
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
    return list(upserted_dict.values()), len(df)


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

    if is_excel:
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
            sheet_names = excel_file.sheet_names
        except Exception as exc:
            raise ApplicationError("INVALID_FILE", f"Failed to parse Excel workbook: {str(exc)}", 400)

        # Multi-plant mode or multiple plant sheets detected
        recognized_sheets = {}
        for s in sheet_names:
            pkey = _normalize_plant_key(s)
            if pkey:
                recognized_sheets[pkey] = s

        if upload_all_plants and is_admin_user(user) and recognized_sheets:
            plants_affected = []
            for pkey, sname in recognized_sheets.items():
                df_sheet = pd.read_excel(excel_file, sheet_name=sname, header=None)
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

                items, sheet_rows = _parse_and_ingest_sheet(db, p_plan, df_sheet, errors, auto_create_consumables=True)
                total_rows += sheet_rows
                all_upserted_items.extend(items)
                plants_affected.append(pkey)
        else:
            # Single plant mode: check if there's a sheet specifically matching current plant
            matched_sheet = None
            for s in sheet_names:
                if _normalize_plant_key(s) == plan.plant_id:
                    matched_sheet = s
                    break
            if not matched_sheet:
                matched_sheet = sheet_names[0]

            df_sheet = pd.read_excel(excel_file, sheet_name=matched_sheet, header=None)
            items, sheet_rows = _parse_and_ingest_sheet(db, plan, df_sheet, errors, auto_create_consumables=auto_create_consumables)
            total_rows += sheet_rows
            all_upserted_items.extend(items)
    else:
        # CSV parsing
        try:
            df_csv = pd.read_csv(io.BytesIO(file_bytes), header=None)
        except Exception:
            try:
                df_csv = pd.read_excel(io.BytesIO(file_bytes), header=None)
            except Exception as exc:
                raise ApplicationError("INVALID_FILE", f"Failed to parse CSV/Excel file: {str(exc)}", 400)

        items, sheet_rows = _parse_and_ingest_sheet(db, plan, df_csv, errors, auto_create_consumables=auto_create_consumables)
        total_rows += sheet_rows
        all_upserted_items.extend(items)

    db.commit()

    results = [_to_line_item_response(it) for it in all_upserted_items]
    return BulkUploadResponse(
        total_rows=total_rows,
        upserted=len(results),
        errors=errors,
        items=results,
        plants_affected=list(set(plants_affected)),
    )


