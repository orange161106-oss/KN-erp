from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApplicationError
from app.domain.rules import (
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
    validate_rule_parameters,
)
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.masters import Product
from app.models.prd import PlanningVersion, PRDOrderItem
from app.models.production import Plant, Process
from app.models.rules import ConsumptionNorm
from app.schemas.rules import (
    ConsumableRef,
    ConsumptionNormCreate,
    ConsumptionNormResponse,
    ConsumptionNormUpdate,
    EvaluationRequest,
    EvaluationResponse,
    ItemCalculationRequest,
    PlanningVersionRef,
    PlantRef,
    ProcessRef,
    ProductionSourceRef,
    ProductRef,
    RuleRef,
    SingleRequirementCalculationResponse,
)


def _to_norm_response(norm: ConsumptionNorm) -> ConsumptionNormResponse:
    return ConsumptionNormResponse(
        id=norm.id,
        rule_type=RuleType(norm.rule_type),
        consumable_id=norm.consumable_id,
        product_id=norm.product_id,
        process_id=norm.process_id,
        plant_id=norm.plant_id,
        version=norm.version,
        parameters=norm.parameters,
        unit_id=norm.unit_id,
        rounding_policy=RoundingPolicy.parse(norm.rounding_policy),
        rounding_precision=norm.rounding_precision,
        effective_from=norm.effective_from,
        effective_to=norm.effective_to,
        is_active=norm.is_active,
        created_at=norm.created_at,
        updated_at=norm.updated_at,
        consumable_code=norm.consumable.code if norm.consumable else None,
        consumable_name=norm.consumable.name if norm.consumable else None,
        product_code=norm.product.code if norm.product else None,
        product_name=norm.product.name if norm.product else None,
        process_name=norm.process.name if norm.process else None,
        plant_name=norm.plant.name if norm.plant else None,
        unit_code=norm.unit.code if norm.unit else None,
    )


def create_consumption_norm(
    db: Session, data: ConsumptionNormCreate
) -> ConsumptionNormResponse:
    # 1. Validate entity existence and active status
    consumable = db.get(Consumable, data.consumable_id)
    if not consumable:
        raise ApplicationError("NOT_FOUND", f"Consumable '{data.consumable_id}' not found", 404)
    if not consumable.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Consumable '{consumable.code}' is inactive", 400)

    unit = db.get(Unit, data.unit_id)
    if not unit:
        raise ApplicationError("NOT_FOUND", f"Unit '{data.unit_id}' not found", 404)
    if not unit.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Unit '{unit.code}' is inactive", 400)

    if data.product_id is not None:
        product = db.get(Product, data.product_id)
        if not product:
            raise ApplicationError("NOT_FOUND", f"Product '{data.product_id}' not found", 404)
        if not product.is_active:
            raise ApplicationError("INACTIVE_ENTITY", f"Product '{product.code}' is inactive", 400)

    if data.process_id is not None:
        process = db.get(Process, data.process_id)
        if not process:
            raise ApplicationError("NOT_FOUND", f"Process '{data.process_id}' not found", 404)
        if not process.is_active:
            raise ApplicationError("INACTIVE_ENTITY", f"Process '{process.name}' is inactive", 400)

    if data.plant_id is not None:
        plant = db.get(Plant, data.plant_id)
        if not plant:
            raise ApplicationError("NOT_FOUND", f"Plant '{data.plant_id}' not found", 404)
        if not plant.is_active:
            raise ApplicationError("INACTIVE_ENTITY", f"Plant '{plant.name}' is inactive", 400)

    # 2. Pure domain parameter validation
    try:
        validated_params = validate_rule_parameters(data.rule_type, data.parameters)
        parameters_dict = validated_params.model_dump(mode="json")
    except RuleDomainError as e:
        raise ApplicationError(e.code, e.message, status_code=400)

    # 3. Determine version and maintain historical immutability
    stmt = (
        select(ConsumptionNorm)
        .where(
            ConsumptionNorm.consumable_id == data.consumable_id,
            ConsumptionNorm.product_id == data.product_id,
            ConsumptionNorm.process_id == data.process_id,
            ConsumptionNorm.plant_id == data.plant_id,
        )
        .order_by(ConsumptionNorm.version.desc())
    )
    existing_norms = db.scalars(stmt).all()

    next_version = 1
    if existing_norms:
        next_version = existing_norms[0].version + 1
        # Supersede previous active norm
        db.execute(
            update(ConsumptionNorm)
            .where(
                ConsumptionNorm.consumable_id == data.consumable_id,
                ConsumptionNorm.product_id == data.product_id,
                ConsumptionNorm.process_id == data.process_id,
                ConsumptionNorm.plant_id == data.plant_id,
            )
            .values(is_active=False)
        )

    norm = ConsumptionNorm(
        rule_type=data.rule_type.value,
        consumable_id=data.consumable_id,
        product_id=data.product_id,
        process_id=data.process_id,
        plant_id=data.plant_id,
        version=next_version,
        parameters=parameters_dict,
        unit_id=data.unit_id,
        rounding_policy=data.rounding_policy.value,
        rounding_precision=data.rounding_precision,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        is_active=True,
    )
    db.add(norm)
    db.commit()
    db.refresh(norm)
    return get_consumption_norm(db, norm.id)


def get_consumption_norm(db: Session, norm_id: UUID) -> ConsumptionNormResponse:
    stmt = (
        select(ConsumptionNorm)
        .options(
            joinedload(ConsumptionNorm.consumable),
            joinedload(ConsumptionNorm.product),
            joinedload(ConsumptionNorm.process),
            joinedload(ConsumptionNorm.plant),
            joinedload(ConsumptionNorm.unit),
        )
        .where(ConsumptionNorm.id == norm_id)
    )
    norm = db.scalars(stmt).first()
    if not norm:
        raise ApplicationError("NOT_FOUND", f"Consumption norm {norm_id} not found", 404)
    return _to_norm_response(norm)


def list_consumption_norms(
    db: Session,
    consumable_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    process_id: Optional[UUID] = None,
    plant_id: Optional[UUID] = None,
    is_active: Optional[bool] = None,
) -> list[ConsumptionNormResponse]:
    stmt = (
        select(ConsumptionNorm)
        .options(
            joinedload(ConsumptionNorm.consumable),
            joinedload(ConsumptionNorm.product),
            joinedload(ConsumptionNorm.process),
            joinedload(ConsumptionNorm.plant),
            joinedload(ConsumptionNorm.unit),
        )
        .order_by(ConsumptionNorm.created_at.desc())
    )
    if consumable_id is not None:
        stmt = stmt.where(ConsumptionNorm.consumable_id == consumable_id)
    if product_id is not None:
        stmt = stmt.where(ConsumptionNorm.product_id == product_id)
    if process_id is not None:
        stmt = stmt.where(ConsumptionNorm.process_id == process_id)
    if plant_id is not None:
        stmt = stmt.where(ConsumptionNorm.plant_id == plant_id)
    if is_active is not None:
        stmt = stmt.where(ConsumptionNorm.is_active == is_active)

    records = db.scalars(stmt).all()
    return [_to_norm_response(r) for r in records]


def update_consumption_norm(
    db: Session, norm_id: UUID, data: ConsumptionNormUpdate
) -> ConsumptionNormResponse:
    norm = db.get(ConsumptionNorm, norm_id)
    if not norm:
        raise ApplicationError("NOT_FOUND", f"Consumption norm {norm_id} not found", 404)

    if data.parameters is not None:
        try:
            validated = validate_rule_parameters(RuleType(norm.rule_type), data.parameters)
            norm.parameters = validated.model_dump(mode="json")
        except RuleDomainError as e:
            raise ApplicationError(e.code, e.message, status_code=400)

    if data.rounding_policy is not None:
        norm.rounding_policy = data.rounding_policy.value
    if data.rounding_precision is not None:
        norm.rounding_precision = data.rounding_precision
    if data.effective_from is not None:
        norm.effective_from = data.effective_from
    if data.effective_to is not None:
        norm.effective_to = data.effective_to
    if data.is_active is not None:
        norm.is_active = data.is_active

    db.commit()
    db.refresh(norm)
    return get_consumption_norm(db, norm.id)


