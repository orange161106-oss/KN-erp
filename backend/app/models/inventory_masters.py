from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.db.base import Base


class MasterRecord:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Unit(MasterRecord, Base):
    __tablename__ = "units"
    __table_args__ = (CheckConstraint("code = upper(btrim(code)) AND length(code) > 0", name="normalized_code"),)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Consumable(MasterRecord, Base):
    __tablename__ = "consumables"
    __table_args__ = (
        CheckConstraint("item_id = upper(btrim(item_id)) AND length(item_id) > 0", name="normalized_item_id"),
        UniqueConstraint("item_id", name="uq_consumables_item_id"),
    )
    item_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    supplier_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    type_of_material: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    output_per_unit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    rule_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    purchasing_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    latest_grn_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True, default=Decimal('0.0'), server_default="0.0")
    unit_id: Mapped[Optional[UUID]] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), index=True, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default=None)

    code = synonym("item_id")

    def __init__(self, **kwargs):
        if "code" in kwargs and "item_id" not in kwargs:
            kwargs["item_id"] = kwargs.pop("code")
        super().__init__(**kwargs)


class Supplier(MasterRecord, Base):
    __tablename__ = "suppliers"
    __table_args__ = (CheckConstraint("code = upper(btrim(code)) AND length(code) > 0", name="normalized_code"),)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class SupplierConsumable(MasterRecord, Base):
    __tablename__ = "supplier_consumables"
    __table_args__ = (UniqueConstraint("supplier_id", "consumable_id"),)
    supplier_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True, nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), index=True, nullable=False)
