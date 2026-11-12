"""Reviewed norm import contracts; workbook quantities remain reference evidence."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rules.types import RoundingPolicy
from app.schemas.rules import ConsumptionNormResponse


class NormImportRowInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_number: int = Field(ge=1)
    part_number: str = Field(default="", max_length=128)
    part_name: str = Field(default="", max_length=255)
    used_part_number: str = Field(default="", max_length=128)
    consumable_code: str = Field(default="", max_length=64)
    consumable_name: str = Field(default="", max_length=255)
    process_name: str = Field(default="", max_length=128)
    thickness: str | None = None
    process_count: str | None = None
    reference_production_qty: str | None = None
    reference_schedule_qty: str | None = None
    output_per_unit: str | None = None


class NormImportError(BaseModel):
    field: str
    code: str
    message: str


class NormImportRow(NormImportRowInput):
    product_id: str | None = None
    consumable_id: str | None = None
    process_id: str | None = None
    unit_id: str | None = None
    unit_code: str | None = None
    action: Literal["CREATE", "EXISTING", "CONFLICT", "INVALID"] = "CREATE"
    errors: list[NormImportError] = Field(default_factory=list)
    is_general: bool = False
    is_possible_duplicate: bool = False
    sch_differs: bool = False
    sch_is_zero: bool = False
    change_status: Literal["unchanged", "changed", "new"] = "new"
    warnings: list[str] = Field(default_factory=list)


class NormImportPreview(BaseModel):
    filename: str
    source_sha256: str
    review_token: str
    sheet_name: str
    row_count: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    existing_count: int
    conflict_count: int
    general_count: int = 0
    skipped_total_count: int = 0
    skipped_empty_count: int = 0
    duplicate_groups_count: int = 0
    rows: list[NormImportRow]


class NormImportCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: list[NormImportRowInput] = Field(min_length=1, max_length=5000)


class NormImportReview(NormImportCorrections):
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    formula_choice: Literal["PRODUCTION_RATE_FROM_PROCESS_COUNT"]
    effective_from: date
    rounding_policy: RoundingPolicy = RoundingPolicy.NONE
    rounding_precision: int = Field(default=4, ge=0, le=4)
    mode: Literal["CREATE", "SUPERSEDE"] = "CREATE"
    reason: str = Field(min_length=1, max_length=2000)
    skip_invalid: bool = False


class NormImportResult(BaseModel):
    created_count: int
    skipped_count: int
    superseded_count: int
    skipped_invalid_count: int = 0
    replayed: bool = False
    records: list[ConsumptionNormResponse]
    message: str
