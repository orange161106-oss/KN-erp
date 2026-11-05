from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UnknownItemIdError(BaseModel):
    sheet: str
    row: int
    item_id: str
    description: Optional[str] = None
    unit: Optional[str] = None
    quantity: Decimal


class DuplicateItemWarning(BaseModel):
    sheet: str
    row: int
    item_id: str
    description: Optional[str] = None
    quantity: Decimal
    action_taken: str = "Skipped duplicate row; kept first occurrence"


class UnitConflictWarning(BaseModel):
    item_id: str
    consumable_name: Optional[str] = None
    master_purchasing_unit: Optional[str] = None
    submitted_units: dict[str, str] = Field(default_factory=dict)  # source_code -> unit
    is_compatible: bool = False
    message: str


class ParsedRequestRow(BaseModel):
    source_type: str
    source_code: str
    sheet_name: str
    row_number: int
    item_id: str
    consumable_id: UUID
    consumable_name: str
    unit: str
    quantity: Decimal


class SheetImportSummary(BaseModel):
    sheet_name: str
    source_type: str
    source_code: str
    header_row: int
    month_column: int
    item_id_column: int
    valid_count: int
    unknown_count: int
    duplicate_count: int
    zero_or_blank_count: int
    total_quantity: Decimal


class RequirementRequestPreviewResponse(BaseModel):
    filename: str
    planning_month: int
    planning_year: int
    planning_period: str
    file_hash: str
    sheets_processed: list[SheetImportSummary] = Field(default_factory=list)
    total_valid_requests: int = 0
    total_unknown_ids: int = 0
    total_zero_skipped: int = 0
    valid_requests: list[ParsedRequestRow] = Field(default_factory=list)
    unknown_items: list[UnknownItemIdError] = Field(default_factory=list)
    duplicates: list[DuplicateItemWarning] = Field(default_factory=list)
    unit_conflicts: list[UnitConflictWarning] = Field(default_factory=list)
    can_confirm: bool = False
    existing_batches_warning: Optional[str] = None
    review_token: str


class RequirementRequestConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    planning_month: int = Field(ge=1, le=12)
    planning_year: int = Field(ge=2000, le=2100)
    file_hash: str
    review_token: str
    source_codes: Optional[list[str]] = None  # None means confirm all sources in preview


class RequirementRequestConfirmResponse(BaseModel):
    planning_month: int
    planning_year: int
    planning_period: str
    imported_batch_count: int
    imported_row_count: int
    superseded_batch_count: int
    batch_ids: list[UUID]
    message: str


class RequirementRequestResponse(BaseModel):
    id: UUID
    planning_month: int
    planning_year: int
    source_type: str
    source_code: str
    consumable_id: UUID
    consumable_code: str
    consumable_name: str
    quantity: Decimal
    unit: str
    batch_id: UUID
    created_at: datetime

