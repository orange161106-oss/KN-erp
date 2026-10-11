from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, Uuid, func, true
from sqlalchemy.schema import conv
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductPlant(Base):
    __tablename__ = "product_plants"
    __table_args__ = (
        UniqueConstraint("product_id", "plant_id", name=conv("uq_product_plants_product_id_plant_id")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    plant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("plants.id", ondelete="RESTRICT"), index=True, nullable=False)
    route_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("routes.id", ondelete="RESTRICT"), index=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    product: Mapped["Product"] = relationship("Product")
    plant: Mapped["Plant"] = relationship("Plant")
    route: Mapped["Route"] = relationship("Route")


class ProductProcessConsumable(Base):
    __tablename__ = "product_process_consumables"
    __table_args__ = (
        UniqueConstraint("product_id", "process_id", "consumable_id", name=conv("uq_product_process_consumables_product_id_process_id_consumable_id")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    process_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("processes.id", ondelete="RESTRICT"), index=True, nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    consumable_item: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    part_no_saleable_item: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    used_for_name_of_saleable_part: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    used_part_no_prd_order: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    process_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    material_thickness_in_mm_gsm: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    no_of_process_per_part: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), server_default="1.0000", default=Decimal("1.0000"), nullable=True)
    output_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    product: Mapped["Product"] = relationship("Product")
    process: Mapped["Process"] = relationship("Process")
    consumable: Mapped["Consumable"] = relationship("Consumable")
