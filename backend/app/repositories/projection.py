from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import StockSnapshot
from app.models.inventory_masters import Consumable, SupplierConsumable, Unit
from app.models.plant_workflow import RequirementAdjustment
from app.models.requirements import CalculatedRequirement
from app.models.prd import PlanningVersion
from app.models.projection import ProjectionInputSet


def material(session: Session, material_id):
    return session.get(Consumable, material_id)


def version(session: Session, version_id):
    return session.get(PlanningVersion, version_id)


def latest_stock(session: Session, material_id):
    return session.scalar(select(StockSnapshot).where(StockSnapshot.consumable_id == material_id)
                          .order_by(StockSnapshot.as_of.desc(), StockSnapshot.id).limit(1))


def source_set(session: Session, source_set_id):
    return session.scalar(select(ProjectionInputSet).where(ProjectionInputSet.source_set_id == source_set_id))


def supplier_mapping_exists(session: Session, material_id, supplier_id):
    return session.scalar(select(SupplierConsumable.id).where(SupplierConsumable.consumable_id == material_id,
                                                            SupplierConsumable.supplier_id == supplier_id).limit(1)) is not None


def requirement_evidence(session: Session, material_id, version_id, unit_id):
    calculations = session.scalars(select(CalculatedRequirement).where(
        CalculatedRequirement.planning_version_id == version_id,
        CalculatedRequirement.consumable_id == material_id).order_by(CalculatedRequirement.id)).all()
    adjustments = session.scalars(select(RequirementAdjustment).where(
        RequirementAdjustment.planning_version_id == version_id,
        RequirementAdjustment.consumable_id == material_id,
        RequirementAdjustment.status == 'APPROVED').order_by(RequirementAdjustment.id)).all()
    return calculations, adjustments, session.get(Unit, unit_id)
