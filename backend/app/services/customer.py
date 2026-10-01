from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Customer
from app.schemas.masters import CustomerCreate


def list_customers(db: Session) -> Sequence[Customer]:
    return db.scalars(select(Customer).order_by(Customer.code)).all()


def get_customer_by_code(db: Session, code: str) -> Customer | None:
    return db.scalars(select(Customer).where(Customer.code == code.strip())).first()


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    code = data.code.strip()
    existing = get_customer_by_code(db, code)
    if existing:
        raise ValueError(f"Customer with code '{code}' already exists")
    customer = Customer(
        code=code,
        name=data.name.strip(),
        is_active=True,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer
