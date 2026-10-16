from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalculationRunRequest(BaseModel):
    planning_version_id: UUID
    as_of_date: Optional[date] = None
    force_recalculate: bool = True


class CalculatedRevisionApprovalRequest(BaseModel):
    acknowledge_missing_norms: bool = False


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
    plant_id: UUID | None
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
    total_basic_requirement: Optional[Decimal] = None
    line_items_count: int
    parts_breakdown: Optional[list[dict[str, Any]]] = None


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
    has_missing_norms: Optional[bool] = False
    missing_parts_count: Optional[int] = 0
    missing_parts_qty: Optional[Decimal] = Decimal('0')
    no_consumption_norms: Optional[list[dict[str, Any]]] = None
    duplicate_norm_groups_count: Optional[int] = 0
    duplicate_groups_warning: Optional[str] = None


class MonthlyRequirementPlanCreate(BaseModel):
    plant_id: str
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class RequirementLineItemCreate(BaseModel):
    consumable_id: Optional[UUID] = None
    item_id: Optional[str] = None
    item_code: Optional[str] = None
    item_description: Optional[str] = None
    part_no: Optional[str] = None
    unit: Optional[str] = None
    serial_no: Optional[int] = None
    formula_qty: Optional[float] = 0.0
    requested_qty: float = Field(default=0.0, ge=0)
    approved_qty: Optional[float] = 0.0
    is_modified: Optional[bool] = False
    modification_reason: Optional[str] = None


class RequirementLineItemUpdate(BaseModel):
    formula_qty: Optional[float] = None
    requested_qty: Optional[float] = Field(default=None, ge=0)
    approved_qty: Optional[float] = None
    is_modified: Optional[bool] = None
    modification_reason: Optional[str] = None
    serial_no: Optional[int] = None
    part_no: Optional[str] = None
    unit: Optional[str] = None
    item_description: Optional[str] = None


class RequirementLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    consumable_id: UUID
    serial_no: Optional[int] = None
    part_no: Optional[str] = None
    formula_qty: float = 0.0
    requested_qty: float = 0.0
    approved_qty: float = 0.0
    is_modified: bool = False
    modification_reason: Optional[str] = None
    item_id: Optional[str] = None
    item_code: Optional[str] = None
    consumable_name: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RejectPlanRequest(BaseModel):
    reason: Optional[str] = None


class FormulaGenerationResponse(BaseModel):
    month: int
    year: int
    plans_updated: list[str]
    total_items_computed: int
    message: str


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
    plants_affected: list[str] = []


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
    item_code: Optional[str] = None
    item_description: Optional[str] = None
    part_no: Optional[str] = None
    unit: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AggregationRunResponse(BaseModel):
    month: int
    year: int
    total_approved_plans: int
    total_aggregated_consumables: int
    records: list[AggregatedRequirementResponse]


