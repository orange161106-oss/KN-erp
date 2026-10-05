"""Pydantic request/response schemas for M5.2 — Purchase Approval Queue."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ApprovalStatus = Literal["PENDING", "APPROVED", "MODIFIED", "REJECTED"]


class SubmitPurchaseApprovalRequest(BaseModel):
    consumable_id: UUID
    supplier_id: UUID
    planning_version_id: Optional[UUID] = None
    raw_calculated_qty: Decimal = Field(decimal_places=4)
    system_recommended_qty: Decimal = Field(decimal_places=4)
    uom: str = Field(min_length=1, max_length=16)
    reason: Optional[str] = Field(default=None, max_length=2000)


class ReviewPurchaseApprovalRequest(BaseModel):
    action: Literal["APPROVE", "MODIFY", "REJECT"]
    approved_qty: Optional[Decimal] = Field(default=None, decimal_places=4)
    reason: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: Optional[str], info) -> Optional[str]:
        action = info.data.get("action")
        if action in ("MODIFY", "REJECT"):
            if not v or not v.strip():
                raise ValueError(f"Reason is required when action is '{action}'.")
            return v.strip()
        return v.strip() if v else None

    @field_validator("approved_qty")
    @classmethod
    def validate_approved_qty(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        action = info.data.get("action")
        if action in ("APPROVE", "MODIFY"):
            if v is not None and v <= Decimal("0"):
                raise ValueError("Approved quantity must be positive.")
        return v


class PurchaseApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consumable_id: UUID
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    supplier_id: UUID
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    planning_version_id: Optional[UUID] = None
    rule_version: str
    raw_calculated_qty: Decimal
    system_recommended_qty: Decimal
    approved_qty: Optional[Decimal] = None
    uom: str
    status: ApprovalStatus
    reason: Optional[str] = None
    requested_by: Optional[UUID] = None
    requested_by_username: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_by_username: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
