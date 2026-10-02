from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductPlant(Base):
    __tablename__ = "product_plants"
    __table_args__ = (
        UniqueConstraint("product_id", "plant_id", name="uq_product_plant"),
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
        UniqueConstraint("product_id", "process_id", "consumable_id", name="uq_product_process_consumable"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    process_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("processes.id", ondelete="RESTRICT"), index=True, nullable=False)
    consumable_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    product: Mapped["Product"] = relationship("Product")
    process: Mapped["Process"] = relationship("Process")
    consumable: Mapped["Consumable"] = relationship("Consumable")