def evaluate_consumption_norm(
    db: Session, req: EvaluationRequest
) -> EvaluationResponse:
    target_date = req.as_of_date or date.today()

    # Search candidates from most specific to global fallback
    candidate_queries = [
        # 1. Exact: consumable + product + process + plant
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == req.consumable_id,
            ConsumptionNorm.product_id == req.product_id,
            ConsumptionNorm.process_id == req.process_id,
            ConsumptionNorm.plant_id == req.plant_id,
        ),
        # 2. Plant-wide for product & process
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == req.consumable_id,
            ConsumptionNorm.product_id == req.product_id,
            ConsumptionNorm.process_id == req.process_id,
            ConsumptionNorm.plant_id == None,
        ),
        # 3. Process-independent for product
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == req.consumable_id,
            ConsumptionNorm.product_id == req.product_id,
            ConsumptionNorm.process_id == None,
            ConsumptionNorm.plant_id == None,
        ),
        # 4. Global fallback for consumable
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == req.consumable_id,
            ConsumptionNorm.product_id == None,
            ConsumptionNorm.process_id == None,
            ConsumptionNorm.plant_id == None,
        ),
    ]

    selected_norm: Optional[ConsumptionNorm] = None
    for stmt in candidate_queries:
        stmt = stmt.options(joinedload(ConsumptionNorm.unit)).order_by(ConsumptionNorm.version.desc())
        norms = db.scalars(stmt).all()
        for norm in norms:
            if not norm.is_active:
                continue
            if norm.effective_from <= target_date and (norm.effective_to is None or norm.effective_to >= target_date):
                selected_norm = norm
                break
        if selected_norm:
            break

    if not selected_norm:
        raise ApplicationError(
            "MISSING_RULE",
            f"No active, effective consumption rule found for consumable {req.consumable_id} as of {target_date}",
            status_code=404,
        )

    # Pure domain calculation execution
    rule_input = RuleCalculationInput(
        rule_type=RuleType(selected_norm.rule_type),
        rule_version=selected_norm.version,
        parameters=selected_norm.parameters,
        production_quantity=req.production_quantity,
        rounding_policy=RoundingPolicy.parse(selected_norm.rounding_policy),
        rounding_precision=selected_norm.rounding_precision,
        unit=selected_norm.unit.code if selected_norm.unit else "PCS",
        requested_quantity=req.requested_quantity,
    )

    try:
        calc_result = evaluate_rule(rule_input)
    except RuleDomainError as e:
        raise ApplicationError(e.code, e.message, status_code=400)

    return EvaluationResponse(norm_id=selected_norm.id, calculation=calc_result)


