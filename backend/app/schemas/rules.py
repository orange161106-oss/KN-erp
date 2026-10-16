from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rules.models import CalculationResult
from app.domain.rules.types import RoundingPolicy, RuleType


class ConsumptionNormBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_type: RuleType
    consumable_id: UUID
    product_id: Optional[UUID] = None
    process_id: Optional[UUID] = None
    plant_id: Optional[UUID] = None
    parameters: dict[str, Any]
    unit_id: UUID
    rounding_policy: RoundingPolicy = RoundingPolicy.NONE
    rounding_precision: int = Field(default=2, ge=0, le=4)
    effective_from: date
    effective_to: Optional[date] = None
    reference_data: Optional[dict[str, Any]] = None


class ConsumptionNormCreate(ConsumptionNormBase):
    pass


class ConsumptionNormUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameters: Optional[dict[str, Any]] = None
    rounding_policy: Optional[RoundingPolicy] = None
    rounding_precision: Optional[int] = Field(default=None, ge=0, le=4)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None
    reference_data: Optional[dict[str, Any]] = None
    expected_version: Optional[int] = Field(default=None, ge=1)


class ConsumptionNormResponse(ConsumptionNormBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    process_name: Optional[str] = None
    plant_name: Optional[str] = None
    unit_code: Optional[str] = None
    product_part_number: Optional[str] = None
    product_item_id: Optional[str] = None


class ConsumptionNormBatchItem(ConsumptionNormUpdate):
    norm_id: UUID
    expected_version: int = Field(ge=1)


class ConsumptionNormBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[ConsumptionNormBatchItem] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)


class ConsumptionNormBatchResponse(BaseModel):
    updated_count: int
    records: list[ConsumptionNormResponse]


class EvaluationRequest(BaseModel):
    consumable_id: UUID
    product_id: Optional[UUID] = None
    process_id: Optional[UUID] = None
    plant_id: Optional[UUID] = None
    production_quantity: Decimal = Decimal("0")
    requested_quantity: Optional[Decimal] = None
    as_of_date: Optional[date] = None


class EvaluationResponse(BaseModel):
    norm_id: UUID
    calculation: CalculationResult


# --- M3.2 Explainable Single Requirement Calculation Models ---

class PlanningVersionRef(BaseModel):
    id: UUID
    planning_period: str
    version_number: int
    revision_label: str
    status: str


class ProductionSourceRef(BaseModel):
    item_id: UUID
    row_number: int
    planned_quantity: Decimal
    uom: str
    target_period: str


class ProductRef(BaseModel):
    id: UUID
    code: str
    name: str


class PlantRef(BaseModel):
    id: UUID
    name: str
    location: Optional[str] = None


class ProcessRef(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None


class ConsumableRef(BaseModel):
    id: UUID
    code: str
    name: str
    unit: str


class RuleRef(BaseModel):
    norm_id: UUID
    rule_type: str
    version: int
    parameters: dict[str, Any]


class ItemCalculationRequest(BaseModel):
    prd_item_id: UUID
    consumable_id: UUID
    plant_id: Optional[UUID] = None
    as_of_date: Optional[date] = None


class SingleRequirementCalculationResponse(BaseModel):
    planning_version: PlanningVersionRef
    production_source: ProductionSourceRef
    product: ProductRef
    plant: PlantRef
    process: ProcessRef
    consumable: ConsumableRef
    rule: RuleRef
    calculation: CalculationResult

