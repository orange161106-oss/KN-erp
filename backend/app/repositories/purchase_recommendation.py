from sqlalchemy import select

from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit


def context(session, material_id, supplier_id):
    material = session.get(Consumable, material_id)
    return (material, session.get(Unit, material.unit_id) if material else None,
            session.get(Supplier, supplier_id),
            session.scalar(select(SupplierConsumable).where(
                SupplierConsumable.consumable_id == material_id,
                SupplierConsumable.supplier_id == supplier_id)))
