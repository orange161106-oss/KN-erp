from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

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
from app.models.requirements import CalculatedRequirement, RequirementCalculationError
from app.models.rules import ConsumptionNorm
from app.schemas.requirements import (
    CalculatedRequirementResponse,
    CalculationRunRequest,
    ConsumableAggregateItem,
    RequirementCalculationErrorResponse,
    RequirementCalculationRunResponse,
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
    version = db.get(PlanningVersion, req.planning_version_id)
    if not version:
        raise ApplicationError(
            "NOT_FOUND",
            f"Planning version '{req.planning_version_id}' not found",
            status_code=404,
        )

    eligible_statuses = {
        "VALIDATED",
        "LOCKED",
        "CALCULATED",
        "CALCULATED_WITH_ERRORS",
        "APPROVED",
    }
    if version.status not in eligible_statuses:
        raise ApplicationError(
            "INVALID_VERSION_STATUS",
            f"Planning version '{version.id}' is in status '{version.status}', must be VALIDATED, LOCKED, or CALCULATED to run requirements calculation",
            status_code=400,
        )

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
        # A. Product Resolution
        product = (
            db.get(Product, item.product_id)
            if item.product_id
            else db.scalars(select(Product).where(Product.code == item.product_code)).first()
        )
        if not product:
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
                    if pm.plant and (pm.plant.name == item.plant_code or item.plant_code in pm.plant.name):
                        matched_plant = pm.plant
                        break
            if not matched_plant and plant_mappings[0].plant:
                matched_plant = plant_mappings[0].plant

        if not matched_plant:
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
                rounding_policy=RoundingPolicy(selected_norm.rounding_policy),
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

