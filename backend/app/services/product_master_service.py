import io
import re
from decimal import Decimal
from typing import Any, Optional, Union
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, Unit
from app.models.mappings import ProductProcessConsumable
from app.models.masters import Product
from app.models.production import Process


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ConsumableSingleCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier_id: Optional[Union[UUID, str]] = None
    supplier_name: Optional[str] = None
    item_id: str
    category: Optional[str] = None
    type_of_material: Optional[str] = None
    description: Optional[str] = None
    output_unit: Optional[str] = "PCS"
    rate: Optional[Decimal] = None


class SalesPartSingleCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    part_no: str
    item_id: str
    part_description: str
    uom: Optional[str] = "PCS"


class AssembleSingleCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    consumable_item: str
    part_no_saleable_item: str
    used_for_name_of_saleable_part: Optional[str] = None
    used_part_no_prd_order: Optional[str] = None
    process_name: Optional[str] = "ASSEMBLY"
    material_thickness_in_mm_gsm: Optional[str] = None
    no_of_process_per_part: Optional[Decimal] = Decimal("1.0000")
    output_unit: Optional[str] = "PCS"
    rate: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# UOM Auto-Provisioning Helper
# ---------------------------------------------------------------------------

def ensure_unit(db: Session, uom_str: Optional[str]) -> Unit:
    """Normalize UOM and auto-provision into units table if missing."""
    raw = (uom_str or "PCS").strip()
    if not raw:
        raw = "PCS"
    clean_code = raw.upper()[:16]

    unit = db.scalars(select(Unit).where(Unit.code == clean_code)).first()
    if unit:
        return unit

    unit = Unit(
        id=uuid4(),
        code=clean_code,
        name=clean_code,
        is_active=True,
    )
    db.add(unit)
    db.flush()
    return unit


