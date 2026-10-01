from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    row_number: int
    column_name: Optional[str] = None
    error_code: str
    error_message: str
    raw_value: Optional[str] = None


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_version_id: Optional[UUID] = None
    filename: str
    file_size_bytes: int
    row_count: int
    valid_row_count: int
    error_row_count: int
    status: str
    uploaded_at: datetime
    completed_at: Optional[datetime] = None
    errors: list[ImportErrorResponse] = []


class PlanningVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_period: str
    version_number: int
    revision_label: str
    description: Optional[str] = None
    source_filename: str
    status: str
    created_at: datetime
    locked_at: Optional[datetime] = None
    calculated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None


class PRDOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_version_id: UUID
    source_row_number: int
    product_code: str
    plant_code: str
    planned_quantity: Decimal
    uom: str
    target_period: str
    created_at: datetime


class PRDPromoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planning_version_id: UUID
    revision_label: str
    status: str
    total_planned_qty: Decimal
    total_line_items: int
