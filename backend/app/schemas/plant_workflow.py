"""Pydantic request/response schemas for M3.4 — Plant Workflow.

ORM models are never exposed directly; all data crosses the API boundary
through these schemas only.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Enumerations ───────────────────────────────────────────────────────────────

AdjustmentCategory = Literal[
    "SPECIAL", "MAINTENANCE", "TRIAL", "REWORK", "PLANT_REQUEST", "OTHER"
]
AdjustmentStatus = Literal["PENDING", "APPROVED", "REJECTED"]


# ── UserPlant ──────────────────────────────────────────────────────────────────

class UserPlantAssignRequest(BaseModel):
    user_id: UUID
    plant_id: UUID


class UserPlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    plant_id: UUID
    assigned_at: datetime
    assigned_by: Optional[UUID] = None


# ── Plant Confirmation ─────────────────────────────────────────────────────────

class ConfirmRequirementRequest(BaseModel):
    calculated_requirement_id: UUID
    notes: Optional[str] = Field(default=None, max_length=2000)


class PlantConfirmationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    calculated_requirement_id: UUID
    planning_version_id: UUID
    plant_id: UUID
    plant_name: Optional[str] = None
    confirmed_by: UUID
    confirmed_by_username: Optional[str] = None
    confirmed_at: datetime
    notes: Optional[str] = None


# ── Requirement Adjustment ─────────────────────────────────────────────────────

class SubmitAdjustmentRequest(BaseModel):
    planning_version_id: UUID
    plant_id: UUID
    consumable_id: UUID
    category: AdjustmentCategory
    requested_qty: Decimal = Field(gt=Decimal("0"), decimal_places=4)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason must not be blank or whitespace only")
        return stripped


class RequirementAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_version_id: UUID
    plant_id: UUID
    plant_name: Optional[str] = None
    consumable_id: UUID
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    category: str
    requested_qty: Decimal
    uom: str
    reason: str
    requested_by: UUID
    requested_by_username: Optional[str] = None
    requested_at: datetime
    status: str
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    reviewer_comment: Optional[str] = None


class ReviewAdjustmentRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    reviewer_comment: Optional[str] = Field(default=None, max_length=2000)


class FinalRequirementItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planning_version_id: UUID
    plant_id: UUID
    plant_name: Optional[str] = None
    consumable_id: UUID
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    uom: str
    calculated_qty: Decimal
    approved_adjustment_qty: Decimal
    final_required_qty: Decimal
    is_fully_confirmed: bool = False

