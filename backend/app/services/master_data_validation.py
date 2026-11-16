"""Master data validation reports for purchase planning auditing."""
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable
from app.models.stock_statements import StockParameter, StockParameterBatch
from app.services.requirement_requests import get_active_requirement_requests_map
from app.services.stock_management_service import normalize_item_id_key


def generate_master_data_validation_report(
    session: Session,
    month: int,
    year: int,
) -> dict[str, Any]:
    """Generate comprehensive audit reports for missing master data:
    - Missing MOQ
    - Missing purchase rates
    - Missing supplier mappings
    - Unit conflicts across sources
    """
    # 1. Active consumables
    all_consumables = session.scalars(
        select(Consumable).where(Consumable.is_active == True).order_by(Consumable.item_id)
    ).all()

    # 2. Latest active StockParameterBatch for month/year
    param_batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == month,
            StockParameterBatch.year == year,
            StockParameterBatch.status == "active",
        ).order_by(StockParameterBatch.created_at.desc())
    )

    moq_map: dict[str, Decimal] = {}
    if param_batch:
        params = session.scalars(
            select(StockParameter).where(StockParameter.batch_id == param_batch.id)
        ).all()
        for p in params:
            key = normalize_item_id_key(p.item_id)
            if p.min_order_qty is not None and p.min_order_qty > Decimal("0"):
                moq_map[key] = p.min_order_qty

    # 3. Active supplier mappings
    supplier_mappings = set(
        session.scalars(
            select(SupplierConsumable.consumable_id).where(SupplierConsumable.is_active == True)
        ).all()
    )

    # 4. Department requests map for unit conflicts
    req_map = get_active_requirement_requests_map(session, month, year)

    missing_moq: list[dict[str, Any]] = []
    missing_rates: list[dict[str, Any]] = []
    missing_suppliers: list[dict[str, Any]] = []
    unit_conflicts: list[dict[str, Any]] = []

    for c in all_consumables:
        code_key = normalize_item_id_key(c.item_id)

        # Check MOQ
        if code_key not in moq_map:
            missing_moq.append({
                "item_id": c.item_id,
                "name": c.name,
                "category": c.category,
                "type_of_material": c.type_of_material,
            })

        # Check Rate
        if c.rate is None or c.rate <= Decimal("0"):
            missing_rates.append({
                "item_id": c.item_id,
                "name": c.name,
                "category": c.category,
                "type_of_material": c.type_of_material,
            })

        # Check Supplier mapping
        has_supplier = (c.supplier_id is not None) or (c.id in supplier_mappings)
        if not has_supplier:
            missing_suppliers.append({
                "item_id": c.item_id,
                "name": c.name,
                "category": c.category,
                "type_of_material": c.type_of_material,
            })

        # Check Unit conflict from department requests
        r_info = req_map.get(c.id, {})
        if r_info.get("has_unit_conflict"):
            unit_conflicts.append({
                "item_id": c.item_id,
                "name": c.name,
                "purchasing_unit": c.purchasing_unit,
                "submitted_units": r_info.get("units", {}),
                "details": r_info.get("unit_conflict_details"),
            })

    return {
        "planning_period": f"{year:04d}-{month:02d}",
        "total_consumables_evaluated": len(all_consumables),
        "missing_moq_count": len(missing_moq),
        "missing_rates_count": len(missing_rates),
        "missing_suppliers_count": len(missing_suppliers),
        "unit_conflicts_count": len(unit_conflicts),
        "missing_moq": missing_moq,
        "missing_rates": missing_rates,
        "missing_suppliers": missing_suppliers,
        "unit_conflicts": unit_conflicts,
    }
