from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Product to Plant Mapping ---

class ProductPlantBase(BaseModel):
    product_id: UUID
    plant_id: UUID
    route_id: UUID
    is_primary: bool = True


class ProductPlantCreate(ProductPlantBase):
    pass


class ProductPlantUpdate(BaseModel):
    route_id: Optional[UUID] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None


class ProductPlantResponse(ProductPlantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    plant_name: Optional[str] = None
    route_name: Optional[str] = None


# --- Product-Process to Consumable Mapping ---

class ProductProcessConsumableBase(BaseModel):
    product_id: UUID
    process_id: UUID
    consumable_id: UUID


class ProductProcessConsumableCreate(ProductProcessConsumableBase):
    pass


class ProductProcessConsumableUpdate(BaseModel):
    is_active: Optional[bool] = None


class ProductProcessConsumableResponse(ProductProcessConsumableBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    process_name: Optional[str] = None
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    unit: Optional[str] = None


# --- Bulk Operations ---

class BulkProductPlantCreate(BaseModel):
    items: list[ProductPlantCreate]


class BulkProductProcessConsumableCreate(BaseModel):
    items: list[ProductProcessConsumableCreate]


class BulkMappingResponse(BaseModel):
    created_count: int
    errors: list[str] = []


# --- Phase 2 Gate Resolution & Validation Schemas ---

class ResolvedConsumable(BaseModel):
    id: UUID
    code: str
    name: str
    unit: str
    is_active: bool


class ResolvedProcessStep(BaseModel):
    sequence_order: int
    process_id: UUID
    process_name: str
    process_description: Optional[str] = None
    consumables: list[ResolvedConsumable] = []


class ResolvedPlantMapping(BaseModel):
    plant_id: UUID
    plant_name: str
    location: Optional[str] = None
    is_primary: bool
    route_id: UUID
    route_name: str
    steps: list[ResolvedProcessStep] = []


class ProductResolutionResponse(BaseModel):
    product_id: UUID
    product_code: str
    product_name: str
    uom: str
    plant_mappings: list[ResolvedPlantMapping] = []


class MappingValidationIssue(BaseModel):
    issue_type: str  # UNMAPPED_PRODUCT, PROCESS_WITHOUT_CONSUMABLES, INACTIVE_ENTITY
    severity: str    # ERROR, WARNING
    product_id: Optional[UUID] = None
    product_code: Optional[str] = None
    plant_id: Optional[UUID] = None
    process_id: Optional[UUID] = None
    consumable_id: Optional[UUID] = None
    message: str


class MappingValidationReport(BaseModel):
    is_valid: bool
    total_products_checked: int
    unmapped_products_count: int
    issues: list[MappingValidationIssue] = []
