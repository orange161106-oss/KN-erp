"""Pydantic schemas for Monthly Purchase Planning."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PurchasePlanItemSchema(BaseModel):
    id: str
    plan_id: str
    s_no: Optional[int] = None
    item_id: str
    description: str
    req_type: Optional[str] = None
    category: Optional[str] = None
    type_of_material: Optional[str] = None
    unit: str = "PCS"
    purchasing_unit: Optional[str] = None
    output_per_unit: Optional[Decimal] = None

    # Stock & Commercial rules
    rate: Optional[Decimal] = None
    moq: Optional[Decimal] = None
    min_stock_level: Optional[Decimal] = None
    max_stock_level: Optional[Decimal] = None
    lead_time_days: Optional[int] = None

    # Previous Month Stock
    prev_opening_qty: Optional[Decimal] = None
    prev_opening_val: Optional[Decimal] = None
    prev_receipt_qty: Optional[Decimal] = None
    prev_issue_qty: Optional[Decimal] = None
    prev_closing_qty: Optional[Decimal] = None
    prev_closing_val: Optional[Decimal] = None
    prev_prd_qty: Optional[Decimal] = None

    # Selected Month Plan (R1)
    sch_qty: Optional[Decimal] = None
    req_qty: Optional[Decimal] = None
    order_qty: Optional[Decimal] = None
    order_value: Optional[Decimal] = None
    receipt_qty: Optional[Decimal] = None
    receipt_value: Optional[Decimal] = None

    # Revision 2 (R2)
    sch_qty_r2: Optional[Decimal] = None
    req_qty_r2: Optional[Decimal] = None
    order_qty_r2: Optional[Decimal] = None
    order_value_r2: Optional[Decimal] = None
    receipt_qty_r2: Optional[Decimal] = None
    receipt_val_r2: Optional[Decimal] = None

    # Actual Purchase
    pur_qty: Optional[Decimal] = None
    pur_value: Optional[Decimal] = None
    bal_pur_qty: Optional[Decimal] = None
    bal_pur_value: Optional[Decimal] = None

    # Supplier / MD View metadata
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    part_no_saleable: Optional[str] = None
    saleable_part_name: Optional[str] = None
    used_part_no: Optional[str] = None
    process_name: Optional[str] = None
    thickness_gsm: Optional[str] = None
    no_of_process_per_part: Optional[Decimal] = None

    # Allocations & Analysis
    plant_allocations: Optional[dict[str, Any]] = Field(default_factory=dict)
    consumption_analysis: Optional[dict[str, Any]] = Field(default_factory=dict)

    override_reason: Optional[str] = None
    is_modified: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PurchasePlanResponse(BaseModel):
    id: str
    planning_period: str
    planning_version_id: Optional[str] = None
    revision_label: str
    status: str
    msl_days_gas: Decimal
    msl_days_general: Decimal
    month_days: int
    working_days: int
    source_filename: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    modified_by: Optional[str] = None
    modified_by_name: Optional[str] = None
    modified_at: Optional[datetime] = None
    total_items: int
    total_order_value: Decimal
    items: list[PurchasePlanItemSchema] = Field(default_factory=list)


class UpdatePlanParametersRequest(BaseModel):
    planning_period: str
    msl_days_gas: Optional[Decimal] = None
    msl_days_general: Optional[Decimal] = None
    working_days: Optional[int] = None


class PurchasePlanItemUpdateRequest(BaseModel):
    id: str
    item_id: Optional[str] = None
    description: Optional[str] = None
    rate: Optional[Decimal] = None
    moq: Optional[Decimal] = None
    min_stock_level: Optional[Decimal] = None
    max_stock_level: Optional[Decimal] = None
    lead_time_days: Optional[int] = None
    order_qty: Optional[Decimal] = None
    override_reason: Optional[str] = None
    plant_allocations: Optional[dict[str, Any]] = None


class SavePurchasePlanRequest(BaseModel):
    planning_period: str
    items: list[PurchasePlanItemUpdateRequest]


class RecalculatePlanRequest(BaseModel):
    planning_period: str
    msl_days_gas: Optional[Decimal] = None
    msl_days_general: Optional[Decimal] = None


class SendToApprovalRequest(BaseModel):
    planning_period: str
    item_ids: Optional[list[str]] = None  # None means all items with order_qty > 0


class PlanInspectResult(BaseModel):
    filename: str
    detected_view: str  # 'NORMAL_VIEW' | 'MD_VIEW' | 'UNKNOWN'
    sheet_name: str
    total_rows: int
    total_columns: int
    headers: list[str]
    missing_required_headers: list[str]
    validation_errors: list[dict[str, Any]]
    sample_rows: list[dict[str, Any]]


class PlanImportConfirmRequest(BaseModel):
    planning_period: str
    detected_view: str
    filename: str
    rows: list[dict[str, Any]]
