import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.domain.inventory_engine.ledger import signed_change, stock_quantity
from app.models.audit import AuditLog
from app.models.inventory import StockImportBatch, StockSnapshot, StockTransaction
from app.models.inventory_masters import Unit
from app.repositories import inventory as repository
from app.schemas.inventory import Balance, ImportResult, SourceImport, TransactionResponse


def fingerprint(value: BaseModel) -> str:
    payload = value.model_dump(mode="json")
    if isinstance(value, SourceImport):
        payload["movements"].sort(key=lambda item: item["source_event_id"])
        payload["snapshots"].sort(key=lambda item: item["source_snapshot_id"])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def result(batch: StockImportBatch, replayed: bool) -> ImportResult:
    return ImportResult(id=batch.id, export_id=batch.export_id, generated_at=batch.generated_at,
                        imported_at=batch.imported_at, imported_by=batch.imported_by,
                        movement_count=batch.movement_count, snapshot_count=batch.snapshot_count, replayed=replayed)


def validate_replay(batch: StockImportBatch, digest: str):
    if batch.payload_hash != digest:
        raise ApplicationError("SOURCE_CONFLICT", "The source identifier already has different content. Resolve the source export; stored history cannot be overwritten.", 409)


def stage_source(session: Session, data: SourceImport, actor_id: UUID, *, enabled: bool) -> ImportResult:
    """Validate and flush source data; the caller must own commit/rollback."""
    if not enabled:
        raise ApplicationError("INVENTORY_IMPORT_DISABLED", "Source import is not enabled. The source export mapping must be verified first.", 409)
    if data.generated_at > datetime.now(timezone.utc):
        raise ApplicationError("INVALID_SOURCE_TIME", "An already-posted source export cannot have a future generation time.", 422)
    digest = fingerprint(data)
    ids = {row.consumable_id for row in [*data.movements, *data.snapshots]}
    materials = repository.lock_consumables(session, ids)
    if len(materials) != len(ids):
        raise ApplicationError("INVALID_REFERENCE", "A source consumable is not present in the master data.", 409)
    previous = repository.find_batch(session, data.export_id)
    if previous is not None:
        validate_replay(previous, digest)
        return result(previous, True)
    new_movements, new_snapshots = [], []
    for rows, model, key_field, target in (
        (data.movements, StockTransaction, "source_event_id", new_movements),
        (data.snapshots, StockSnapshot, "source_snapshot_id", new_snapshots),
    ):
        for row in rows:
            material = materials[row.consumable_id]
            if row.unit_id != material.unit_id:
                raise ApplicationError("UNIT_MISMATCH", "A source stock unit does not match its consumable's stock unit.", 409)
            if model is StockTransaction and session.get(Unit, row.source_unit_id) is None:
                raise ApplicationError("INVALID_REFERENCE", "A source unit is not present in the unit master.", 409)
            row_hash = fingerprint(row)
            existing = repository.find_source_record(session, model, getattr(row, key_field))
            if existing is not None:
                validate_replay(existing, row_hash)
                continue
            values = row.model_dump(exclude={"condition", "source_status"})
            if model is StockTransaction:
                values["quantity"] = stock_quantity(row.source_quantity, row.conversion_factor)
                values["signed_quantity"] = signed_change(row.movement, values["quantity"])
                values["movement"] = row.movement.value
            target.append(model(**values, payload_hash=row_hash))
    batch = StockImportBatch(export_id=data.export_id, payload_hash=digest, generated_at=data.generated_at,
                             imported_by=actor_id, import_reason=data.import_reason,
                             movement_count=len(new_movements), snapshot_count=len(new_snapshots))
    session.add(batch)
    session.flush()
    for record in [*new_movements, *new_snapshots]:
        record.batch_id = batch.id
        session.add(record)
    session.flush()
    session.add(AuditLog(actor_id=actor_id, action="IMPORT_SOURCE_STOCK", entity_type="stock_import_batches",
                         entity_id=batch.id, old_values=None, new_values={
                             "export_id": batch.export_id, "payload_hash": digest,
                             "generated_at": data.generated_at.isoformat(),
                             "source": "EXISTING_ERP", "movement_count": batch.movement_count,
                             "snapshot_count": batch.snapshot_count,
                             "movement_ids": [str(row.id) for row in new_movements],
                             "snapshot_ids": [str(row.id) for row in new_snapshots],
                         }, reason=data.import_reason))
    session.flush()
    return result(batch, False)


def import_source(session: Session, data: SourceImport, actor_id: UUID, *, enabled: bool) -> ImportResult:
    try:
        imported = stage_source(session, data, actor_id, enabled=enabled)
        session.commit()
        return imported
    except IntegrityError:
        session.rollback()
        raise ApplicationError("SOURCE_CONFLICT", "Source identifiers or snapshot timestamps conflict with stored history.", 409) from None
    except SQLAlchemyError:
        session.rollback()
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None
    except Exception:
        session.rollback()
        raise


def list_balances(session: Session, **filters):
    try:
        rows, total = repository.balances(session, **filters)
        items = [Balance(consumable_id=material.id, code=material.code, name=material.name,
                         is_active=material.is_active, unit_id=material.unit_id, unit_code=unit_code,
                         usable_quantity=None if snapshot is None else snapshot.usable_quantity,
                         as_of=None if snapshot is None else snapshot.as_of,
                         imported_at=None if batch is None else batch.imported_at,
                         source_export_id=None if batch is None else batch.export_id,
                         availability="NOT_IMPORTED" if snapshot is None else "REPORTED")
                 for material, unit_code, snapshot, batch in rows]
        return {"items": items, "total": total, "limit": filters["limit"], "offset": filters["offset"]}
    except SQLAlchemyError:
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None


def get_balance(session: Session, consumable_id: UUID):
    page = list_balances(session, consumable_id=consumable_id, limit=1, offset=0)
    if not page["items"]:
        raise ApplicationError("MASTER_NOT_FOUND", "Consumable does not exist.", 404)
    return page["items"][0]


def list_transactions(session: Session, **filters):
    if filters.get("since") and filters.get("until") and filters["since"] > filters["until"]:
        raise ApplicationError("INVALID_DATE_RANGE", "History start must not be after its end.", 422)
    try:
        rows, total = repository.transactions(session, **filters)
        items = [TransactionResponse(
            id=entry.id, source_event_id=entry.source_event_id, consumable_id=entry.consumable_id,
            code=code, name=name, unit_id=entry.unit_id, unit_code=unit_code,
            source_unit_id=entry.source_unit_id, source_unit_code=source_unit_code,
            source_quantity=entry.source_quantity, conversion_factor=entry.conversion_factor,
            conversion_reference=entry.conversion_reference, movement=entry.movement,
            quantity=entry.quantity, signed_quantity=entry.signed_quantity,
            event_at=entry.event_at, source_actor=entry.source_actor, imported_at=batch.imported_at,
            imported_by=batch.imported_by, source_export_id=batch.export_id)
                 for entry, code, name, unit_code, source_unit_code, batch in rows]
        return {"items": items, "total": total, "limit": filters["limit"], "offset": filters["offset"]}
    except SQLAlchemyError:
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None
