from datetime import date
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID, uuid4

from sqlalchemy import select, update, text
from sqlalchemy.orm import Session, joinedload
from pydantic import ValidationError

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
from app.models.audit import AuditLog
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


def _to_norm_response(norm: ConsumptionNorm, reference_data=None) -> ConsumptionNormResponse:
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
        product_part_number=norm.product.part_number if norm.product else None,
        product_item_id=norm.product.item_id if norm.product else None,
        reference_data=reference_data,
    )


def norm_reference_data(db: Session, ids: list[UUID]) -> dict[UUID, dict]:
    """Read immutable row provenance from the existing audit store in one query."""
    if not ids:
        return {}
    rows = db.execute(select(AuditLog.entity_id, AuditLog.new_values).where(AuditLog.entity_type == "ConsumptionNorm",
        AuditLog.entity_id.in_(ids)).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()))
    result = {}
    for row in rows:
        values = row.new_values or {}
        if row.entity_id not in result and "reference_data" in values:
            result[row.entity_id] = values["reference_data"]
    return result


def _reference_data(value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    allowed = {"part_number", "part_name", "used_part_number", "thickness", "process_count",
        "reference_production_qty", "reference_schedule_qty", "source_filename", "source_sha256",
        "source_row", "sheet_name", "formula_choice", "sch", "prd_order", "is_general",
        "sch_overridden", "flags", "import_batch_id", "warnings"}
    if set(value) - allowed:
        raise ApplicationError("INVALID_NORM_REFERENCE", "Unknown consumption norm reference field.", 422)
    result = {}
    for key, item in value.items():
        if item is not None and (not isinstance(item, (str, int, float, bool, list, dict)) or len(str(item)) > 4000):
            raise ApplicationError("INVALID_NORM_REFERENCE", f"{key}: use a text reference value.", 422)
        result[key] = item
    for key in ("process_count", "reference_production_qty", "reference_schedule_qty", "sch", "prd_order"):
        raw = result.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            number = Decimal(str(raw))
            if not number.is_finite() or number < 0:
                raise ValueError
        except (ValueError, ArithmeticError):
            raise ApplicationError("INVALID_NORM_REFERENCE", f"{key}: enter a valid nonnegative number.", 422) from None
        result[key] = str(number)
    raw_thickness = result.get("thickness")
    if raw_thickness is not None and str(raw_thickness).strip() != "":
        raw_t_str = str(raw_thickness).strip()
        try:
            num = Decimal(raw_t_str)
            if num.is_finite() and num >= 0:
                result["thickness"] = str(num)
            else:
                result["thickness"] = raw_t_str
        except (ValueError, ArithmeticError):
            result["thickness"] = raw_t_str
    return result


def _audit_norm(db, norm, actor_id, action, reference_data, old_values=None, reason="Reviewed consumption norm maintenance"):
    db.add(AuditLog(actor_id=actor_id, action=action, entity_type="ConsumptionNorm", entity_id=norm.id,
        old_values=old_values, new_values={"version": norm.version, "parameters": norm.parameters,
            "is_active": norm.is_active, "reference_data": reference_data}, reason=reason))
    db.flush()


def lock_norm_catalog(db):
    """Serialize norm version changes, including empty scopes, across API workers."""
    if db.bind.dialect.name == "postgresql":
        transaction = db.get_transaction()
        if transaction is None or db.info.get("norm_catalog_locked_transaction") is not transaction:
            db.execute(text("SELECT pg_advisory_xact_lock(734020260015)"))
            db.info["norm_catalog_locked_transaction"] = db.get_transaction()


def create_consumption_norm(
    db: Session, data: ConsumptionNormCreate, *, actor_id: Optional[UUID] = None,
    commit: bool = True, reason: str = "Reviewed consumption norm creation"
) -> ConsumptionNormResponse:
    lock_norm_catalog(db)
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
    if data.unit_id != consumable.unit_id:
        raise ApplicationError("NORM_UNIT_MISMATCH", "The norm output unit must match the consumable's reviewed stock unit.", 422)
    if data.effective_to is not None and data.effective_to < data.effective_from:
        raise ApplicationError("INVALID_EFFECTIVE_DATES", "Effective until cannot precede effective from.", 422)
    reference_data = _reference_data(data.reference_data)

    if data.product_id is not None:
        product = db.scalar(select(Product).where(Product.id == data.product_id).with_for_update())
        if not product:
            raise ApplicationError("NOT_FOUND", f"Product '{data.product_id}' not found", 404)
        if not product.is_active:
            raise ApplicationError("INACTIVE_ENTITY", f"Product '{product.code}' is inactive", 400)
        if reference_data and (reference_data.get('used_part_number') or reference_data.get('part_number')):
            from app.services.basic_norms import match_product
            matched, issue = match_product([product], part_number=reference_data.get('used_part_number') or reference_data.get('part_number'))
            if issue:
                raise ApplicationError('NORM_PRODUCT_REFERENCE_CONFLICT', 'The production part reference must match the selected Product Master. Select a different product in a new norm to change its scope.', 422)

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
        if data.rule_type == RuleType.MIN_MAX and all(data.parameters.get(key) is not None for key in ("min_quantity", "max_quantity", "base_rate")) and not any(key in data.parameters for key in ("msl_days", "moq", "current_stock")):
            # Preserve the existing bounded-consumption branch; stock defaults select a different formula.
            parameters_dict = {key: parameters_dict[key] for key in data.parameters if key in parameters_dict}
    except RuleDomainError as e:
        raise ApplicationError(e.code, e.message, status_code=400)
    except ValidationError:
        raise ApplicationError("INVALID_NORM_PARAMETERS", "Enter valid parameters for the selected formula.", 422) from None
    if reference_data and reference_data.get('formula_choice'):
        rate_val = Decimal(str(parameters_dict.get('rate', '0')))
        pc_val = Decimal(str(reference_data.get('process_count') or '0'))
        ref_sch = reference_data.get('sch') if reference_data.get('sch') is not None else reference_data.get('reference_schedule_qty')
        sch_val = Decimal(str(ref_sch)) if ref_sch is not None else pc_val
        valid_rates = {pc_val, sch_val}
        if (reference_data['formula_choice'] != 'PRODUCTION_RATE_FROM_PROCESS_COUNT'
            or data.rule_type != RuleType.PRODUCTION_RATE
            or rate_val not in valid_rates
            or Decimal(str(parameters_dict.get('scrap_factor', '0'))) != 0):
            raise ApplicationError('NORM_APPROVED_FORMULA_CONFLICT', 'For the reviewed production × process-count formula, rate must equal process count or Sch and no extra scrap factor may be added.', 422)

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
        id=uuid4(),
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
    db.flush()
    _audit_norm(db, norm, actor_id, "CREATE_VERSION", reference_data,
        old_values={"superseded_ids": [str(n.id) for n in existing_norms if n.id != norm.id]}, reason=reason)
    if commit:
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
    return _to_norm_response(norm, norm_reference_data(db, [norm.id]).get(norm.id))


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
    references = norm_reference_data(db, [r.id for r in records])
    return [_to_norm_response(r, references.get(r.id)) for r in records]


def update_consumption_norm(
    db: Session, norm_id: UUID, data: ConsumptionNormUpdate, *, actor_id: Optional[UUID] = None,
    commit: bool = True, reason: str = "Reviewed consumption norm update"
) -> ConsumptionNormResponse:
    lock_norm_catalog(db)
    norm = db.scalar(select(ConsumptionNorm).where(ConsumptionNorm.id == norm_id).with_for_update())
    if not norm:
        raise ApplicationError("NOT_FOUND", f"Consumption norm {norm_id} not found", 404)

    if data.expected_version is not None and data.expected_version != norm.version:
        raise ApplicationError("STALE_NORM", "This norm changed. Reload and review the latest version.", 409)
    latest = db.scalar(select(ConsumptionNorm).where(ConsumptionNorm.consumable_id == norm.consumable_id,
        ConsumptionNorm.product_id == norm.product_id, ConsumptionNorm.process_id == norm.process_id,
        ConsumptionNorm.plant_id == norm.plant_id).order_by(ConsumptionNorm.version.desc()).limit(1))
    if latest.id != norm.id:
        raise ApplicationError("NORM_HISTORY_PROTECTED", "Edit the latest norm version; historical versions are protected.", 409)
    changed_fields = data.model_fields_set - {"expected_version"}
    reference = norm_reference_data(db, [norm.id]).get(norm.id)
    if changed_fields - {"is_active"}:
        parameters = dict(norm.parameters) if data.parameters is None else dict(data.parameters)
        if data.reference_data is not None:
            for key in ("source_filename", "source_sha256", "source_row", "sheet_name", "formula_choice"):
                if key in data.reference_data and data.reference_data[key] != (reference or {}).get(key):
                    raise ApplicationError("NORM_PROVENANCE_PROTECTED", "Imported source and formula approval evidence cannot be edited.", 422)
            reference = {**(reference or {}), **data.reference_data}
            reference = _reference_data(reference)
        if reference and reference.get("formula_choice") == "PRODUCTION_RATE_FROM_PROCESS_COUNT":
            try:
                count = Decimal(str(reference.get("process_count") or "0"))
                rate = Decimal(str(parameters.get("rate", "0")))
                if not count.is_finite() or count <= 0 or not rate.is_finite():
                    raise ValueError
            except (ValueError, ArithmeticError):
                raise ApplicationError("INVALID_PROCESS_COUNT", "The approved process count must be positive.", 422) from None
            if data.parameters is not None and rate != count:
                raise ApplicationError("NORM_RATE_CONFLICT", "For this imported formula, rate must equal the reviewed process count.", 422)
            parameters["rate"] = str(count)
        replacement = ConsumptionNormCreate(rule_type=RuleType(norm.rule_type), consumable_id=norm.consumable_id,
            product_id=norm.product_id, process_id=norm.process_id, plant_id=norm.plant_id,
            parameters=parameters, unit_id=norm.unit_id,
            rounding_policy=data.rounding_policy or RoundingPolicy.parse(norm.rounding_policy),
            rounding_precision=data.rounding_precision if data.rounding_precision is not None else norm.rounding_precision,
            effective_from=data.effective_from or norm.effective_from,
            effective_to=data.effective_to if "effective_to" in changed_fields else norm.effective_to,
            reference_data=reference)
        response = create_consumption_norm(db, replacement, actor_id=actor_id, commit=False, reason=reason)
        new_norm = db.get(ConsumptionNorm, response.id)
        if data.is_active is not None:
            new_norm.is_active = data.is_active
        if commit:
            db.commit()
        return get_consumption_norm(db, new_norm.id)
    if data.is_active is not None:
        old = {"is_active": norm.is_active}
        norm.is_active = data.is_active
        _audit_norm(db, norm, actor_id, "SET_ACTIVE", reference, old_values=old, reason=reason)
    if commit:
        db.commit()
    return get_consumption_norm(db, norm.id)


def bulk_update_consumption_norms(db, payload, actor_id):
    identities = [item.norm_id for item in payload.updates]
    if len(set(identities)) != len(identities):
        raise ApplicationError("DUPLICATE_NORM_UPDATE", "Review each norm once per save.", 422)
    try:
        if not payload.reason.strip():
            raise ApplicationError("REASON_REQUIRED", "Enter a reason for the norm changes.", 422)
        lock_norm_catalog(db)
        records = []
        for item in sorted(payload.updates, key=lambda item: str(item.norm_id)):
            values = item.model_dump(exclude={"norm_id"}, exclude_unset=True)
            records.append(update_consumption_norm(db, item.norm_id, ConsumptionNormUpdate(**values),
                actor_id=actor_id, commit=False, reason=payload.reason))
        db.commit()
        return {"updated_count": len(records), "records": records}
    except Exception:
        db.rollback()
        raise


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
    if consumable.unit_id is None:
        raise ApplicationError("STOCK_UNIT_REQUIRED", "Add the consumable stock unit in Product Master before calculating requirements.", 422)
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

