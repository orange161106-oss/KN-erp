from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.masters import Customer, CustomerAlias
from app.schemas.masters import CustomerAliasCreate, CustomerCreate
from app.services.sales_schedule_parser import normalize_alias, seed_default_customers_and_aliases


def list_customers(db: Session) -> Sequence[Customer]:
    customers = db.scalars(
        select(Customer)
        .options(joinedload(Customer.aliases))
        .order_by(Customer.code)
    ).unique().all()

    if not customers:
        seed_default_customers_and_aliases(db)
        db.commit()
        customers = db.scalars(
            select(Customer)
            .options(joinedload(Customer.aliases))
            .order_by(Customer.code)
        ).unique().all()

    return customers


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


def create_customer_alias(db: Session, data: CustomerAliasCreate) -> CustomerAlias:
    customer = db.get(Customer, data.customer_id)
    if not customer:
        raise ValueError(f"Customer '{data.customer_id}' not found.")
    norm = normalize_alias(data.alias_text)
    if not norm:
        raise ValueError("Alias text cannot be empty.")

    existing = db.scalar(select(CustomerAlias).where(CustomerAlias.normalized_alias == norm))
    if existing:
        existing.customer_id = data.customer_id
        existing.alias_text = data.alias_text.strip()
        existing.group_label = data.group_label
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    alias = CustomerAlias(
        customer_id=data.customer_id,
        alias_text=data.alias_text.strip(),
        normalized_alias=norm,
        group_label=data.group_label,
        is_active=True,
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias


def list_customer_aliases(db: Session) -> Sequence[CustomerAlias]:
    return db.scalars(select(CustomerAlias).where(CustomerAlias.is_active.is_(True)).order_by(CustomerAlias.alias_text)).all()
