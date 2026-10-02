from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApplicationError
from app.models.inventory_masters import Consumable, Unit
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.masters import Product
from app.models.production import Plant, Process, Route, RouteStep
from app.schemas.mappings import (
    BulkMappingResponse,
    BulkProductPlantCreate,
    BulkProductProcessConsumableCreate,
    MappingValidationIssue,
    MappingValidationReport,
    ProductPlantCreate,
    ProductPlantResponse,
    ProductPlantUpdate,
    ProductProcessConsumableCreate,
    ProductProcessConsumableResponse,
    ProductProcessConsumableUpdate,
    ProductResolutionResponse,
    ResolvedConsumable,
    ResolvedPlantMapping,
    ResolvedProcessStep,
)


def _to_product_plant_response(mapping: ProductPlant) -> ProductPlantResponse:
    return ProductPlantResponse(
        id=mapping.id,
        product_id=mapping.product_id,
        plant_id=mapping.plant_id,
        route_id=mapping.route_id,
        is_primary=mapping.is_primary,
        is_active=mapping.is_active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        product_code=mapping.product.code if mapping.product else None,
        product_name=mapping.product.name if mapping.product else None,
        plant_name=mapping.plant.name if mapping.plant else None,
        route_name=mapping.route.name if mapping.route else None,
    )


def _to_ppc_response(
    mapping: ProductProcessConsumable, unit_code: str | None = None
) -> ProductProcessConsumableResponse:
    return ProductProcessConsumableResponse(
        id=mapping.id,
        product_id=mapping.product_id,
        process_id=mapping.process_id,
        consumable_id=mapping.consumable_id,
        is_active=mapping.is_active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        product_code=mapping.product.code if mapping.product else None,
        product_name=mapping.product.name if mapping.product else None,
        process_name=mapping.process.name if mapping.process else None,
        consumable_code=mapping.consumable.code if mapping.consumable else None,
        consumable_name=mapping.consumable.name if mapping.consumable else None,
        unit=unit_code,
    )


# ==========================================
# Product-to-Plant Mapping Services
# ==========================================

def get_product_plant_mapping(db: Session, mapping_id: UUID) -> ProductPlantResponse:
    stmt = (
        select(ProductPlant)
        .options(
            joinedload(ProductPlant.product),
            joinedload(ProductPlant.plant),
            joinedload(ProductPlant.route),
        )
        .where(ProductPlant.id == mapping_id)
    )
    mapping = db.scalars(stmt).first()
    if not mapping:
        raise ApplicationError("NOT_FOUND", f"ProductPlant mapping {mapping_id} not found", 404)
    return _to_product_plant_response(mapping)


def list_product_plant_mappings(
    db: Session,
    product_id: UUID | None = None,
    plant_id: UUID | None = None,
    is_active: bool | None = None,
) -> list[ProductPlantResponse]:
    stmt = (
        select(ProductPlant)
        .options(
            joinedload(ProductPlant.product),
            joinedload(ProductPlant.plant),
            joinedload(ProductPlant.route),
        )
        .order_by(ProductPlant.created_at.desc())
    )
    if product_id is not None:
        stmt = stmt.where(ProductPlant.product_id == product_id)
    if plant_id is not None:
        stmt = stmt.where(ProductPlant.plant_id == plant_id)
    if is_active is not None:
        stmt = stmt.where(ProductPlant.is_active == is_active)

    records = db.scalars(stmt).all()
    return [_to_product_plant_response(r) for r in records]


def create_product_plant_mapping(db: Session, data: ProductPlantCreate) -> ProductPlantResponse:
    product = db.get(Product, data.product_id)
    if not product:
        raise ApplicationError("NOT_FOUND", f"Product with ID '{data.product_id}' not found", 404)
    if not product.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Product '{product.code}' is inactive", 400)

    plant = db.get(Plant, data.plant_id)
    if not plant:
        raise ApplicationError("NOT_FOUND", f"Plant with ID '{data.plant_id}' not found", 404)
    if not plant.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Plant '{plant.name}' is inactive", 400)

    route = db.get(Route, data.route_id)
    if not route:
        raise ApplicationError("NOT_FOUND", f"Route with ID '{data.route_id}' not found", 404)
    if not route.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Route '{route.name}' is inactive", 400)

    existing = db.scalars(
        select(ProductPlant).where(
            ProductPlant.product_id == data.product_id,
            ProductPlant.plant_id == data.plant_id,
        )
    ).first()
    if existing:
        raise ApplicationError(
            "DUPLICATE_MAPPING",
            f"Product '{product.code}' is already mapped to plant '{plant.name}'",
            409,
        )

    if data.is_primary:
        # Demote other mappings for this product to non-primary
        db.execute(
            update(ProductPlant)
            .where(ProductPlant.product_id == data.product_id)
            .values(is_primary=False)
        )

    mapping = ProductPlant(
        product_id=data.product_id,
        plant_id=data.plant_id,
        route_id=data.route_id,
        is_primary=data.is_primary,
        is_active=True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return get_product_plant_mapping(db, mapping.id)


def update_product_plant_mapping(
    db: Session, mapping_id: UUID, data: ProductPlantUpdate
) -> ProductPlantResponse:
    mapping = db.get(ProductPlant, mapping_id)
    if not mapping:
        raise ApplicationError("NOT_FOUND", f"ProductPlant mapping {mapping_id} not found", 404)

    if data.route_id is not None and data.route_id != mapping.route_id:
        route = db.get(Route, data.route_id)
        if not route:
            raise ApplicationError("NOT_FOUND", f"Route with ID '{data.route_id}' not found", 404)
        if not route.is_active:
            raise ApplicationError("INACTIVE_ENTITY", f"Route '{route.name}' is inactive", 400)
        mapping.route_id = data.route_id

    if data.is_primary is True:
        db.execute(
            update(ProductPlant)
            .where(ProductPlant.product_id == mapping.product_id)
            .values(is_primary=False)
        )
        mapping.is_primary = True
    elif data.is_primary is False:
        mapping.is_primary = False

    if data.is_active is True and not mapping.is_active:
        product = db.get(Product, mapping.product_id)
        plant = db.get(Plant, mapping.plant_id)
        route = db.get(Route, mapping.route_id)
        if not (product and product.is_active):
            raise ApplicationError("INACTIVE_ENTITY", f"Cannot activate: product is inactive", 400)
        if not (plant and plant.is_active):
            raise ApplicationError("INACTIVE_ENTITY", f"Cannot activate: plant is inactive", 400)
        if not (route and route.is_active):
            raise ApplicationError("INACTIVE_ENTITY", f"Cannot activate: route is inactive", 400)
        mapping.is_active = True
    elif data.is_active is False:
        mapping.is_active = False

    db.commit()
    db.refresh(mapping)
    return get_product_plant_mapping(db, mapping.id)


def bulk_create_product_plants(
    db: Session, data: BulkProductPlantCreate
) -> BulkMappingResponse:
    created = 0
    errors: list[str] = []
    for item in data.items:
        try:
            create_product_plant_mapping(db, item)
            created += 1
        except Exception as e:
            errors.append(str(e))
    return BulkMappingResponse(created_count=created, errors=errors)


# ==========================================
# Product-Process to Consumable Mapping Services
# ==========================================

def get_product_process_consumable_mapping(
    db: Session, mapping_id: UUID
) -> ProductProcessConsumableResponse:
    stmt = (
        select(ProductProcessConsumable)
        .options(
            joinedload(ProductProcessConsumable.product),
            joinedload(ProductProcessConsumable.process),
            joinedload(ProductProcessConsumable.consumable),
        )
        .where(ProductProcessConsumable.id == mapping_id)
    )
    mapping = db.scalars(stmt).first()
    if not mapping:
        raise ApplicationError("NOT_FOUND", f"ProductProcessConsumable mapping {mapping_id} not found", 404)

    unit = db.get(Unit, mapping.consumable.unit_id) if mapping.consumable else None
    return _to_ppc_response(mapping, unit.code if unit else None)


def list_product_process_consumable_mappings(
    db: Session,
    product_id: UUID | None = None,
    process_id: UUID | None = None,
    consumable_id: UUID | None = None,
    is_active: bool | None = None,
) -> list[ProductProcessConsumableResponse]:
    stmt = (
        select(ProductProcessConsumable)
        .options(
            joinedload(ProductProcessConsumable.product),
            joinedload(ProductProcessConsumable.process),
            joinedload(ProductProcessConsumable.consumable),
        )
        .order_by(ProductProcessConsumable.created_at.desc())
    )
    if product_id is not None:
        stmt = stmt.where(ProductProcessConsumable.product_id == product_id)
    if process_id is not None:
        stmt = stmt.where(ProductProcessConsumable.process_id == process_id)
    if consumable_id is not None:
        stmt = stmt.where(ProductProcessConsumable.consumable_id == consumable_id)
    if is_active is not None:
        stmt = stmt.where(ProductProcessConsumable.is_active == is_active)

    records = db.scalars(stmt).all()
    # Cache units for performance
    unit_ids = {r.consumable.unit_id for r in records if r.consumable and r.consumable.unit_id}
    units_map = {}
    if unit_ids:
        unit_records = db.scalars(select(Unit).where(Unit.id.in_(unit_ids))).all()
        units_map = {u.id: u.code for u in unit_records}

    responses = []
    for r in records:
        u_code = units_map.get(r.consumable.unit_id) if r.consumable else None
        responses.append(_to_ppc_response(r, u_code))
    return responses


def create_product_process_consumable_mapping(
    db: Session, data: ProductProcessConsumableCreate
) -> ProductProcessConsumableResponse:
    product = db.get(Product, data.product_id)
    if not product:
        raise ApplicationError("NOT_FOUND", f"Product with ID '{data.product_id}' not found", 404)
    if not product.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Product '{product.code}' is inactive", 400)

    process = db.get(Process, data.process_id)
    if not process:
        raise ApplicationError("NOT_FOUND", f"Process with ID '{data.process_id}' not found", 404)
    if not process.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Process '{process.name}' is inactive", 400)

    consumable = db.get(Consumable, data.consumable_id)
    if not consumable:
        raise ApplicationError("NOT_FOUND", f"Consumable with ID '{data.consumable_id}' not found", 404)
    if not consumable.is_active:
        raise ApplicationError("INACTIVE_ENTITY", f"Consumable '{consumable.code}' is inactive", 400)

    existing = db.scalars(
        select(ProductProcessConsumable).where(
            ProductProcessConsumable.product_id == data.product_id,
            ProductProcessConsumable.process_id == data.process_id,
            ProductProcessConsumable.consumable_id == data.consumable_id,
        )
    ).first()
    if existing:
        raise ApplicationError(
            "DUPLICATE_MAPPING",
            f"Mapping already exists for product '{product.code}', process '{process.name}', consumable '{consumable.code}'",
            409,
        )

    mapping = ProductProcessConsumable(
        product_id=data.product_id,
        process_id=data.process_id,
        consumable_id=data.consumable_id,
        is_active=True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return get_product_process_consumable_mapping(db, mapping.id)


def update_product_process_consumable_mapping(
    db: Session, mapping_id: UUID, data: ProductProcessConsumableUpdate
) -> ProductProcessConsumableResponse:
    mapping = db.get(ProductProcessConsumable, mapping_id)
    if not mapping:
        raise ApplicationError("NOT_FOUND", f"ProductProcessConsumable mapping {mapping_id} not found", 404)

    if data.is_active is True and not mapping.is_active:
        product = db.get(Product, mapping.product_id)
        process = db.get(Process, mapping.process_id)
        consumable = db.get(Consumable, mapping.consumable_id)
        if not (product and product.is_active):
            raise ApplicationError("INACTIVE_ENTITY", "Cannot activate: product is inactive", 400)
        if not (process and process.is_active):
            raise ApplicationError("INACTIVE_ENTITY", "Cannot activate: process is inactive", 400)
        if not (consumable and consumable.is_active):
            raise ApplicationError("INACTIVE_ENTITY", "Cannot activate: consumable is inactive", 400)
        mapping.is_active = True
    elif data.is_active is False:
        mapping.is_active = False

    db.commit()
    db.refresh(mapping)
    return get_product_process_consumable_mapping(db, mapping.id)


def bulk_create_product_process_consumables(
    db: Session, data: BulkProductProcessConsumableCreate
) -> BulkMappingResponse:
    created = 0
    errors: list[str] = []
    for item in data.items:
        try:
            create_product_process_consumable_mapping(db, item)
            created += 1
        except Exception as e:
            errors.append(str(e))
    return BulkMappingResponse(created_count=created, errors=errors)


# ==========================================
# Phase 2 Gate Resolution Service:
# Product -> Plant -> Route -> Process -> Consumable
# ==========================================

def resolve_product_mapping(
    db: Session, product_id: UUID, plant_id: UUID | None = None
) -> ProductResolutionResponse:
    product = db.get(Product, product_id)
    if not product:
        raise ApplicationError("NOT_FOUND", f"Product with ID '{product_id}' not found", 404)

    plant_mappings_stmt = (
        select(ProductPlant)
        .options(
            joinedload(ProductPlant.plant),
            joinedload(ProductPlant.route),
        )
        .where(
            ProductPlant.product_id == product_id,
            ProductPlant.is_active == True,
        )
        .order_by(ProductPlant.is_primary.desc())
    )
    if plant_id is not None:
        plant_mappings_stmt = plant_mappings_stmt.where(ProductPlant.plant_id == plant_id)

    plant_mappings = db.scalars(plant_mappings_stmt).all()

    resolved_plants: list[ResolvedPlantMapping] = []

    for pm in plant_mappings:
        route = pm.route
        steps_stmt = (
            select(RouteStep)
            .options(joinedload(RouteStep.process))
            .where(RouteStep.route_id == route.id)
            .order_by(RouteStep.sequence_order.asc())
        )
        steps = db.scalars(steps_stmt).all()

        resolved_steps: list[ResolvedProcessStep] = []
        for step in steps:
            process = step.process

            ppc_stmt = (
                select(ProductProcessConsumable)
                .options(joinedload(ProductProcessConsumable.consumable))
                .where(
                    ProductProcessConsumable.product_id == product_id,
                    ProductProcessConsumable.process_id == process.id,
                    ProductProcessConsumable.is_active == True,
                )
            )
            ppc_records = db.scalars(ppc_stmt).all()

            unit_ids = {c.consumable.unit_id for c in ppc_records if c.consumable and c.consumable.unit_id}
            units_map = {}
            if unit_ids:
                unit_records = db.scalars(select(Unit).where(Unit.id.in_(unit_ids))).all()
                units_map = {u.id: u.code for u in unit_records}

            resolved_consumables: list[ResolvedConsumable] = []
            for item in ppc_records:
                c = item.consumable
                if c:
                    unit_code = units_map.get(c.unit_id, "PCS")
                    resolved_consumables.append(
                        ResolvedConsumable(
                            id=c.id,
                            code=c.code,
                            name=c.name,
                            unit=unit_code,
                            is_active=c.is_active,
                        )
                    )

            resolved_steps.append(
                ResolvedProcessStep(
                    sequence_order=step.sequence_order,
                    process_id=process.id,
                    process_name=process.name,
                    process_description=process.description,
                    consumables=resolved_consumables,
                )
            )

        resolved_plants.append(
            ResolvedPlantMapping(
                plant_id=pm.plant.id,
                plant_name=pm.plant.name,
                location=pm.plant.location,
                is_primary=pm.is_primary,
                route_id=route.id,
                route_name=route.name,
                steps=resolved_steps,
            )
        )

    return ProductResolutionResponse(
        product_id=product.id,
        product_code=product.code,
        product_name=product.name,
        uom=product.uom,
        plant_mappings=resolved_plants,
    )


# ==========================================
# Mapping Validation & Integrity Engine
# ==========================================

def validate_mappings(
    db: Session, product_id: UUID | None = None
) -> MappingValidationReport:
    """Validates structural integrity across the entire mapping chain.
    Detects:
    - Unmapped products (active products without active plant/route assignments)
    - Inactive entities participating in active mappings
    - Route process steps without assigned consumables for the product
    """
    products_stmt = select(Product).where(Product.is_active == True).order_by(Product.code)
    if product_id is not None:
        products_stmt = products_stmt.where(Product.id == product_id)

    products = db.scalars(products_stmt).all()
    issues: list[MappingValidationIssue] = []
    unmapped_count = 0

    for product in products:
        plant_mappings = db.scalars(
            select(ProductPlant)
            .options(
                joinedload(ProductPlant.plant),
                joinedload(ProductPlant.route),
            )
            .where(
                ProductPlant.product_id == product.id,
                ProductPlant.is_active == True,
            )
        ).all()

        if not plant_mappings:
            unmapped_count += 1
            issues.append(
                MappingValidationIssue(
                    issue_type="UNMAPPED_PRODUCT",
                    severity="ERROR",
                    product_id=product.id,
                    product_code=product.code,
                    message=f"Product '{product.code}' ({product.name}) has no active plant/route assignments.",
                )
            )
            continue

        for pm in plant_mappings:
            if not pm.plant.is_active:
                issues.append(
                    MappingValidationIssue(
                        issue_type="INACTIVE_ENTITY",
                        severity="ERROR",
                        product_id=product.id,
                        product_code=product.code,
                        plant_id=pm.plant.id,
                        message=f"Plant '{pm.plant.name}' in active mapping for '{product.code}' is inactive.",
                    )
                )

            if not pm.route.is_active:
                issues.append(
                    MappingValidationIssue(
                        issue_type="INACTIVE_ENTITY",
                        severity="ERROR",
                        product_id=product.id,
                        product_code=product.code,
                        message=f"Route '{pm.route.name}' in active mapping for '{product.code}' is inactive.",
                    )
                )

            # Check process steps
            steps = db.scalars(
                select(RouteStep)
                .options(joinedload(RouteStep.process))
                .where(RouteStep.route_id == pm.route.id)
                .order_by(RouteStep.sequence_order.asc())
            ).all()

            for step in steps:
                process = step.process
                if not process.is_active:
                    issues.append(
                        MappingValidationIssue(
                            issue_type="INACTIVE_ENTITY",
                            severity="ERROR",
                            product_id=product.id,
                            product_code=product.code,
                            process_id=process.id,
                            message=f"Process '{process.name}' in route '{pm.route.name}' is inactive.",
                        )
                    )

                ppc_records = db.scalars(
                    select(ProductProcessConsumable)
                    .options(joinedload(ProductProcessConsumable.consumable))
                    .where(
                        ProductProcessConsumable.product_id == product.id,
                        ProductProcessConsumable.process_id == process.id,
                        ProductProcessConsumable.is_active == True,
                    )
                ).all()

                if not ppc_records:
                    issues.append(
                        MappingValidationIssue(
                            issue_type="PROCESS_WITHOUT_CONSUMABLES",
                            severity="WARNING",
                            product_id=product.id,
                            product_code=product.code,
                            plant_id=pm.plant.id,
                            process_id=process.id,
                            message=(
                                f"Product '{product.code}' at plant '{pm.plant.name}' has no consumables "
                                f"assigned to process step '{process.name}' (step #{step.sequence_order})."
                            ),
                        )
                    )
                else:
                    for ppc in ppc_records:
                        if ppc.consumable and not ppc.consumable.is_active:
                            issues.append(
                                MappingValidationIssue(
                                    issue_type="INACTIVE_ENTITY",
                                    severity="ERROR",
                                    product_id=product.id,
                                    product_code=product.code,
                                    process_id=process.id,
                                    consumable_id=ppc.consumable.id,
                                    message=(
                                        f"Consumable '{ppc.consumable.code}' assigned to '{product.code}' "
                                        f"in process '{process.name}' is inactive."
                                    ),
                                )
                            )

    has_errors = any(i.severity == "ERROR" for i in issues)
    return MappingValidationReport(
        is_valid=not has_errors,
        total_products_checked=len(products),
        unmapped_products_count=unmapped_count,
        issues=issues,
    )