def ensure_supplier(
    db: Session,
    supp_ref: Optional[Union[UUID, str]],
    supp_name: Optional[str] = None,
) -> Optional[Supplier]:
    """Auto-provision or resolve Supplier from ID/code and name."""
    raw_ref = str(supp_ref or "").strip()
    if raw_ref.lower() in ("nan", "none", "null", "undefined"):
        raw_ref = ""

    raw_name = str(supp_name or "").strip()
    if raw_name.lower() in ("nan", "none", "null", "undefined"):
        raw_name = ""

    if not raw_ref and not raw_name:
        return None

    # 1. Check if raw_ref is a valid UUID
    parsed_uuid: Optional[UUID] = None
    if raw_ref:
        try:
            parsed_uuid = UUID(raw_ref)
        except ValueError:
            parsed_uuid = None

    if parsed_uuid:
        supplier = db.scalars(select(Supplier).where(Supplier.id == parsed_uuid)).first()
        if supplier:
            return supplier

        clean_code = (raw_name.upper() if raw_name else f"SUP-{parsed_uuid.hex[:8]}".upper())[:64].strip()
        if not clean_code:
            clean_code = f"SUP-{parsed_uuid.hex[:8]}".upper()

        existing_code = db.scalars(select(Supplier).where(Supplier.code == clean_code)).first()
        if existing_code:
            clean_code = f"{clean_code[:50]}-{parsed_uuid.hex[:8]}".upper()[:64]

        supplier = Supplier(
            id=parsed_uuid,
            code=clean_code,
            name=(raw_name or clean_code)[:255],
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        return supplier

    # 2. If raw_ref is a string code (e.g. 'SUP-001', 'VEND-42')
    if raw_ref:
        clean_code = raw_ref.upper()[:64].strip()
        supplier = db.scalars(select(Supplier).where(Supplier.code == clean_code)).first()
        if supplier:
            return supplier

        supplier = Supplier(
            id=uuid4(),
            code=clean_code,
            name=(raw_name or clean_code)[:255],
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        return supplier

    # 3. Only raw_name was provided
    clean_code = re.sub(r"[^A-Z0-9]", "", raw_name.upper())[:64].strip()
    if not clean_code:
        clean_code = f"SUP-{uuid4().hex[:8].upper()}"

    supplier = db.scalars(
        select(Supplier).where(or_(Supplier.name == raw_name, Supplier.code == clean_code))
    ).first()
    if supplier:
        return supplier

    existing = db.scalars(select(Supplier).where(Supplier.code == clean_code)).first()
    if existing:
        clean_code = f"{clean_code[:50]}-{uuid4().hex[:8].upper()}"[:64]

    supplier = Supplier(
        id=uuid4(),
        code=clean_code,
        name=raw_name[:255],
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier


# ---------------------------------------------------------------------------
# Pandas Header Hunter Engine
# ---------------------------------------------------------------------------

def _normalize_col_name(val: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(val or "").lower())


def header_hunter(file_bytes: bytes, target_anchors: list[str]) -> pd.DataFrame:
    """Scan first 30 rows of Excel workbook for required anchor columns.
    
    Drops title rows, whitespace, and guarantees 1:1 vocabulary extraction.
    """
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "Uploaded Excel file is empty.", 422)

    try:
        # Read raw sheets without header assumption
        raw_df = pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=str, engine="openpyxl")
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Failed to parse Excel workbook: {str(e)}", 422) from None

    if raw_df.empty:
        raise ApplicationError("EMPTY_WORKSHEET", "Excel worksheet contains no data.", 422)

    norm_anchors = {_normalize_col_name(a) for a in target_anchors}
    header_idx = None

    # Scan the first 30 rows
    max_scan = min(30, len(raw_df))
    for r in range(max_scan):
        row_cells = [_normalize_col_name(c) for c in raw_df.iloc[r] if pd.notna(c)]
        # Check if any target anchor matches a normalized header in this row
        if any(anchor in row_cells for anchor in norm_anchors):
            header_idx = r
            break

    if header_idx is None:
        raise ApplicationError(
            "ANCHOR_HEADER_NOT_FOUND",
            f"Could not locate an anchor header row matching any of {target_anchors} in the first 30 rows.",
            422,
        )

    # Set column names from the anchor row
    raw_headers = [str(c).strip() if pd.notna(c) else f"col_{i}" for i, c in enumerate(raw_df.iloc[header_idx])]
    data_df = raw_df.iloc[header_idx + 1:].copy()
    data_df.columns = raw_headers

    # Drop completely empty rows
    data_df = data_df.dropna(how="all")

    # Replace all variations of NaN/None with empty string and strip whitespace
    for col in data_df.columns:
        data_df[col] = (
            data_df[col]
            .astype(str)
            .str.strip()
            .replace({
                "nan": "",
                "NaN": "",
                "NAN": "",
                "None": "",
                "none": "",
                "null": "",
                "NULL": "",
                "undefined": "",
            })
        )

    # Drop rows that have all empty values across all columns
    data_df = data_df[~(data_df == "").all(axis=1)].copy()

    return data_df


def _extract_field(row: pd.Series, aliases: list[str]) -> str:
    norm_map = {_normalize_col_name(col): col for col in row.index}
    for alias in aliases:
        norm_a = _normalize_col_name(alias)
        if norm_a in norm_map:
            val = str(row[norm_map[norm_a]]).strip()
            if val and val.lower() not in ("nan", "none", "null", "undefined"):
                return val
    return ""


def _parse_decimal(val: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Parse numeric values cleanly to Decimal or default.

    Guarantees float NaN, np.nan, or invalid strings are never passed to SQLAlchemy.
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if np.isnan(val) or np.isinf(val):
            return default
        try:
            return Decimal(str(val))
        except Exception:
            return default
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "undefined", ""):
        return default
    cleaned = re.sub(r"[^\d.-]", "", s)
    if not cleaned or cleaned in (".", "-", "-."):
        return default
    try:
        return Decimal(cleaned)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Tab 1: List of Consumables Ingestion
# ---------------------------------------------------------------------------

def upsert_single_consumable(
    db: Session,
    data: ConsumableSingleCreate,
    actor_id: UUID,
    username: Optional[str] = None,
) -> Consumable:
    clean_item_id = data.item_id.strip().upper()
    if not clean_item_id:
        raise ApplicationError("INVALID_ITEM_ID", "Item Id is required.", 422)

    unit = ensure_unit(db, data.output_unit)
    supplier = ensure_supplier(db, data.supplier_id, data.supplier_name)
    supplier_id_val = supplier.id if supplier else None
    supplier_name_val = data.supplier_name.strip() if data.supplier_name else (supplier.name if supplier else None)

    stmt = insert(Consumable).values({
        "id": uuid4(),
        "item_id": clean_item_id,
        "supplier_id": supplier_id_val,
        "supplier_name": supplier_name_val,
        "category": data.category.strip() if data.category else None,
        "type_of_material": data.type_of_material.strip() if data.type_of_material else None,
        "name": (data.description or clean_item_id).strip()[:255],
        "description": data.description.strip() if data.description else None,
        "output_unit": unit.code,
        "rate": data.rate,
        "unit_id": unit.id,
        "is_active": True,
    })

    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["item_id"],
        set_={
            "supplier_id": stmt.excluded.supplier_id,
            "supplier_name": stmt.excluded.supplier_name,
            "category": stmt.excluded.category,
            "type_of_material": stmt.excluded.type_of_material,
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "output_unit": stmt.excluded.output_unit,
            "rate": stmt.excluded.rate,
            "unit_id": stmt.excluded.unit_id,
            "is_active": True,
            "updated_at": func.now(),
        },
    ).returning(Consumable)

    record = db.scalars(upsert_stmt).first()
    db.add(AuditLog(
        actor_id=actor_id,
        user_id=actor_id,
        username=username,
        action="CREATE",
        module="Product Master - Consumables",
        entity_type="consumable",
        entity_id=record.id,
        record_id=str(record.id),
        new_values=data.model_dump(mode="json"),
        changes_summary=data.model_dump(mode="json"),
        reason="Single consumable upsert",
    ))
    db.commit()
    return record


