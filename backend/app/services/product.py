from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy import insert, inspect, select
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm import Session

from app.models.masters import Product
from app.models.audit import AuditLog
from app.schemas.masters import ProductCreate
from app.schemas.masters import ProductBulkCreate
from app.core.errors import ApplicationError
from sqlalchemy.exc import IntegrityError


def require_product_schema(db: Session) -> None:
    """Give operators an actionable error before querying an unmigrated table."""
    try:
        columns = {column['name'] for column in inspect(db.connection()).get_columns('products')}
    except NoSuchTableError:
        columns = set()
    if not {'id', 'code', 'item_id', 'part_number'}.issubset(columns):
        raise ApplicationError(
            'PRODUCT_DATABASE_SETUP_REQUIRED',
            'Product database setup is incomplete. Ask the administrator to apply the pending database updates, then retry saving.',
            503,
        )


def list_products(db: Session) -> Sequence[Product]:
    require_product_schema(db)
    return db.scalars(select(Product).order_by(Product.code)).all()


def get_product_by_code(db: Session, code: str) -> Product | None:
    return db.scalars(select(Product).where(Product.code == code.strip())).first()


def create_product(db: Session, data: ProductCreate, actor_id: UUID | None = None) -> Product:
    require_product_schema(db)
    code = data.code.strip()
    existing = get_product_by_code(db, code)
    if existing:
        raise ValueError(f"Product with code '{code}' already exists")
    product = Product(
        id=uuid4(),
        code=code,
        name=data.name.strip(),
        uom=data.uom.strip() if data.uom else "PCS",
        description=data.description.strip() if data.description else None,
        is_active=True,
        item_id=data.item_id,
        part_number=data.part_number,
    )
    db.add(product)
    if actor_id is not None:
        db.add(AuditLog(actor_id=actor_id, action="CREATE", entity_type="product", entity_id=product.id,
            old_values=None, new_values=data.model_dump(mode="json"), reason="Reviewed product master created"))
    db.commit()
    db.refresh(product)
    return product


def create_products(db: Session, data: ProductBulkCreate, actor_id: UUID) -> list[Product]:
    """A reviewed batch is all-or-nothing; existing records cannot be overwritten."""
    seen = set()
    try:
        reviewed = []
        for record in data.products:
            code = record.code.strip()
            if not code or not record.name.strip() or not record.uom.strip() or code in seen:
                raise ApplicationError("INVALID_PRODUCT_BATCH", "Every product needs a unique code, name and reviewed unit.", 422)
            seen.add(code)
            values = record.model_dump()
            values.update(code=code, name=record.name.strip(), uom=record.uom.strip())
            reviewed.append(values)

        require_product_schema(db)
        # A remote database must not incur one round trip for every spreadsheet row.
        existing_by_code = {product.code: product for product in db.scalars(
            select(Product).where(Product.code.in_(seen))
        ).all()}
        new_products = []
        new_audits = []
        for values in reviewed:
            code = values['code']
            existing = existing_by_code.get(code)
            if existing:
                if any(getattr(existing, field) != value for field, value in values.items()):
                    raise ApplicationError("PRODUCT_SOURCE_CONFLICT", f"Product {code} differs from its existing master. Review the discrepancy.", 409)
                continue
            product_id = uuid4()
            new_products.append({'id': product_id, **values, 'is_active': True})
            new_audits.append({'id': uuid4(), 'actor_id': actor_id, 'action': 'CREATE',
                'entity_type': 'product', 'entity_id': product_id, 'old_values': None,
                'new_values': {**values, 'source_reference': data.source_reference},
                'reason': 'Reviewed source product master batch'})
        if new_products:
            created = db.scalars(insert(Product).returning(Product), new_products).all()
            existing_by_code.update({product.code: product for product in created})
            # Insert audit rows after products, before the same transaction commits.
            db.execute(insert(AuditLog), new_audits)
        db.commit()
        return [existing_by_code[values['code']] for values in reviewed]
    except IntegrityError:
        db.rollback()
        raise ApplicationError("PRODUCT_SOURCE_CONFLICT", "A product code was created concurrently. Review and retry.", 409) from None
    except Exception:
        db.rollback()
        raise
