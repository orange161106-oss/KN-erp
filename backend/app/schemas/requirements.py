from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalculationRunRequest(BaseModel):
    planning_version_id: UUID
    as_of_date: Optional[date] = None
    force_recalculate: bool = True


class CalculatedRevisionApprovalResponse(BaseModel):
    planning_version_id: UUID
    status: str
    replayed: bool


class CalculatedRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_version_id: UUID
    prd_order_item_id: UUID
    product_id: UUID
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    plant_id: UUID
    plant_name: Optional[str] = None
    process_id: UUID
    process_name: Optional[str] = None
    consumable_id: UUID
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    rule_id: UUID
    rule_type: str
    rule_version: int
    parameters: dict[str, Any]
    source_production_qty: Decimal
    raw_requirement: Decimal
    rounding_policy: str
    rounding_precision: int
    calculated_qty: Decimal
    unit_id: UUID
    uom: str
    calculation_steps: list[dict[str, Any]]
    explanation_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RequirementCalculationErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_version_id: UUID
    prd_order_item_id: UUID
    product_id: UUID
    product_code: Optional[str] = None
    plant_id: Optional[UUID] = None
    plant_name: Optional[str] = None
    consumable_id: Optional[UUID] = None
    consumable_code: Optional[str] = None
    error_code: str
    error_message: str
    context_data: Optional[dict[str, Any]] = None
    created_at: datetime


class ConsumableAggregateItem(BaseModel):
    consumable_id: UUID
    consumable_code: str
    consumable_name: str
    uom: str
    total_raw_requirement: Decimal
    total_calculated_qty: Decimal
    line_items_count: int


class RequirementCalculationRunResponse(BaseModel):
    planning_version_id: UUID
    planning_period: str
    revision_label: str
    status: str
    total_items_processed: int
    successful_requirements_count: int
    error_count: int
    summary_by_consumable: list[ConsumableAggregateItem]
    errors: list[RequirementCalculationErrorResponse]


class MonthlyRequirementPlanCreate(BaseModel):
    plant_id: str
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class RequirementLineItemCreate(BaseModel):
    consumable_id: UUID
    requested_qty: float = Field(ge=0)


class RequirementLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    consumable_id: UUID
    requested_qty: float
    item_id: Optional[str] = None
    consumable_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MonthlyRequirementPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plant_id: str
    month: int
    year: int
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    line_items: list[RequirementLineItemResponse] = []


class BulkUploadResponse(BaseModel):
    total_rows: int
    upserted: int
    errors: list[str] = []
    items: list[RequirementLineItemResponse] = []


class AggregatedRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    month: int
    year: int
    consumable_id: UUID
    total_gross_qty: float
    net_purchase_qty: float
    consumable_name: Optional[str] = None
    item_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AggregationRunResponse(BaseModel):
    month: int
    year: int
    total_approved_plans: int
    total_aggregated_consumables: int
    records: list[AggregatedRequirementResponse]


