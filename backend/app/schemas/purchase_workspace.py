from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.requirements_workspace import MonthlyPlanMetadata
from app.schemas.inventory_masters import Reason


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
    master_unit: Optional[str] = None
    requested_purchase_qty: Optional[Decimal] = Field(default=None, ge=0, lt=100000000000000, decimal_places=4)
    requested_purchase_unit: Optional[str] = None
    purchase_notes: Optional[str] = None
    draft_version: int = 0

    required_qty: Decimal = Field(decimal_places=4)
    plant_demands: Optional[dict[str, Decimal]] = None
    dept_demands: Optional[dict[str, Decimal]] = None
    total_plant_qty: Optional[Decimal] = None
    total_dept_qty: Optional[Decimal] = None
    stock_qty: Optional[Decimal] = Field(default=None, decimal_places=4)
    po_pending_qty: Optional[Decimal] = Field(default=None, decimal_places=4)
    shortage_qty: Optional[Decimal] = Field(default=None, decimal_places=4)
    system_recommended_qty: Optional[Decimal] = Field(default=None, decimal_places=4)
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
    notice: Optional[str] = None


class PurchaseSubmitRequest(BaseModel):
    record_ids: list[str]
    reason: Optional[str] = Field(default=None, max_length=2000)


class PurchasePlanEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_id: str
    expected_draft_version: int = Field(ge=0)
    expected_name: str
    expected_master_unit: str
    consumable_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    master_unit: Optional[str] = Field(default=None, min_length=1, max_length=16)
    requested_purchase_qty: Optional[Decimal] = Field(default=None, ge=0, lt=100000000000000, decimal_places=4)
    purchase_notes: Optional[str] = Field(default=None, max_length=2000)


class PurchasePlanSave(BaseModel):
    edits: list[PurchasePlanEdit] = Field(min_length=1, max_length=1000)
    reason: Reason


class PurchaseSubmitResponse(BaseModel):
    message: str
    submitted_count: int
    skipped_count: int
    records: list[PurchaseWorkspaceRecord]
    plan_metadata: MonthlyPlanMetadata
