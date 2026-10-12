from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.requirements_workspace import MonthlyPlanMetadata


class PurchaseWorkspaceRecord(BaseModel):
    id: str
    planning_period: str
    planning_month: int
    planning_year: int
    plan_id: Optional[str] = None
    revision: str = "R0"

    consumable_id: Optional[UUID] = None
    consumable_code: str
    consumable_name: str
    supplier_id: Optional[UUID] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    unit: str

    required_qty: Decimal = Field(decimal_places=4)
    stock_qty: Decimal = Field(decimal_places=4)
    po_pending_qty: Decimal = Field(decimal_places=4)
    shortage_qty: Decimal = Field(decimal_places=4)
    system_recommended_qty: Decimal = Field(decimal_places=4)
    approval_status: Optional[str] = None
    approval_id: Optional[UUID] = None
    status: str
    remarks: Optional[str] = None

    source_row_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PurchaseWorkspaceResponse(BaseModel):
    plan_metadata: MonthlyPlanMetadata
    records: list[PurchaseWorkspaceRecord]


class PurchaseSubmitRequest(BaseModel):
    record_ids: list[str]
    reason: Optional[str] = Field(default=None, max_length=2000)


class PurchaseSubmitResponse(BaseModel):
    message: str
    submitted_count: int
    skipped_count: int
    records: list[PurchaseWorkspaceRecord]
    plan_metadata: MonthlyPlanMetadata
