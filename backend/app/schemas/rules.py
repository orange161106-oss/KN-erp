from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.rules.models import CalculationResult
from app.domain.rules.types import RoundingPolicy, RuleType


class ConsumptionNormBase(BaseModel):
    rule_type: RuleType
    consumable_id: UUID
    product_id: Optional[UUID] = None
    process_id: Optional[UUID] = None
    plant_id: Optional[UUID] = None
    parameters: dict[str, Any]
    unit_id: UUID
    rounding_policy: RoundingPolicy = RoundingPolicy.NONE
    rounding_precision: int = 2
    effective_from: date
    effective_to: Optional[date] = None


class ConsumptionNormCreate(ConsumptionNormBase):
    pass


class ConsumptionNormUpdate(BaseModel):
    parameters: Optional[dict[str, Any]] = None
    rounding_policy: Optional[RoundingPolicy] = None
    rounding_precision: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None


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