def bulk_upsert_consumables(
    db: Session,
    file_bytes: bytes,
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict:
    df = header_hunter(file_bytes, [
        "item_id", "itemid", "item no", "item code", "description",
        "supplier_id", "supplier id", "supplier name", "supplier",
    ])

    # Strip empty rows at bottom where item_id is missing
    def _is_valid_consumable_row(r: pd.Series) -> bool:
        item = _extract_field(r, ["item_id", "itemid", "item no", "item code", "code"])
        return bool(item and item.lower() not in ("nan", "none", "null", "undefined"))

    df = df[df.apply(_is_valid_consumable_row, axis=1)].reset_index(drop=True)
    
    total_rows = 0
    upserted_count = 0
    errors = []

    try:
        for idx, row in df.iterrows():
            item_id = _extract_field(row, ["item_id", "itemid", "item no", "item code", "code"])
            if not item_id:
                continue  # skip blank identifier rows
            
            total_rows += 1
            clean_item_id = item_id.upper()
            supp_id_raw = _extract_field(row, [
                "supplier_id", "supplier id", "supplier code", "suppliercode",
                "vendor_id", "vendor id", "vendor code", "supp id", "supplier",
            ])
            supp_name = _extract_field(row, [
                "supplier_name", "supplier name", "vendor", "vendor name",
            ])
            desc = _extract_field(row, ["description", "part description", "name", "item description"])
            uom = _extract_field(row, ["output_unit", "output/unit", "unit", "uom"]) or "PCS"
            cat = _extract_field(row, ["category", "item category"])
            mat_type = _extract_field(row, ["type_of_material", "type of material", "material type", "type"])
            raw_rate = _extract_field(row, ["rate", "price", "unit rate", "cost"])

            rate_val = _parse_decimal(raw_rate, default=None)

            try:
                unit = ensure_unit(db, uom)
                supplier = ensure_supplier(db, supp_id_raw, supp_name)
                supplier_id_val = supplier.id if supplier else None
                supplier_name_val = supp_name or (supplier.name if supplier else None)

                stmt = insert(Consumable).values({
                    "id": uuid4(),
                    "item_id": clean_item_id,
                    "supplier_id": supplier_id_val,
                    "supplier_name": supplier_name_val,
                    "category": cat or None,
                    "type_of_material": mat_type or None,
                    "name": (desc or clean_item_id)[:255],
                    "description": desc or None,
                    "output_unit": unit.code,
                    "rate": rate_val,
                    "unit_id": unit.id,
                    "is_active": True,
                })
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["item_id"],
                    set_={
                        "supplier_id": stmt.excluded.supplier_id,
                        "supplier_name": stmt.excluded.supplier_name,
                        "category": stmt.excluded.category,
                        "type_of_material": stmt.excluded.type_of_material,
                        "name": stmt.excluded.name,
                        "description": stmt.excluded.description,
                        "output_unit": stmt.excluded.output_unit,
                        "rate": stmt.excluded.rate,
                        "unit_id": stmt.excluded.unit_id,
                        "is_active": True,
                        "updated_at": func.now(),
                    },
                )
                db.execute(upsert_stmt)
                db.commit()
                upserted_count += 1
            except Exception as e:
                db.rollback()
                errors.append(f"Row {idx + 1} ({clean_item_id}): {str(e)}")

        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="BULK_UPLOAD",
            module="Product Master - Consumables",
            entity_type="consumables",
            entity_id=uuid4(),
            new_values={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            changes_summary={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            reason="Bulk Excel Consumables Header Hunter ingestion",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Bulk consumables iteration error: {str(e)}")

    return {
        "total_rows": total_rows,
        "upserted": upserted_count,
        "errors": errors[:20],
    }


# ---------------------------------------------------------------------------
# Tab 2: List of Sales Parts Ingestion
# ---------------------------------------------------------------------------

def upsert_single_sales_part(
    db: Session,
    data: SalesPartSingleCreate,
    actor_id: UUID,
    username: Optional[str] = None,
) -> Product:
    clean_part_no = data.part_no.strip()
    clean_item_id = data.item_id.strip()
    clean_desc = data.part_description.strip()
    if not clean_part_no or not clean_item_id:
        raise ApplicationError("INVALID_IDENTIFIERS", "Part No. and Item Id are required.", 422)

    uom_code = (data.uom or "PCS").strip().upper()
    ensure_unit(db, uom_code)

    composite_code = f"{clean_part_no}_{clean_item_id}"[:128]

    stmt = insert(Product).values({
        "id": uuid4(),
        "code": composite_code,
        "part_number": clean_part_no,
        "item_id": clean_item_id,
        "name": clean_desc[:255],
        "description": clean_desc,
        "uom": uom_code,
        "is_active": True,
    })

    upsert_stmt = stmt.on_conflict_do_update(
        constraint="uq_products_part_number_item_id",
        set_={
            "code": stmt.excluded.code,
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "uom": stmt.excluded.uom,
            "is_active": True,
            "updated_at": func.now(),
        },
    ).returning(Product)

    record = db.scalars(upsert_stmt).first()
    db.add(AuditLog(
        actor_id=actor_id,
        user_id=actor_id,
        username=username,
        action="CREATE",
        module="Product Master - Sales Parts",
        entity_type="product",
        entity_id=record.id,
        record_id=str(record.id),
        new_values=data.model_dump(mode="json"),
        changes_summary=data.model_dump(mode="json"),
        reason="Single sales part upsert",
    ))
    db.commit()
    return record


def bulk_upsert_sales_parts(
    db: Session,
    file_bytes: bytes,
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict:
    df = header_hunter(file_bytes, ["part_no", "partno", "part number", "item_id", "itemid"])

    # Strip empty rows at bottom where both part_no and item_id are missing
    def _is_valid_sales_part_row(row: pd.Series) -> bool:
        p = _extract_field(row, ["part_no", "partno", "part number", "part_number"])
        i = _extract_field(row, ["item_id", "itemid", "item no", "item code"])
        p_valid = bool(p and p.lower() not in ("nan", "none", "null", "undefined"))
        i_valid = bool(i and i.lower() not in ("nan", "none", "null", "undefined"))
        return p_valid or i_valid

    df = df[df.apply(_is_valid_sales_part_row, axis=1)].reset_index(drop=True)

    total_rows = 0
    upserted_count = 0
    errors = []

    try:
        for idx, row in df.iterrows():
            part_no = _extract_field(row, ["part_no", "partno", "part number", "part_number"])
            item_id = _extract_field(row, ["item_id", "itemid", "item no", "item code"])
            if not part_no and not item_id:
                continue
            
            # If one is missing, fall back to the available identifier
            if not part_no:
                part_no = item_id
            if not item_id:
                item_id = part_no

            total_rows += 1
            desc = _extract_field(row, ["part_description", "description", "name", "part name"]) or f"Part {part_no}"
            uom = (_extract_field(row, ["uom", "unit", "output_unit"]) or "PCS").upper()

            composite_code = f"{part_no}_{item_id}"[:128]

            try:
                ensure_unit(db, uom)

                stmt = insert(Product).values({
                    "id": uuid4(),
                    "code": composite_code,
                    "part_number": part_no,
                    "item_id": item_id,
                    "name": desc[:255],
                    "description": desc,
                    "uom": uom,
                    "is_active": True,
                })
                upsert_stmt = stmt.on_conflict_do_update(
                    constraint="uq_products_part_number_item_id",
                    set_={
                        "code": stmt.excluded.code,
                        "name": stmt.excluded.name,
                        "description": stmt.excluded.description,
                        "uom": stmt.excluded.uom,
                        "is_active": True,
                        "updated_at": func.now(),
                    },
                )
                db.execute(upsert_stmt)
                db.commit()
                upserted_count += 1
            except Exception as e:
                db.rollback()
                errors.append(f"Row {idx + 1} ({part_no} / {item_id}): {str(e)}")

        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="BULK_UPLOAD",
            module="Product Master - Sales Parts",
            entity_type="products",
            entity_id=uuid4(),
            new_values={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            changes_summary={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            reason="Bulk Excel Sales Parts Header Hunter ingestion",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Bulk sales parts iteration error: {str(e)}")

    return {
        "total_rows": total_rows,
        "upserted": upserted_count,
        "errors": errors[:20],
    }


# ---------------------------------------------------------------------------
# Tab 3: Consumable for Assemble (BOM) Ingestion
# ---------------------------------------------------------------------------

def _resolve_or_create_product(db: Session, part_no: str, part_name: Optional[str], uom: str) -> Product:
    clean_p = part_no.strip()
    product = db.scalars(
        select(Product).where(or_(Product.part_number == clean_p, Product.code == clean_p))
    ).first()
    if product:
        return product

    # Auto-provision parent product stub so BOM ingestion remains frictionless
    composite_code = f"{clean_p}_{clean_p}"[:128]
    product = Product(
        id=uuid4(),
        code=composite_code,
        part_number=clean_p,
        item_id=clean_p,
        name=(part_name or clean_p)[:255],
        description=part_name or clean_p,
        uom=uom,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _resolve_or_create_consumable(db: Session, consumable_code: str, uom: str) -> Consumable:
    clean_c = consumable_code.strip().upper()
    consumable = db.scalars(
        select(Consumable).where(or_(Consumable.item_id == clean_c, Consumable.name == clean_c))
    ).first()
    if consumable:
        return consumable

    unit = ensure_unit(db, uom)
    consumable = Consumable(
        id=uuid4(),
        item_id=clean_c,
        name=clean_c,
        description=clean_c,
        output_unit=unit.code,
        unit_id=unit.id,
        is_active=True,
    )
    db.add(consumable)
    db.flush()
    return consumable


def _resolve_or_create_process(db: Session, proc_name: Optional[str]) -> Process:
    clean_proc = (proc_name or "ASSEMBLY").strip().upper()
    process = db.scalars(
        select(Process).where(func.upper(Process.name) == clean_proc)
    ).first()
    if process:
        return process

    # Fallback to any existing active process or create stub
    process = db.scalars(select(Process).where(Process.is_active == True)).first()
    if process:
        return process

    process = Process(
        id=uuid4(),
        name=clean_proc,
        is_active=True,
    )
    db.add(process)
    db.flush()
    return process


def upsert_single_assemble(
    db: Session,
    data: AssembleSingleCreate,
    actor_id: UUID,
    username: Optional[str] = None,
) -> ProductProcessConsumable:
    product = _resolve_or_create_product(db, data.part_no_saleable_item, data.used_for_name_of_saleable_part, data.output_unit or "PCS")
    consumable = _resolve_or_create_consumable(db, data.consumable_item, data.output_unit or "PCS")
    process = _resolve_or_create_process(db, data.process_name)

    stmt = insert(ProductProcessConsumable).values({
        "id": uuid4(),
        "product_id": product.id,
        "consumable_id": consumable.id,
        "process_id": process.id,
        "consumable_item": data.consumable_item.strip(),
        "part_no_saleable_item": data.part_no_saleable_item.strip(),
        "used_for_name_of_saleable_part": data.used_for_name_of_saleable_part.strip() if data.used_for_name_of_saleable_part else None,
        "used_part_no_prd_order": data.used_part_no_prd_order.strip() if data.used_part_no_prd_order else None,
        "process_name": process.name,
        "material_thickness_in_mm_gsm": data.material_thickness_in_mm_gsm.strip() if data.material_thickness_in_mm_gsm else None,
        "no_of_process_per_part": data.no_of_process_per_part or Decimal("1.0000"),
        "output_unit": data.output_unit or "PCS",
        "rate": data.rate,
        "is_active": True,
    })

    upsert_stmt = stmt.on_conflict_do_update(
        constraint="uq_product_process_consumables_product_id_process_id_consumable_id",
        set_={
            "consumable_item": stmt.excluded.consumable_item,
            "part_no_saleable_item": stmt.excluded.part_no_saleable_item,
            "used_for_name_of_saleable_part": stmt.excluded.used_for_name_of_saleable_part,
            "used_part_no_prd_order": stmt.excluded.used_part_no_prd_order,
            "process_name": stmt.excluded.process_name,
            "material_thickness_in_mm_gsm": stmt.excluded.material_thickness_in_mm_gsm,
            "no_of_process_per_part": stmt.excluded.no_of_process_per_part,
            "output_unit": stmt.excluded.output_unit,
            "rate": stmt.excluded.rate,
            "is_active": True,
            "updated_at": func.now(),
        },
    ).returning(ProductProcessConsumable)

    record = db.scalars(upsert_stmt).first()
    db.add(AuditLog(
        actor_id=actor_id,
        user_id=actor_id,
        username=username,
        action="CREATE",
        module="Product Master - Assembly BOM",
        entity_type="product_process_consumable",
        entity_id=record.id,
        record_id=str(record.id),
        new_values=data.model_dump(mode="json"),
        changes_summary=data.model_dump(mode="json"),
        reason="Single BOM assemble consumable upsert",
    ))
    db.commit()
    return record


def bulk_upsert_assemble(
    db: Session,
    file_bytes: bytes,
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict:
    df = header_hunter(file_bytes, [
        "consumable_item", "consumable item", "part_no_saleable_item",
        "saleable part", "part no", "process"
    ])

    # Strip empty rows at bottom where consumable_item or part_no is missing
    def _is_valid_assemble_row(row: pd.Series) -> bool:
        c = _extract_field(row, ["consumable_item", "consumable item", "consumable", "item id", "item_id"])
        p = _extract_field(row, ["part_no_saleable_item", "saleable part no", "part no", "finished part no", "part_no"])
        c_valid = bool(c and c.lower() not in ("nan", "none", "null", "undefined"))
        p_valid = bool(p and p.lower() not in ("nan", "none", "null", "undefined"))
        return c_valid and p_valid

    df = df[df.apply(_is_valid_assemble_row, axis=1)].reset_index(drop=True)

    total_rows = 0
    upserted_count = 0
    errors = []

    try:
        for idx, row in df.iterrows():
            consumable_item = _extract_field(row, ["consumable_item", "consumable item", "consumable", "item id", "item_id"])
            part_no = _extract_field(row, ["part_no_saleable_item", "saleable part no", "part no", "finished part no", "part_no"])
            if not consumable_item or not part_no:
                continue

            total_rows += 1
            used_name = _extract_field(row, ["used_for_name_of_saleable_part", "saleable part name", "part name"])
            prd_part = _extract_field(row, ["used_part_no_prd_order", "prd part no"])
            proc_name = _extract_field(row, ["process_name", "process"]) or "ASSEMBLY"
            thickness = _extract_field(row, ["material_thickness_in_mm_gsm", "thickness"])
            raw_qty = _extract_field(row, ["no_of_process_per_part", "qty", "process count", "quantity"])
            uom = _extract_field(row, ["output_unit", "unit", "uom"]) or "PCS"
            raw_rate = _extract_field(row, ["rate", "cost", "unit rate", "price"])

            qty_val = _parse_decimal(raw_qty, default=Decimal("1.0000"))
            if qty_val is None:
                qty_val = Decimal("0.0000")
            rate_val = _parse_decimal(raw_rate, default=None)

            try:
                product = _resolve_or_create_product(db, part_no, used_name, uom)
                consumable = _resolve_or_create_consumable(db, consumable_item, uom)
                process = _resolve_or_create_process(db, proc_name)

                stmt = insert(ProductProcessConsumable).values({
                    "id": uuid4(),
                    "product_id": product.id,
                    "consumable_id": consumable.id,
                    "process_id": process.id,
                    "consumable_item": consumable_item,
                    "part_no_saleable_item": part_no,
                    "used_for_name_of_saleable_part": used_name or None,
                    "used_part_no_prd_order": prd_part or None,
                    "process_name": process.name,
                    "material_thickness_in_mm_gsm": thickness or None,
                    "no_of_process_per_part": qty_val,
                    "output_unit": uom,
                    "rate": rate_val,
                    "is_active": True,
                })
                upsert_stmt = stmt.on_conflict_do_update(
                    constraint="uq_product_process_consumables_product_id_process_id_consumable_id",
                    set_={
                        "consumable_item": stmt.excluded.consumable_item,
                        "part_no_saleable_item": stmt.excluded.part_no_saleable_item,
                        "used_for_name_of_saleable_part": stmt.excluded.used_for_name_of_saleable_part,
                        "used_part_no_prd_order": stmt.excluded.used_part_no_prd_order,
                        "process_name": stmt.excluded.process_name,
                        "material_thickness_in_mm_gsm": stmt.excluded.material_thickness_in_mm_gsm,
                        "no_of_process_per_part": stmt.excluded.no_of_process_per_part,
                        "output_unit": stmt.excluded.output_unit,
                        "rate": stmt.excluded.rate,
                        "is_active": True,
                        "updated_at": func.now(),
                    },
                )
                db.execute(upsert_stmt)
                db.commit()
                upserted_count += 1
            except Exception as e:
                db.rollback()
                errors.append(f"Row {idx + 1} ({part_no} + {consumable_item}): {str(e)}")

        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="BULK_UPLOAD",
            module="Product Master - Assembly BOM",
            entity_type="product_process_consumables",
            entity_id=uuid4(),
            new_values={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            changes_summary={"total_evaluated": total_rows, "upserted": upserted_count, "summary": f"Processed {upserted_count} rows"},
            reason="Bulk Excel BOM Assemble Header Hunter ingestion",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Bulk assemble iteration error: {str(e)}")

    return {
        "total_rows": total_rows,
        "upserted": upserted_count,
        "errors": errors[:20],
    }


# ---------------------------------------------------------------------------
# Listing Queries with Total Counts (Strictly Active Items)
# ---------------------------------------------------------------------------

def list_consumables_table(db: Session, q: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict:
    query = (
        select(Consumable, Supplier.code.label("supplier_code"))
        .outerjoin(Supplier, Consumable.supplier_id == Supplier.id)
        .where(Consumable.is_active == True)
    )
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(
            func.lower(Consumable.item_id).like(term),
            func.lower(Consumable.description).like(term),
            func.lower(Consumable.supplier_name).like(term),
            func.lower(Consumable.category).like(term),
            func.lower(Supplier.code).like(term),
        ))
    
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.execute(query.order_by(Consumable.item_id).offset(offset).limit(limit)).all()

    items = [{
        "id": str(r[0].id),
        "supplier_id": r[1] or (str(r[0].supplier_id) if r[0].supplier_id else None),
        "supplier_name": r[0].supplier_name or "",
        "item_id": r[0].item_id,
        "category": r[0].category or "",
        "type_of_material": r[0].type_of_material or "",
        "description": r[0].description or r[0].name or "",
        "output_unit": r[0].output_unit or "PCS",
        "rate": float(r[0].rate) if r[0].rate is not None else None,
        "is_active": r[0].is_active,
    } for r in records]

    return {"items": items, "total": total}


def list_sales_parts_table(db: Session, q: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict:
    query = select(Product).where(Product.is_active == True)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(
            func.lower(Product.part_number).like(term),
            func.lower(Product.item_id).like(term),
            func.lower(Product.name).like(term),
            func.lower(Product.code).like(term),
        ))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(Product.part_number).offset(offset).limit(limit)).all()

    items = [{
        "id": str(p.id),
        "s_no": idx + offset + 1,
        "part_no": p.part_number or p.code,
        "item_id": p.item_id or p.code,
        "part_description": p.name or p.description or "",
        "uom": p.uom,
        "is_active": p.is_active,
    } for idx, p in enumerate(records)]

    return {"items": items, "total": total}


def list_assemble_table(db: Session, q: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict:
    query = select(ProductProcessConsumable).where(ProductProcessConsumable.is_active == True)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(
            func.lower(ProductProcessConsumable.consumable_item).like(term),
            func.lower(ProductProcessConsumable.part_no_saleable_item).like(term),
            func.lower(ProductProcessConsumable.used_for_name_of_saleable_part).like(term),
            func.lower(ProductProcessConsumable.process_name).like(term),
        ))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(ProductProcessConsumable.part_no_saleable_item).offset(offset).limit(limit)).all()

    items = [{
        "id": str(m.id),
        "consumable_item": m.consumable_item or "",
        "part_no_saleable_item": m.part_no_saleable_item or "",
        "used_for_name_of_saleable_part": m.used_for_name_of_saleable_part or "",
        "used_part_no_prd_order": m.used_part_no_prd_order or "",
        "process_name": m.process_name or "",
        "material_thickness_in_mm_gsm": m.material_thickness_in_mm_gsm or "",
        "no_of_process_per_part": float(m.no_of_process_per_part) if m.no_of_process_per_part is not None else 1.0,
        "output_unit": m.output_unit or "PCS",
        "rate": float(m.rate) if m.rate is not None else None,
        "is_active": m.is_active,
    } for m in records]

    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# Soft Delete & Full Update Implementations
# ---------------------------------------------------------------------------

def _json_safe_dict(d: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            safe[k] = float(v)
        elif isinstance(v, UUID):
            safe[k] = str(v)
        else:
            safe[k] = v
    return safe


def update_product_master_item(
    db: Session,
    category: str,
    item_id: Union[UUID, str],
    data: dict[str, Any],
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict:
    try:
        parsed_id = UUID(str(item_id))
    except ValueError:
        raise ApplicationError("INVALID_ID", "Invalid item ID format.", 422)

    cat = category.lower().replace("-", "_")
    safe_data = _json_safe_dict(data)

    if cat in ("consumables", "consumable"):
        row = db.scalars(select(Consumable).where(Consumable.id == parsed_id)).first()
        if not row:
            raise ApplicationError("NOT_FOUND", f"Consumable with id {item_id} not found.", 404)

        if "item_id" in data and data["item_id"]:
            new_code = str(data["item_id"]).strip().upper()
            if new_code != row.item_id:
                conflict = db.scalars(select(Consumable).where(Consumable.item_id == new_code, Consumable.id != parsed_id)).first()
                if conflict:
                    raise ApplicationError("CONFLICT", f"Consumable Item ID '{new_code}' already exists.", 409)
                row.item_id = new_code

        if "output_unit" in data and data["output_unit"]:
            unit = ensure_unit(db, data["output_unit"])
            row.output_unit = unit.code
            row.unit_id = unit.id

        if "supplier_id" in data or "supplier_name" in data:
            supplier = ensure_supplier(db, data.get("supplier_id"), data.get("supplier_name"))
            row.supplier_id = supplier.id if supplier else None
            row.supplier_name = data.get("supplier_name") or (supplier.name if supplier else None)

        if "category" in data:
            row.category = str(data["category"]).strip() if data["category"] else None
        if "type_of_material" in data:
            row.type_of_material = str(data["type_of_material"]).strip() if data["type_of_material"] else None
        if "description" in data:
            desc = str(data["description"]).strip() if data["description"] else None
            row.description = desc
            if desc:
                row.name = desc[:255]
        if "rate" in data:
            row.rate = _parse_decimal(data["rate"], None)

        row.is_active = True
        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="UPDATE",
            module="Product Master - Consumables",
            entity_type="consumable",
            entity_id=row.id,
            record_id=str(row.id),
            new_values=safe_data,
            changes_summary=safe_data,
            reason="Consumable updated via UI",
        ))
        db.commit()
        db.refresh(row)
        return {
            "id": str(row.id),
            "item_id": row.item_id,
            "message": "Consumable updated successfully.",
        }

    elif cat in ("sales_parts", "sales_part", "products", "product"):
        product = db.scalars(select(Product).where(Product.id == parsed_id)).first()
        if not product:
            raise ApplicationError("NOT_FOUND", f"Sales part with id {item_id} not found.", 404)

        if "part_no" in data and data["part_no"]:
            product.part_number = str(data["part_no"]).strip()
        if "item_id" in data and data["item_id"]:
            product.item_id = str(data["item_id"]).strip()
        if "part_description" in data and data["part_description"]:
            product.name = str(data["part_description"]).strip()[:255]
            product.description = str(data["part_description"]).strip()
        if "uom" in data and data["uom"]:
            product.uom = str(data["uom"]).strip().upper()[:16]

        product.is_active = True
        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="UPDATE",
            module="Product Master - Sales Parts",
            entity_type="product",
            entity_id=product.id,
            record_id=str(product.id),
            new_values=safe_data,
            changes_summary=safe_data,
            reason="Sales part updated via UI",
        ))
        db.commit()
        db.refresh(product)
        return {
            "id": str(product.id),
            "part_no": product.part_number,
            "item_id": product.item_id,
            "message": "Sales part updated successfully.",
        }

    elif cat in ("assemble", "assembly", "product_process_consumables"):
        mapping = db.scalars(select(ProductProcessConsumable).where(ProductProcessConsumable.id == parsed_id)).first()
        if not mapping:
            raise ApplicationError("NOT_FOUND", f"Assembly mapping with id {item_id} not found.", 404)

        if "consumable_item" in data and data["consumable_item"]:
            mapping.consumable_item = str(data["consumable_item"]).strip()
        if "part_no_saleable_item" in data and data["part_no_saleable_item"]:
            mapping.part_no_saleable_item = str(data["part_no_saleable_item"]).strip()
        if "used_for_name_of_saleable_part" in data:
            mapping.used_for_name_of_saleable_part = str(data["used_for_name_of_saleable_part"]).strip() if data["used_for_name_of_saleable_part"] else None
        if "used_part_no_prd_order" in data:
            mapping.used_part_no_prd_order = str(data["used_part_no_prd_order"]).strip() if data["used_part_no_prd_order"] else None
        if "process_name" in data and data["process_name"]:
            mapping.process_name = str(data["process_name"]).strip()
        if "material_thickness_in_mm_gsm" in data:
            mapping.material_thickness_in_mm_gsm = str(data["material_thickness_in_mm_gsm"]).strip() if data["material_thickness_in_mm_gsm"] else None
        if "no_of_process_per_part" in data:
            mapping.no_of_process_per_part = _parse_decimal(data["no_of_process_per_part"], Decimal("1.0000"))
        if "output_unit" in data and data["output_unit"]:
            mapping.output_unit = str(data["output_unit"]).strip().upper()
        if "rate" in data:
            mapping.rate = _parse_decimal(data["rate"], None)

        mapping.is_active = True
        db.add(AuditLog(
            actor_id=actor_id,
            user_id=actor_id,
            username=username,
            action="UPDATE",
            module="Product Master - Assembly BOM",
            entity_type="product_process_consumable",
            entity_id=mapping.id,
            record_id=str(mapping.id),
            new_values=safe_data,
            changes_summary=safe_data,
            reason="Assembly mapping updated via UI",
        ))
        db.commit()
        db.refresh(mapping)
        return {
            "id": str(mapping.id),
            "consumable_item": mapping.consumable_item,
            "part_no_saleable_item": mapping.part_no_saleable_item,
            "message": "Assembly mapping updated successfully.",
        }

    else:
        raise ApplicationError("INVALID_CATEGORY", f"Unknown master category: {category}", 400)


def deactivate_product_master_item(
    db: Session,
    category: str,
    item_id: Union[UUID, str],
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict:
    try:
        parsed_id = UUID(str(item_id))
    except ValueError:
        raise ApplicationError("INVALID_ID", "Invalid item ID format.", 422)

    cat = category.lower().replace("-", "_")
    if cat in ("consumables", "consumable"):
        row = db.scalars(select(Consumable).where(Consumable.id == parsed_id)).first()
        entity_type = "consumable"
        module_name = "Product Master - Consumables"
    elif cat in ("sales_parts", "sales_part", "products", "product"):
        row = db.scalars(select(Product).where(Product.id == parsed_id)).first()
        entity_type = "product"
        module_name = "Product Master - Sales Parts"
    elif cat in ("assemble", "assembly", "product_process_consumables"):
        row = db.scalars(select(ProductProcessConsumable).where(ProductProcessConsumable.id == parsed_id)).first()
        entity_type = "product_process_consumable"
        module_name = "Product Master - Assembly BOM"
    else:
        raise ApplicationError("INVALID_CATEGORY", f"Unknown master category: {category}", 400)

    if not row:
        raise ApplicationError("NOT_FOUND", f"Item with id {item_id} not found in category {category}.", 404)

    row.is_active = False
    db.add(AuditLog(
        actor_id=actor_id,
        user_id=actor_id,
        username=username,
        action="DELETE",
        module=module_name,
        entity_type=entity_type,
        entity_id=row.id,
        record_id=str(row.id),
        new_values={"is_active": False},
        changes_summary={"is_active": False},
        reason="Soft-deleted via UI",
    ))
    db.commit()
    return {
        "id": str(row.id),
        "is_active": False,
        "message": f"{category.capitalize()} item deactivated successfully.",
    }

