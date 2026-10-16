import io
import itertools
import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Union
from uuid import UUID, uuid4

import numpy as np
import openpyxl
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApplicationError
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, Unit
from app.models.mappings import ProductProcessConsumable
from app.models.masters import Product
from app.models.production import Process

logger = logging.getLogger("kn.product_master")


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


class AssembleRowIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row: int
    column: Optional[str] = None
    error_code: str
    message: str
    raw_value: Optional[str] = None
    suggested_action: Optional[str] = None


class AssembleImportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_token: str
    source_filename: str
    detected_header_row: int
    columns_matched: list[str]
    total_rows: int
    rows_to_add: int
    rows_to_update: int
    errors: list[AssembleRowIssue] = []
    warning_count: int = 0
    error_count: int = 0
    can_confirm: bool = True


class AssembleImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_token: str


class AssembleImportJobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: str
    status: str  # "queued", "running", "completed", "failed"
    stage: str
    progress_percent: int
    total_rows: int
    upserted: int
    rows_added: int
    rows_updated: int
    errors: list[AssembleRowIssue] = []
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# In-Memory Preview & Background Job Stores
# ---------------------------------------------------------------------------

_ASSEMBLE_PREVIEW_STORE: dict[str, dict[str, Any]] = {}
_ASSEMBLE_IMPORT_JOBS: dict[str, dict[str, Any]] = {}
ASSEMBLE_PREVIEW_TTL_SECONDS = 1800  # 30 minutes


def _is_sqlite(db: Session) -> bool:
    try:
        return bool(db.bind and "sqlite" in db.bind.dialect.name.lower())
    except Exception:
        return False


def _get_insert_fn(db: Session):
    return sqlite_insert if _is_sqlite(db) else pg_insert


insert = pg_insert


def execute_with_db_retry(operation, max_retries: int = 1):
    """Executes a database operation with automatic retry on transient OperationalError."""
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except (OperationalError, DBAPIError) as e:
            logger.warning(
                "Database connection error (attempt %d/%d): %s",
                attempt + 1,
                max_retries + 1,
                str(e),
            )
            if attempt < max_retries:
                time.sleep(1.0)
                continue
            raise ApplicationError(
                "DATABASE_UNAVAILABLE",
                "Database connection lost or timed out. Please try again.",
                503,
            ) from e


