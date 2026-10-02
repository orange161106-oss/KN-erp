from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CalculationRunRequest(BaseModel):
    planning_version_id: UUID
    as_of_date: Optional[date] = None
    force_recalculate: bool = True


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

