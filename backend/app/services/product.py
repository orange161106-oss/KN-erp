from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Product
from app.schemas.masters import ProductCreate


def list_products(db: Session) -> Sequence[Product]:
    return db.scalars(select(Product).order_by(Product.code)).all()


def get_product_by_code(db: Session, code: str) -> Product | None:
    return db.scalars(select(Product).where(Product.code == code.strip())).first()


def create_product(db: Session, data: ProductCreate) -> Product:
    code = data.code.strip()
    existing = get_product_by_code(db, code)
    if existing:
        raise ValueError(f"Product with code '{code}' already exists")
    product = Product(
        code=code,
        name=data.name.strip(),
        uom=data.uom.strip() if data.uom else "PCS",
        description=data.description.strip() if data.description else None,
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
