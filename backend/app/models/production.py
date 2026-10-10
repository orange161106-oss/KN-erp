from uuid import UUID, uuid4
from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, Integer, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

class Process(Base):
    __tablename__ = "processes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

class Route(Base):
    __tablename__ = "routes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    steps: Mapped[list["RouteStep"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="RouteStep.sequence_order"
    )

class RouteStep(Base):
    __tablename__ = "route_steps"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    route_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("routes.id"), nullable=False)
    process_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("processes.id"), nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)

    route: Mapped["Route"] = relationship(back_populates="steps")
    process: Mapped["Process"] = relationship()