from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column

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
    __table_args__ = (CheckConstraint("code = upper(btrim(code)) AND length(code) > 0", name="normalized_code"),)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("units.id", ondelete="RESTRICT"), index=True, nullable=False)


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
