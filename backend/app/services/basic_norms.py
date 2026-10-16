"""Exact product matching and effective norms for direct consumable planning.

No plant-route or process-consumable assignment is inferred here. A norm must
itself reference the product, material and process that authorize its use.
"""
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.rules import ConsumptionNorm


def key(value):
    return str(value or "").strip().casefold()


def match_product(products, *, product_id=None, code=None, part_number=None, item_id=None):
    """Return one canonical product or a diagnostic; never fall back from a bad pair."""
    active = [p for p in products if p.is_active]
    if product_id:
        matches = [p for p in active if str(p.id) == str(product_id)]
    elif part_number and item_id:
        matches = [p for p in active if key(p.part_number) == key(part_number) and key(p.item_id) == key(item_id)]
    elif code:
        matches = [p for p in active if key(p.code) == key(code)]
    elif part_number:
        matches = [p for p in active if key(p.part_number) == key(part_number)]
        if not matches:
            matches = [p for p in active if key(p.code) == key(part_number)]
    elif item_id:
        matches = [p for p in active if key(p.item_id) == key(item_id)]
    else:
        matches = []
    if len(matches) != 1:
        return None, "PRODUCT_AMBIGUOUS" if len(matches) > 1 else "PRODUCT_NOT_FOUND"
    product = matches[0]
    if code and key(product.code) != key(code):
        return None, "PRODUCT_IDENTITY_CONFLICT"
    # An explicit UUID/code must not hide inconsistent source identifiers.
    if part_number and key(product.part_number) != key(part_number) and key(product.code) != key(part_number):
        return None, "PRODUCT_IDENTITY_CONFLICT"
    if item_id and key(product.item_id) != key(item_id):
        return None, "PRODUCT_IDENTITY_CONFLICT"
    return product, None


def load_product_norms(session, product_ids):
    if not product_ids:
        return []
    return list(session.scalars(select(ConsumptionNorm).options(
        joinedload(ConsumptionNorm.consumable), joinedload(ConsumptionNorm.process), joinedload(ConsumptionNorm.unit),
    ).where(ConsumptionNorm.product_id.in_(product_ids), ConsumptionNorm.is_active.is_(True))
        .order_by(ConsumptionNorm.product_id, ConsumptionNorm.process_id, ConsumptionNorm.consumable_id, ConsumptionNorm.version)))


def is_production_rule(norm):
    """Mirror the existing MIN_MAX branch selector without adding stock policy."""
    if norm.rule_type == "PLANT_REQUEST":
        return False
    if norm.rule_type != "MIN_MAX":
        return True
    parameters = norm.parameters or {}
    return (
        all(parameters.get(name) is not None for name in ("min_quantity", "max_quantity", "base_rate"))
        and not any(name in parameters for name in ("msl_days", "moq", "current_stock"))
    )


def applicable_norms(norms, product_id: UUID, as_of: date, plant_id: UUID | None = None, *, ignore_dates: bool = False, allow_duplicates: bool = False, allow_missing: bool = False):
    """Choose one version per process/material, favoring an explicitly supplied plant.

    Plant-independent plans do not borrow another plant's parameters. Conflicting
    active versions are reported instead of resolved by arbitrary database order.
    """
    candidates = defaultdict(list)
    for norm in norms:
        if not norm.is_active or norm.product_id != product_id:
            continue
        if (norm.parameters or {}).get("is_general"):
            continue
        if not ignore_dates and (norm.effective_from > as_of or (norm.effective_to is not None and norm.effective_to < as_of)):
            continue
        if norm.plant_id is not None and norm.plant_id != plant_id:
            continue
        candidates[(norm.process_id, norm.consumable_id)].append(norm)
    selected, errors = [], []
    for identity, choices in candidates.items():
        specificity = max(int(n.plant_id is not None) for n in choices)
        choices = [n for n in choices if int(n.plant_id is not None) == specificity]
        version = max(n.version for n in choices)
        choices = [n for n in choices if n.version == version]
        if len(choices) != 1 and not allow_duplicates:
            errors.append({"code": "AMBIGUOUS_NORM", "process_id": str(identity[0]) if identity[0] else None,
                           "consumable_id": str(identity[1]) if identity[1] else None,
                           "message": "Several active norms have the same scope and version. Review the norm history."})
            continue
        for norm in choices:
            issue = None
            if not norm.process_id or not norm.process or not norm.process.is_active:
                issue = ("PROCESS_REQUIRED", "Choose an active process on the product's consumption norm.")
            elif not norm.consumable or not norm.consumable.is_active:
                issue = ("CONSUMABLE_INACTIVE", "The norm's consumable must be active.")
            elif not norm.unit or not norm.unit.is_active or norm.unit_id != norm.consumable.unit_id:
                issue = ("NORM_UNIT_MISMATCH", "Use the consumable's approved stock unit; no conversion factor is assumed.")
            elif not is_production_rule(norm):
                issue = ("WRONG_CALCULATION_STAGE", "Stock policies and manual requests are not production-derived basic demand.")
            if issue:
                errors.append({"code": issue[0], "norm_id": str(norm.id),
                               "process_id": str(identity[0]) if identity[0] else None,
                               "consumable_id": str(identity[1]) if identity[1] else None,
                               "message": issue[1]})
            else:
                selected.append(norm)
    if not candidates and not allow_missing:
        errors.append({"code": "MISSING_CONSUMPTION_NORM", "message": "No active, effective product consumption norm matches this planning scope and date."})
    return selected, errors
