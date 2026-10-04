from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.repositories import inventory_masters as repository
from app.repositories.inventory import has_stock_records
from app.schemas import inventory_masters as schemas


@dataclass(frozen=True)
class Resource:
    path: str
    model: type
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    response_schema: type[BaseModel]

    @property
    def permission_name(self):
        return self.model.__tablename__


RESOURCES = (
    Resource("units", Unit, schemas.UnitCreate, schemas.UnitUpdate, schemas.UnitResponse),
    Resource("consumables", Consumable, schemas.ConsumableCreate, schemas.ConsumableUpdate, schemas.ConsumableResponse),
    Resource("suppliers", Supplier, schemas.SupplierCreate, schemas.SupplierUpdate, schemas.SupplierResponse),
    Resource("supplier-consumables", SupplierConsumable, schemas.SupplierConsumableCreate, schemas.SupplierConsumableUpdate, schemas.SupplierConsumableResponse),
)


def get_record(session: Session, resource: Resource, entity_id: UUID, *, lock=False):
    try:
        record = repository.find(session, resource.model, entity_id, lock=lock)
    except SQLAlchemyError:
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None
    if record is None:
        raise ApplicationError("MASTER_NOT_FOUND", "Master record does not exist.", 404)
    return record


def list_records(session: Session, resource: Resource, **filters):
    try:
        items, total = repository.list_records(session, resource.model, **filters)
    except SQLAlchemyError:
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None
    return {"items": items, "total": total, "limit": filters["limit"], "offset": filters["offset"]}


@contextmanager
def mutation(session: Session):
    # Authentication may already have opened this request's transaction.
    try:
        yield
        session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApplicationError("MASTER_CONFLICT", "Code, mapping, or reference conflicts with an existing record.", 409) from None
    except SQLAlchemyError:
        session.rollback()
        raise ApplicationError("DATABASE_UNAVAILABLE", "Database is unavailable.", 503) from None
    except Exception:
        session.rollback()
        raise


def active_reference(session: Session, model, entity_id: UUID):
    record = repository.find(session, model, entity_id, lock=True)
    if record is None:
        raise ApplicationError("INVALID_REFERENCE", "Referenced master record does not exist.", 409)
    if not record.is_active:
        raise ApplicationError("INACTIVE_REFERENCE", "Referenced master record is inactive.", 409)
    return record


def validate_references(session: Session, record):
    if isinstance(record, Consumable):
        active_reference(session, Unit, record.unit_id)
    elif isinstance(record, SupplierConsumable):
        active_reference(session, Supplier, record.supplier_id)
        consumable = active_reference(session, Consumable, record.consumable_id)
        active_reference(session, Unit, consumable.unit_id)


def snapshot(resource: Resource, record) -> dict:
    return resource.response_schema.model_validate(record).model_dump(mode="json")


def audit(session: Session, resource: Resource, record, actor_id: UUID, action: str,
          reason: str, old_values: dict | None):
    session.add(AuditLog(actor_id=actor_id, action=action, entity_type=resource.model.__tablename__,
                         entity_id=record.id, old_values=old_values,
                         new_values=snapshot(resource, record), reason=reason))


def create_record(session: Session, resource: Resource, data: BaseModel, actor_id: UUID):
    with mutation(session):
        record = resource.model(**data.model_dump(exclude={"change_reason"}))
        validate_references(session, record)
        session.add(record)
        session.flush()
        audit(session, resource, record, actor_id, "CREATE", data.change_reason, None)
    return record


def update_record(session: Session, resource: Resource, entity_id: UUID, data: BaseModel, actor_id: UUID):
    with mutation(session):
        record = get_record(session, resource, entity_id, lock=True)
        before = snapshot(resource, record)
        changes = data.model_dump(exclude_unset=True, exclude={"change_reason"})
        if isinstance(record, Consumable) and "unit_id" in changes and changes["unit_id"] != record.unit_id:
            if has_stock_records(session, record.id):
                raise ApplicationError("UNIT_CHANGE_CONFLICT", "Unit cannot change after stock history or a reported balance exists.", 409)
            if repository.has_supplier_mapping(session, record.id):
                raise ApplicationError("UNIT_CHANGE_CONFLICT", "Unit cannot change after a supplier mapping exists.", 409)
            active_reference(session, Unit, changes["unit_id"])
        for field, value in changes.items():
            setattr(record, field, value)
        if isinstance(record, SupplierConsumable):
            validate_references(session, record)
        session.flush()
        if snapshot(resource, record) != before:
            audit(session, resource, record, actor_id, "UPDATE", data.change_reason, before)
    return record


def change_status(session: Session, resource: Resource, entity_id: UUID, data: schemas.StatusChange, actor_id: UUID):
    with mutation(session):
        record = get_record(session, resource, entity_id, lock=True)
        if record.is_active == data.is_active:
            return record
        before = snapshot(resource, record)
        if data.is_active:
            validate_references(session, record)
        elif isinstance(record, Unit) and repository.has_active_consumables(session, record.id):
            raise ApplicationError("REFERENCE_IN_USE", "Deactivate the unit's active consumables first.", 409)
        record.is_active = data.is_active
        session.flush()
        audit(session, resource, record, actor_id, "ACTIVATE" if data.is_active else "DEACTIVATE", data.change_reason, before)
    return record