def _cleanup_stale_assemble_previews() -> None:
    now = time.time()
    stale = [
        k
        for k, v in _ASSEMBLE_PREVIEW_STORE.items()
        if now - v.get("created_at", 0) > ASSEMBLE_PREVIEW_TTL_SECONDS
    ]
    for k in stale:
        _ASSEMBLE_PREVIEW_STORE.pop(k, None)


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

    insert_fn = _get_insert_fn(db)
    stmt = insert_fn(Consumable).values({
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

                insert_fn = _get_insert_fn(db)
                stmt = insert_fn(Consumable).values({
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

    insert_fn = _get_insert_fn(db)
    stmt = insert_fn(Product).values({
        "id": uuid4(),
        "code": composite_code,
        "part_number": clean_part_no,
        "item_id": clean_item_id,
        "name": clean_desc[:255],
        "description": clean_desc,
        "uom": uom_code,
        "is_active": True,
    })

    if _is_sqlite(db):
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["part_number", "item_id"],
            set_={
                "code": stmt.excluded.code,
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "uom": stmt.excluded.uom,
                "is_active": True,
                "updated_at": func.now(),
            },
        ).returning(Product)
    else:
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

                insert_fn = _get_insert_fn(db)
                stmt = insert_fn(Product).values({
                    "id": uuid4(),
                    "code": composite_code,
                    "part_number": part_no,
                    "item_id": item_id,
                    "name": desc[:255],
                    "description": desc,
                    "uom": uom,
                    "is_active": True,
                })
                if _is_sqlite(db):
                    upsert_stmt = stmt.on_conflict_do_update(
                        index_elements=["part_number", "item_id"],
                        set_={
                            "code": stmt.excluded.code,
                            "name": stmt.excluded.name,
                            "description": stmt.excluded.description,
                            "uom": stmt.excluded.uom,
                            "is_active": True,
                            "updated_at": func.now(),
                        },
                    )
                else:
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

    insert_fn = _get_insert_fn(db)
    stmt = insert_fn(ProductProcessConsumable).values({
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
        index_elements=["product_id", "process_id", "consumable_id"],
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


# ---------------------------------------------------------------------------
# Fast Streaming Openpyxl Parser & Batch Engine for Consumable for Assemble
# ---------------------------------------------------------------------------

ASSEMBLE_FIELD_MAPPINGS: dict[str, list[str]] = {
    "consumable_item": [
        "consumable_description", "consumable description",
        "consumable_item", "consumable item", "consumable", "item id", "item_id", "description",
    ],
    "part_no_saleable_item": [
        "part_no_of_saleable_item", "part no of saleable item", "part no. of saleable item",
        "part_no_saleable_item", "saleable part no", "part no", "finished part no", "part_no",
    ],
    "used_for_name_of_saleable_part": [
        "used_for_name_of_saleable_part", "used for – name of saleable part", "used for - name of saleable part",
        "used for name of saleable part", "saleable part name", "part name", "used for",
    ],
    "used_part_no_prd_order": [
        "used_part_no_prd_order", "used part no. (prd order)", "used part no (prd order)", "used part no prd order",
        "prd part no",
    ],
    "process_name": [
        "process_name", "process name", "process",
    ],
    "material_thickness_in_mm_gsm": [
        "material_thickness_in_mm_gsm", "material thickness in mm / gsm", "material thickness in mm/gsm",
        "material thickness in mm gsm", "thickness (mm/gsm)", "thickness",
    ],
    "no_of_process_per_part": [
        "no_of_processes_per_part", "no. of processes per part", "no of processes per part",
        "no_of_process_per_part", "no. of process per part", "no of process per part",
        "qty / part", "qty", "process count", "quantity",
    ],
    "output_unit": [
        "output_unit", "output / unit", "output/unit", "output unit", "unit", "uom",
    ],
    "rate": [
        "rate", "cost", "unit rate", "price",
    ],
}


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", "undefined"):
        return ""
    return re.sub(r"[\s\u00a0\ufeff]+", " ", s).strip()


def _clean_header_cell(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(val).lower())


def fast_parse_assemble_excel(
    file_bytes: bytes,
    filename: str = "upload.xlsx",
) -> tuple[int, list[str], list[dict[str, Any]], list[AssembleRowIssue]]:
    """Fast, memory-efficient Excel parser using openpyxl streaming (read_only=True).
    
    Drops decorative banner rows, maps approved KNL columns, validates row-level fields,
    and applies early termination on consecutive empty rows.
    """
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "Uploaded Excel file is empty.", 422)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Failed to parse Excel workbook: {str(e)}", 422) from None

    try:
        ws = wb.active or wb.worksheets[0]
    except Exception:
        wb.close()
        raise ApplicationError("INVALID_EXCEL_FILE", "No active worksheet found in workbook.", 422)

    # Prepared normalized targets for fast header matching
    norm_targets = {
        field: [_clean_header_cell(alias) for alias in aliases]
        for field, aliases in ASSEMBLE_FIELD_MAPPINGS.items()
    }

    detected_header_row: Optional[int] = None
    col_idx_to_field: dict[int, str] = {}
    matched_columns: list[str] = []

    # 1. Scan up to first 30 rows to detect table header
    row_generator = ws.iter_rows(values_only=True)
    scanned_rows: list[tuple[Any, ...]] = []

    for r_idx in range(1, 31):
        try:
            row_vals = next(row_generator)
        except StopIteration:
            break
        scanned_rows.append(row_vals)

        # Attempt to match this row as the header
        temp_col_map: dict[int, str] = {}
        for c_idx, cell_val in enumerate(row_vals):
            clean_val = _clean_header_cell(cell_val)
            if not clean_val:
                continue
            for field, aliases in norm_targets.items():
                if clean_val in aliases and field not in temp_col_map.values():
                    temp_col_map[c_idx] = field
                    break

        # A valid header must at least contain consumable_item and part_no_saleable_item (or >= 2 anchors)
        has_consumable = "consumable_item" in temp_col_map.values()
        has_part_no = "part_no_saleable_item" in temp_col_map.values()
        if (has_consumable and has_part_no) or len(temp_col_map) >= 2:
            detected_header_row = r_idx
            col_idx_to_field = temp_col_map
            matched_columns = list(temp_col_map.values())
            break

    if detected_header_row is None:
        wb.close()
        raise ApplicationError(
            "HEADER_NOT_FOUND",
            "Could not detect valid table headers in the first 30 rows. Expected columns such as 'Consumable Description' and 'Part No. of Saleable Item'.",
            422,
        )

    parsed_rows: list[dict[str, Any]] = []
    issues: list[AssembleRowIssue] = []
    consecutive_empty = 0
    max_row_limit = 5000

    # Process remaining rows from scanned rows (after header row)
    rows_stream = itertools.chain(
        scanned_rows[detected_header_row:],
        row_generator,
    )

    current_row_idx = detected_header_row
    for row_vals in rows_stream:
        current_row_idx += 1
        if not row_vals:
            consecutive_empty += 1
            if consecutive_empty >= 20:
                break
            continue

        # Extract values for mapped columns
        extracted: dict[str, Any] = {}
        row_has_any_val = False
        for c_idx, field in col_idx_to_field.items():
            val = row_vals[c_idx] if c_idx < len(row_vals) else None
            cleaned = _clean_str(val)
            if cleaned:
                row_has_any_val = True
            extracted[field] = cleaned

        if not row_has_any_val:
            consecutive_empty += 1
            if consecutive_empty >= 20:
                break
            continue

        consecutive_empty = 0

        part_no = extracted.get("part_no_saleable_item", "")
        consumable_item = extracted.get("consumable_item", "")

        # Check required primary keys
        if not part_no and not consumable_item:
            continue  # Blank line spacer

        if not part_no:
            issues.append(AssembleRowIssue(
                row=current_row_idx,
                column="part_no_saleable_item",
                error_code="MISSING_PART_NO",
                message=f"Row {current_row_idx}: Part No. of Saleable Item is missing.",
                raw_value="",
                suggested_action="Specify a valid saleable part number.",
            ))
            continue

        if not consumable_item:
            issues.append(AssembleRowIssue(
                row=current_row_idx,
                column="consumable_item",
                error_code="MISSING_CONSUMABLE",
                message=f"Row {current_row_idx}: Consumable Description is missing.",
                raw_value="",
                suggested_action="Specify a valid consumable description.",
            ))
            continue

        # Parse numeric quantity
        raw_qty = extracted.get("no_of_process_per_part")
        qty_val = Decimal("1.0000")
        if raw_qty:
            parsed_q = _parse_decimal(raw_qty, default=None)
            if parsed_q is not None:
                qty_val = parsed_q
            else:
                issues.append(AssembleRowIssue(
                    row=current_row_idx,
                    column="no_of_process_per_part",
                    error_code="INVALID_QTY",
                    message=f"Row {current_row_idx}: Invalid quantity '{raw_qty}'. Defaulted to 1.0000.",
                    raw_value=str(raw_qty),
                    suggested_action="Ensure quantity is a valid positive number.",
                ))

        # Parse numeric rate
        raw_rate = extracted.get("rate")
        rate_val: Optional[Decimal] = None
        if raw_rate:
            parsed_r = _parse_decimal(raw_rate, default=None)
            if parsed_r is not None:
                rate_val = parsed_r
            else:
                issues.append(AssembleRowIssue(
                    row=current_row_idx,
                    column="rate",
                    error_code="INVALID_RATE",
                    message=f"Row {current_row_idx}: Invalid rate '{raw_rate}'. Rate left empty.",
                    raw_value=str(raw_rate),
                    suggested_action="Ensure rate is a valid decimal number.",
                ))

        parsed_rows.append({
            "row_idx": current_row_idx,
            "consumable_item": consumable_item,
            "part_no": part_no,
            "used_name": extracted.get("used_for_name_of_saleable_part") or None,
            "prd_part": extracted.get("used_part_no_prd_order") or None,
            "process_name": (extracted.get("process_name") or "ASSEMBLY").strip().upper(),
            "thickness": extracted.get("material_thickness_in_mm_gsm") or None,
            "qty": qty_val,
            "uom": (extracted.get("output_unit") or "PCS").strip().upper(),
            "rate": rate_val,
        })

        if len(parsed_rows) >= max_row_limit:
            issues.append(AssembleRowIssue(
                row=current_row_idx,
                error_code="MAX_ROWS_REACHED",
                message=f"File exceeds maximum batch limit of {max_row_limit} rows. Remaining rows truncated.",
                suggested_action="Split larger workbooks into smaller batches.",
            ))
            break

    wb.close()
    return detected_header_row, matched_columns, parsed_rows, issues


def preview_assemble_import(
    db: Session,
    file_bytes: bytes,
    filename: str,
    actor_id: UUID,
) -> AssembleImportPreviewResponse:
    """Parses and validates an Excel workbook for Consumable for Assemble without committing."""
    _cleanup_stale_assemble_previews()

    detected_header_row, matched_columns, parsed_rows, parse_issues = fast_parse_assemble_excel(file_bytes, filename)
    if not parsed_rows:
        raise ApplicationError("EMPTY_DATA", "No valid data rows found in uploaded Excel file.", 422)

    # In-memory deduplication & duplicate detection
    seen_keys: set[tuple[str, str, str]] = set()
    duplicate_count = 0
    issues = list(parse_issues)

    for r in parsed_rows:
        key = (r["part_no"].upper(), r["process_name"].upper(), r["consumable_item"].upper())
        if key in seen_keys:
            duplicate_count += 1
            issues.append(AssembleRowIssue(
                row=r["row_idx"],
                column="part_no_saleable_item",
                error_code="DUPLICATE_ROW_IN_FILE",
                message=f"Row {r['row_idx']}: Duplicate mapping for Part '{r['part_no']}' and Consumable '{r['consumable_item']}'. Last row in file will overwrite earlier ones.",
                raw_value=r["part_no"],
                suggested_action="Review duplicate rows in file.",
            ))
        seen_keys.add(key)

    # Batch check additions vs updates against DB
    part_nos = {r["part_no"] for r in parsed_rows}
    cons_codes = {r["consumable_item"].upper() for r in parsed_rows}
    proc_names = {r["process_name"].upper() for r in parsed_rows}

    existing_prods = db.scalars(
        select(Product).where(or_(Product.part_number.in_(list(part_nos)), Product.code.in_(list(part_nos))))
    ).all()
    existing_prod_ids = {p.id for p in existing_prods}

    existing_cons = db.scalars(
        select(Consumable).where(or_(Consumable.item_id.in_(list(cons_codes)), Consumable.name.in_(list(cons_codes))))
    ).all()
    existing_cons_ids = {c.id for c in existing_cons}

    existing_procs = db.scalars(
        select(Process).where(func.upper(Process.name).in_(list(proc_names)))
    ).all()
    existing_proc_ids = {p.id for p in existing_procs}

    existing_mappings_set: set[tuple[UUID, UUID, UUID]] = set()
    if existing_prod_ids and existing_cons_ids and existing_proc_ids:
        mappings = db.scalars(
            select(ProductProcessConsumable).where(
                ProductProcessConsumable.product_id.in_(list(existing_prod_ids)),
                ProductProcessConsumable.consumable_id.in_(list(existing_cons_ids)),
                ProductProcessConsumable.process_id.in_(list(existing_proc_ids)),
            )
        ).all()
        for m in mappings:
            existing_mappings_set.add((m.product_id, m.process_id, m.consumable_id))

    # Map part_no -> id, cons -> id, proc -> id
    prod_id_map: dict[str, UUID] = {}
    for p in existing_prods:
        if p.part_number:
            prod_id_map[p.part_number.upper()] = p.id
        if p.code:
            prod_id_map[p.code.upper()] = p.id

    cons_id_map: dict[str, UUID] = {}
    for c in existing_cons:
        if c.item_id:
            cons_id_map[c.item_id.upper()] = c.id
        if c.name:
            cons_id_map[c.name.upper()] = c.id

    proc_id_map: dict[str, UUID] = {}
    for pr in existing_procs:
        proc_id_map[pr.name.upper()] = pr.id

    rows_to_update = 0
    rows_to_add = 0
    unique_deduped_rows = len(seen_keys)

    for key in seen_keys:
        p_no_key, proc_key, c_key = key
        p_id = prod_id_map.get(p_no_key)
        c_id = cons_id_map.get(c_key)
        pr_id = proc_id_map.get(proc_key)
        if p_id and c_id and pr_id and (p_id, pr_id, c_id) in existing_mappings_set:
            rows_to_update += 1
        else:
            rows_to_add += 1

    file_token = uuid4().hex
    _ASSEMBLE_PREVIEW_STORE[file_token] = {
        "file_token": file_token,
        "filename": filename,
        "parsed_rows": parsed_rows,
        "issues": issues,
        "detected_header_row": detected_header_row,
        "columns_matched": matched_columns,
        "total_rows": len(parsed_rows),
        "rows_to_add": rows_to_add,
        "rows_to_update": rows_to_update,
        "created_at": time.time(),
        "actor_id": actor_id,
    }

    warning_count = sum(1 for iss in issues if iss.error_code in ("DUPLICATE_ROW_IN_FILE", "INVALID_QTY", "INVALID_RATE"))
    error_count = sum(1 for iss in issues if iss.error_code not in ("DUPLICATE_ROW_IN_FILE", "INVALID_QTY", "INVALID_RATE"))

    return AssembleImportPreviewResponse(
        file_token=file_token,
        source_filename=filename,
        detected_header_row=detected_header_row,
        columns_matched=matched_columns,
        total_rows=len(parsed_rows),
        rows_to_add=rows_to_add,
        rows_to_update=rows_to_update,
        errors=issues[:50],
        warning_count=warning_count,
        error_count=error_count,
        can_confirm=len(parsed_rows) > 0,
    )


def execute_assemble_import_batch(
    db: Session,
    parsed_rows: list[dict[str, Any]],
    actor_id: UUID,
    job: Optional[dict[str, Any]] = None,
    username: Optional[str] = None,
) -> dict[str, Any]:
    """Constant O(1) batched upsert engine for Consumable for Assemble.
    
    Resolves/auto-provisions units, processes, consumables, and products in single batch
    queries, then executes set-based upserts in chunks of 500 rows.
    """
    if not parsed_rows:
        return {"total_rows": 0, "upserted": 0, "errors": []}

    # 1. In-memory deduplication: keep last occurrence for identical (part_no, process_name, consumable_item)
    deduped_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in parsed_rows:
        p_no = str(r["part_no"]).strip()
        proc = (str(r.get("process_name") or "ASSEMBLY")).strip().upper()
        c_item = str(r["consumable_item"]).strip()
        key = (p_no.upper(), proc, c_item.upper())
        deduped_map[key] = r

    deduped_rows = list(deduped_map.values())
    total_to_upsert = len(deduped_rows)

    if job:
        job["stage"] = "Resolving master references"
        job["progress_percent"] = 10

    # 2. Collect unique values for batch lookups
    all_uoms = {
        (r.get("uom") or "PCS").strip().upper()
        for r in deduped_rows
        if r.get("uom")
    }
    all_uoms.add("PCS")

    all_procs = {
        (r.get("process_name") or "ASSEMBLY").strip().upper()
        for r in deduped_rows
    }
    all_procs.add("ASSEMBLY")

    all_consumable_codes = {r["consumable_item"].strip().upper() for r in deduped_rows}
    all_part_nos = {r["part_no"].strip() for r in deduped_rows}

    # 3. Batch resolve/provision Units
    existing_units = db.scalars(select(Unit).where(Unit.code.in_(list(all_uoms)))).all()
    unit_map = {u.code.upper(): u for u in existing_units}
    missing_uoms = [u for u in all_uoms if u not in unit_map]
    if missing_uoms:
        new_units = [Unit(id=uuid4(), code=u, name=u, is_active=True) for u in missing_uoms]
        db.add_all(new_units)
        db.flush()
        for u in new_units:
            unit_map[u.code.upper()] = u

    # 4. Batch resolve/provision Processes
    existing_procs = db.scalars(select(Process).where(func.upper(Process.name).in_(list(all_procs)))).all()
    proc_map = {p.name.upper(): p for p in existing_procs}
    fallback_proc = db.scalars(select(Process).where(Process.is_active == True)).first()
    missing_procs = [p for p in all_procs if p not in proc_map]
    if missing_procs:
        new_procs = [Process(id=uuid4(), name=p, is_active=True) for p in missing_procs]
        db.add_all(new_procs)
        db.flush()
        for p in new_procs:
            proc_map[p.name.upper()] = p

    # 5. Batch resolve/provision Consumables
    existing_consumables = db.scalars(
        select(Consumable).where(
            or_(
                Consumable.item_id.in_(list(all_consumable_codes)),
                Consumable.name.in_(list(all_consumable_codes)),
            )
        )
    ).all()
    cons_map: dict[str, Consumable] = {}
    for c in existing_consumables:
        if c.item_id:
            cons_map[c.item_id.upper()] = c
        if c.name:
            cons_map[c.name.upper()] = c

    missing_cons_codes = [c for c in all_consumable_codes if c not in cons_map]
    if missing_cons_codes:
        new_cons_list = []
        for code in missing_cons_codes:
            u_code = "PCS"
            u_obj = unit_map.get(u_code)
            new_c = Consumable(
                id=uuid4(),
                item_id=code,
                name=code[:255],
                description=code,
                output_unit=u_code,
                unit_id=u_obj.id if u_obj else None,
                is_active=True,
            )
            new_cons_list.append(new_c)
        db.add_all(new_cons_list)
        db.flush()
        for c in new_cons_list:
            cons_map[c.item_id.upper()] = c
            cons_map[c.name.upper()] = c

    # 6. Batch resolve/provision Products
    existing_products = db.scalars(
        select(Product).where(
            or_(
                Product.part_number.in_(list(all_part_nos)),
                Product.code.in_(list(all_part_nos)),
            )
        )
    ).all()
    prod_map: dict[str, Product] = {}
    for p in existing_products:
        if p.part_number:
            prod_map[p.part_number.upper()] = p
        if p.code:
            prod_map[p.code.upper()] = p

    part_meta: dict[str, dict[str, Any]] = {}
    for r in deduped_rows:
        p_no = r["part_no"].strip()
        if p_no.upper() not in part_meta:
            part_meta[p_no.upper()] = {
                "name": r.get("used_name") or p_no,
                "uom": (r.get("uom") or "PCS").strip().upper(),
            }

    missing_part_nos = [p for p in all_part_nos if p.upper() not in prod_map]
    if missing_part_nos:
        new_prods = []
        for p_no in missing_part_nos:
            meta = part_meta.get(p_no.upper(), {})
            clean_name = meta.get("name") or p_no
            clean_uom = meta.get("uom") or "PCS"
            new_p = Product(
                id=uuid4(),
                code=f"{p_no}_{p_no}"[:128],
                part_number=p_no,
                item_id=p_no,
                name=clean_name[:255],
                description=clean_name,
                uom=clean_uom,
                is_active=True,
            )
            new_prods.append(new_p)
        db.add_all(new_prods)
        db.flush()
        for p in new_prods:
            prod_map[p.part_number.upper()] = p
            prod_map[p.code.upper()] = p

    # 7. Upsert ProductProcessConsumable in chunks of 500
    if job:
        job["stage"] = f"Saving 0 of {total_to_upsert}"
        job["progress_percent"] = 30

    chunk_size = 500
    upserted_count = 0
    is_sqlite = _is_sqlite(db)

    for i in range(0, total_to_upsert, chunk_size):
        chunk = deduped_rows[i : i + chunk_size]
        values_chunk = []
        for row in chunk:
            p_no_key = row["part_no"].strip().upper()
            c_key = row["consumable_item"].strip().upper()
            proc_key = (row.get("process_name") or "ASSEMBLY").strip().upper()

            prod = prod_map.get(p_no_key)
            cons = cons_map.get(c_key)
            proc = proc_map.get(proc_key) or fallback_proc

            if not prod or not cons or not proc:
                continue

            values_chunk.append({
                "id": uuid4(),
                "product_id": prod.id,
                "consumable_id": cons.id,
                "process_id": proc.id,
                "consumable_item": row["consumable_item"].strip(),
                "part_no_saleable_item": row["part_no"].strip(),
                "used_for_name_of_saleable_part": (row.get("used_name") or "").strip() or None,
                "used_part_no_prd_order": (row.get("prd_part") or "").strip() or None,
                "process_name": proc.name,
                "material_thickness_in_mm_gsm": (row.get("thickness") or "").strip() or None,
                "no_of_process_per_part": row.get("qty") or Decimal("1.0000"),
                "output_unit": (row.get("uom") or "PCS").strip().upper(),
                "rate": row.get("rate"),
                "is_active": True,
            })

        if values_chunk:
            insert_fn = _get_insert_fn(db)
            stmt = insert_fn(ProductProcessConsumable).values(values_chunk)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["product_id", "process_id", "consumable_id"],
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
            upserted_count += len(values_chunk)

        if job:
            pct = 30 + int((min(i + chunk_size, total_to_upsert) / total_to_upsert) * 60)
            job["stage"] = f"Saving {min(i + chunk_size, total_to_upsert)} of {total_to_upsert}"
            job["progress_percent"] = pct
            job["upserted"] = upserted_count

    # 8. Audit log and commit
    db.add(AuditLog(
        actor_id=actor_id,
        user_id=actor_id,
        username=username,
        action="BULK_IMPORT",
        entity_type="product_process_consumables",
        entity_id=uuid4(),
        new_values={"total_evaluated": len(parsed_rows), "upserted": upserted_count},
        reason="Bulk Excel BOM Assemble Header Hunter fast batch ingestion",
    ))
    db.commit()

    if job:
        job["stage"] = "Completed successfully"
        job["progress_percent"] = 100
        job["status"] = "completed"
        job["upserted"] = upserted_count
        job["completed_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "total_rows": len(parsed_rows),
        "upserted": upserted_count,
        "errors": [],
    }


def run_assemble_import_job(
    job_id: str,
    file_token: str,
    actor_id: UUID,
    session_factory: sessionmaker[Session],
) -> None:
    """Background task worker for processing assemble imports exceeding 200 rows."""
    job = _ASSEMBLE_IMPORT_JOBS.get(job_id)
    if not job:
        logger.error("Assemble import job %s not found in registry.", job_id)
        return

    preview_entry = _ASSEMBLE_PREVIEW_STORE.get(file_token)
    if not preview_entry:
        job["status"] = "failed"
        job["error_message"] = "Preview token expired or invalid."
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        return

    job["status"] = "running"
    job["stage"] = "Starting import..."

    try:
        with session_scope(session_factory) as db:
            execute_with_db_retry(
                lambda: execute_assemble_import_batch(db, preview_entry["parsed_rows"], actor_id, job=job)
            )
        # Cleanup preview store entry on successful import
        _ASSEMBLE_PREVIEW_STORE.pop(file_token, None)
    except Exception as e:
        logger.exception("Failed background assemble import job %s: %s", job_id, str(e))
        job["status"] = "failed"
        job["stage"] = "Import failed"
        job["error_message"] = str(e)
        job["completed_at"] = datetime.now(timezone.utc).isoformat()


def confirm_assemble_import(
    db: Session,
    file_token: str,
    actor_id: UUID,
    session_factory: Optional[sessionmaker[Session]] = None,
    background_tasks: Any = None,
) -> AssembleImportJobResponse:
    """Confirms previewed assemble import. Runs synchronously for <= 200 rows or enqueues background job."""
    preview_entry = _ASSEMBLE_PREVIEW_STORE.get(file_token)
    if not preview_entry:
        raise ApplicationError(
            "EXPIRED_TOKEN",
            "The preview session has expired or is invalid. Please re-upload your Excel file.",
            404,
        )

    parsed_rows = preview_entry["parsed_rows"]
    total_rows = len(parsed_rows)
    job_id = uuid4().hex
    now_str = datetime.now(timezone.utc).isoformat()

    # If small file (<= 200 rows), execute inline synchronously
    if total_rows <= 200 or not session_factory or not background_tasks:
        job_data = {
            "job_id": job_id,
            "status": "running",
            "stage": "Processing records",
            "progress_percent": 0,
            "total_rows": total_rows,
            "upserted": 0,
            "rows_added": preview_entry["rows_to_add"],
            "rows_updated": preview_entry["rows_to_update"],
            "errors": preview_entry["issues"][:50],
            "error_message": None,
            "created_at": now_str,
            "completed_at": None,
        }
        res = execute_with_db_retry(
            lambda: execute_assemble_import_batch(db, parsed_rows, actor_id, job=job_data)
        )
        _ASSEMBLE_PREVIEW_STORE.pop(file_token, None)
        _ASSEMBLE_IMPORT_JOBS[job_id] = job_data
        return AssembleImportJobResponse(**job_data)

    # For large file (> 200 rows), enqueue background job and return 202 Accepted status
    job_data = {
        "job_id": job_id,
        "status": "queued",
        "stage": "Queued in background",
        "progress_percent": 0,
        "total_rows": total_rows,
        "upserted": 0,
        "rows_added": preview_entry["rows_to_add"],
        "rows_updated": preview_entry["rows_to_update"],
        "errors": preview_entry["issues"][:50],
        "error_message": None,
        "created_at": now_str,
        "completed_at": None,
    }
    _ASSEMBLE_IMPORT_JOBS[job_id] = job_data
    background_tasks.add_task(run_assemble_import_job, job_id, file_token, actor_id, session_factory)
    return AssembleImportJobResponse(**job_data)


def get_assemble_job_status(job_id: str) -> AssembleImportJobResponse:
    """Retrieves live background job status and progress for polling."""
    job = _ASSEMBLE_IMPORT_JOBS.get(job_id)
    if not job:
        raise ApplicationError("NOT_FOUND", f"Import job '{job_id}' not found.", 404)
    return AssembleImportJobResponse(**job)


def export_assemble_errors_excel(issues: list[AssembleRowIssue]) -> bytes:
    """Generates a downloadable Excel (.xlsx) workbook of all validation issues and warnings."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Validation Issues"

    headers = ["Row", "Column", "Error Code", "Message", "Raw Value", "Suggested Action"]
    ws.append(headers)

    header_font = openpyxl.styles.Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = openpyxl.styles.PatternFill(start_color="1F4E5B", end_color="1F4E5B", fill_type="solid")
    center_align = openpyxl.styles.Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = openpyxl.styles.Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin_border = openpyxl.styles.Border(
        left=openpyxl.styles.Side(style="thin", color="CCCCCC"),
        right=openpyxl.styles.Side(style="thin", color="CCCCCC"),
        top=openpyxl.styles.Side(style="thin", color="CCCCCC"),
        bottom=openpyxl.styles.Side(style="thin", color="CCCCCC"),
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    data_font = openpyxl.styles.Font(name="Calibri", size=10)
    for r_idx, issue in enumerate(issues, start=2):
        row_vals = [
            issue.row,
            issue.column or "",
            issue.error_code,
            issue.message,
            issue.raw_value or "",
            issue.suggested_action or "",
        ]
        ws.append(row_vals)
        for c_idx in range(1, len(headers) + 1):
            c = ws.cell(row=r_idx, column=c_idx)
            c.font = data_font
            c.border = thin_border
            if c_idx == 1:
                c.alignment = center_align
            else:
                c.alignment = left_align

    col_widths = {1: 10, 2: 24, 3: 20, 4: 45, 5: 20, 6: 40}
    for col_idx, width in col_widths.items():
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 24
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def bulk_upsert_assemble(
    db: Session,
    file_bytes: bytes,
    actor_id: UUID,
    username: Optional[str] = None,
) -> dict[str, Any]:
    """Legacy backward-compatible bulk upsert endpoint using new fast streaming & batch engine."""
    _header_row, _matched_cols, parsed_rows, parse_issues = fast_parse_assemble_excel(file_bytes)
    res = execute_with_db_retry(lambda: execute_assemble_import_batch(db, parsed_rows, actor_id, username=username))
    all_errors = [f"Row {issue.row}: {issue.message}" for issue in parse_issues]
    res["errors"] = (all_errors + res.get("errors", []))[:20]
    return res


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
        "output_unit": r[0].output_unit or "",
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
        "output_unit": m.output_unit or "",
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
    # Reuse the catalog's optional-unit and Decimal validation for partial table
    # edits, instead of applying the add-item form's fallback values.
    from app.services import master_catalog as catalog
    from app.services.master_uploads import number
    from types import SimpleNamespace
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

        if "output_unit" in data:
            values = {"output_unit": row.output_unit}
            catalog.apply_edits("consumables", values, {"output_unit": str(data["output_unit"]) if data["output_unit"] is not None else None})
            catalog.update_stock_unit(db, "consumables", row, values["output_unit"], SimpleNamespace(id=actor_id))

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
            row.rate = number(data["rate"], "rate")

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
            quantity = number(data["no_of_process_per_part"], "no_of_process_per_part")
            if quantity is None:
                raise ApplicationError("INVALID_MASTER_VALUE", "Process Count is required.", 422)
            mapping.no_of_process_per_part = quantity
        if "output_unit" in data:
            values = {"output_unit": mapping.output_unit}
            catalog.apply_edits("assemble", values, {"output_unit": str(data["output_unit"]) if data["output_unit"] is not None else None})
            catalog.update_stock_unit(db, "assemble", mapping, values["output_unit"], SimpleNamespace(id=actor_id))
            mapping.output_unit = values["output_unit"]
        if "rate" in data:
            mapping.rate = number(data["rate"], "rate")

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

