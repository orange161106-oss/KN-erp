"""ORM models for M3.4 — Plant Confirmation & Additional Requirement Workflow.

Tables:
  user_plants              — many-to-many: users ↔ plants they may act within
  plant_confirmations      — acknowledgement that a plant agrees with a calculated requirement
  requirement_adjustments  — additional consumable demand beyond engine-calculated qty
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserPlant(Base):
    """Associates a user to a plant they are authorised to act within.

    Many-to-many: one user may cover multiple plants; one plant may have
    multiple authorised PLANT_INCHARGE users.
    """

    __tablename__ = "user_plants"
    __table_args__ = (
        UniqueConstraint("user_id", "plant_id", name="uq_user_plant"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # nullable: system-seed rows have no assigning user
    assigned_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    plant: Mapped["Plant"] = relationship("Plant", foreign_keys=[plant_id])  # noqa: F821


class PlantConfirmation(Base):
    """Records that an authorised PLANT_INCHARGE has confirmed a calculated requirement.

    One-to-one with CalculatedRequirement (unique constraint).
    calculated_qty is NEVER modified here — this is an acknowledgement only.
    """

    __tablename__ = "plant_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "calculated_requirement_id",
            name="uq_plant_confirmation_calc_req",
        ),
        Index("ix_plant_conf_version", "planning_version_id"),
        Index("ix_plant_conf_plant", "plant_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    calculated_requirement_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("calculated_requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalised for fast version-level queries without join
    planning_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=False
    )
    plant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    calculated_requirement: Mapped["CalculatedRequirement"] = relationship(  # noqa: F821
        "CalculatedRequirement"
    )
    planning_version: Mapped["PlanningVersion"] = relationship("PlanningVersion")  # noqa: F821
    plant: Mapped["Plant"] = relationship("Plant")  # noqa: F821
    confirmed_by_user: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[confirmed_by]
    )


class RequirementAdjustment(Base):
    """Additional consumable demand beyond the engine-calculated requirement.

    These are SEPARATE records — they do NOT replace or modify calculated_qty.
    Only APPROVED adjustments contribute to the Final Requirement (M3.5 contract).

    Categories (TBD-2 resolved: PLANT_REQUEST is allowed as an adjustable category):
      SPECIAL, MAINTENANCE, TRIAL, REWORK, PLANT_REQUEST, OTHER

    Statuses:
      PENDING  — submitted, awaiting review
      APPROVED — approved by authorised reviewer (M3.5)
      REJECTED — rejected by authorised reviewer (M3.5)
    """

    __tablename__ = "requirement_adjustments"
    __table_args__ = (
        Index("ix_req_adj_version", "planning_version_id"),
        Index("ix_req_adj_plant", "plant_id"),
        Index("ix_req_adj_status", "status"),
        Index("ix_req_adj_version_plant", "planning_version_id", "plant_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("planning_versions.id", ondelete="CASCADE"), nullable=False
    )
    plant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False
    )
    consumable_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("consumables.id", ondelete="RESTRICT"), nullable=False
    )
    # Allowed: SPECIAL | MAINTENANCE | TRIAL | REWORK | PLANT_REQUEST | OTHER
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # Must be > 0; enforced at service layer with Decimal
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    # Copied from consumable.unit at submission time (same pattern as calculated_requirements)
    uom: Mapped[str] = mapped_column(String(16), nullable=False)
    # Mandatory — blank reason is rejected at service layer
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # PENDING | APPROVED | REJECTED
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    # Populated by M3.5 approval workflow
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    planning_version: Mapped["PlanningVersion"] = relationship("PlanningVersion")  # noqa: F821
    plant: Mapped["Plant"] = relationship("Plant")  # noqa: F821
    consumable: Mapped["Consumable"] = relationship("Consumable")  # noqa: F821
    requested_by_user: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[requested_by]
    )
    reviewed_by_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[reviewed_by]
    )