def calculate_single_item_requirement(
    db: Session, req: ItemCalculationRequest
) -> SingleRequirementCalculationResponse:
    # 1. Production Source (PRDOrderItem)
    prd_item = db.get(PRDOrderItem, req.prd_item_id)
    if not prd_item:
        raise ApplicationError("NOT_FOUND", f"PRD order item '{req.prd_item_id}' not found", 404)

    # 2. Planning Version
    plan_version = db.get(PlanningVersion, prd_item.planning_version_id)
    if not plan_version:
        raise ApplicationError("NOT_FOUND", f"Planning version '{prd_item.planning_version_id}' not found", 404)

    # 3. Product Resolution
    product = (
        db.get(Product, prd_item.product_id)
        if prd_item.product_id
        else db.scalars(select(Product).where(Product.code == prd_item.product_code)).first()
    )
    if not product:
        raise ApplicationError("NOT_FOUND", f"Product '{prd_item.product_code}' not found", 404)

    # 4. Consumable Resolution
    consumable = db.get(Consumable, req.consumable_id)
    if not consumable:
        raise ApplicationError("NOT_FOUND", f"Consumable '{req.consumable_id}' not found", 404)
    consumable_unit = db.get(Unit, consumable.unit_id)
    consumable_unit_code = consumable_unit.code if consumable_unit else "PCS"

    # 5. Plant Resolution
    plant = None
    if req.plant_id:
        plant = db.get(Plant, req.plant_id)
        if not plant:
            raise ApplicationError("NOT_FOUND", f"Plant '{req.plant_id}' not found", 404)
    else:
        plant_mapping = db.scalars(
            select(ProductPlant)
            .options(joinedload(ProductPlant.plant))
            .where(ProductPlant.product_id == product.id, ProductPlant.is_active == True)
            .order_by(ProductPlant.is_primary.desc())
        ).first()
        if plant_mapping and plant_mapping.plant:
            plant = plant_mapping.plant
        else:
            raise ApplicationError("NOT_FOUND", f"No active plant mapping found for product '{product.code}'", 404)

    # 6. Process Resolution via ProductProcessConsumable mapping
    mapping = db.scalars(
        select(ProductProcessConsumable)
        .options(joinedload(ProductProcessConsumable.process))
        .where(
            ProductProcessConsumable.product_id == product.id,
            ProductProcessConsumable.consumable_id == consumable.id,
            ProductProcessConsumable.is_active == True,
        )
    ).first()
    if not mapping or not mapping.process:
        raise ApplicationError(
            "NOT_FOUND",
            f"Consumable '{consumable.code}' is not mapped to any process step for product '{product.code}'",
            404,
        )
    process = mapping.process

    # 7. Rule / Consumption Norm Resolution
    target_date = req.as_of_date or date.today()
    candidate_queries = [
        # Exact: consumable + product + process + plant
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == consumable.id,
            ConsumptionNorm.product_id == product.id,
            ConsumptionNorm.process_id == process.id,
            ConsumptionNorm.plant_id == plant.id,
        ),
        # Plant-independent for product & process
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == consumable.id,
            ConsumptionNorm.product_id == product.id,
            ConsumptionNorm.process_id == process.id,
            ConsumptionNorm.plant_id == None,
        ),
        # Process-independent for product
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == consumable.id,
            ConsumptionNorm.product_id == product.id,
            ConsumptionNorm.process_id == None,
            ConsumptionNorm.plant_id == None,
        ),
        # Global fallback for consumable
        select(ConsumptionNorm).where(
            ConsumptionNorm.consumable_id == consumable.id,
            ConsumptionNorm.product_id == None,
            ConsumptionNorm.process_id == None,
            ConsumptionNorm.plant_id == None,
        ),
    ]

    selected_norm: Optional[ConsumptionNorm] = None
    for q in candidate_queries:
        q = q.options(joinedload(ConsumptionNorm.unit)).order_by(ConsumptionNorm.version.desc())
        norms = db.scalars(q).all()
        for n in norms:
            if not n.is_active:
                continue
            if n.effective_from <= target_date and (n.effective_to is None or n.effective_to >= target_date):
                selected_norm = n
                break
        if selected_norm:
            break

    if not selected_norm:
        raise ApplicationError(
            "MISSING_RULE",
            f"No active, effective consumption rule found for consumable '{consumable.code}' as of {target_date}",
            status_code=404,
        )

    # 8. Deterministic Calculation via Domain Engine
    unit_code = (
        selected_norm.unit.code
        if selected_norm.unit
        else consumable_unit_code
    )
    rule_input = RuleCalculationInput(
        rule_type=RuleType(selected_norm.rule_type),
        rule_version=selected_norm.version,
        parameters=selected_norm.parameters,
        production_quantity=prd_item.planned_quantity,
        rounding_policy=RoundingPolicy.parse(selected_norm.rounding_policy),
        rounding_precision=selected_norm.rounding_precision,
        unit=unit_code,
    )

    try:
        calc_result = evaluate_rule(rule_input)
    except RuleDomainError as e:
        raise ApplicationError(e.code, e.message, status_code=400)

    # 9. Fully Explainable Contract Assembly
    return SingleRequirementCalculationResponse(
        planning_version=PlanningVersionRef(
            id=plan_version.id,
            planning_period=plan_version.planning_period,
            version_number=plan_version.version_number,
            revision_label=plan_version.revision_label,
            status=plan_version.status,
        ),
        production_source=ProductionSourceRef(
            item_id=prd_item.id,
            row_number=prd_item.source_row_number,
            planned_quantity=prd_item.planned_quantity,
            uom=prd_item.uom,
            target_period=prd_item.target_period,
        ),
        product=ProductRef(
            id=product.id,
            code=product.code,
            name=product.name,
        ),
        plant=PlantRef(
            id=plant.id,
            name=plant.name,
            location=plant.location,
        ),
        process=ProcessRef(
            id=process.id,
            name=process.name,
            description=process.description,
        ),
        consumable=ConsumableRef(
            id=consumable.id,
            code=consumable.code,
            name=consumable.name,
            unit=consumable_unit_code,
        ),
        rule=RuleRef(
            norm_id=selected_norm.id,
            rule_type=selected_norm.rule_type,
            version=selected_norm.version,
            parameters=selected_norm.parameters,
        ),
        calculation=calc_result,
    )

