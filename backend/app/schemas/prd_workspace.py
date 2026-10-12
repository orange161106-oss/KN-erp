from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PRDWorkspaceRecordResponse(BaseModel):
    id: UUID
    row_index: int | None = None
    plant: str
    customer: str | None = None
    customer_id: UUID | None = None
    customer_code: str | None = None
    customer_group: str | None = None
    product_code: str
    description: str
    planned_quantity: str
    uom: str = "Nos"
    target_period: str
    planning_version: str = "V1"
    revision: str | None = None
    schedule_given_on: datetime | None = None
    section_type: str = "STANDARD"
    status: str = "SAVED"
    remarks: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PRDWorkspaceRecordInput(BaseModel):
    id: UUID | None = None
    row_index: int | None = None
    plant: str = Field(min_length=1, max_length=64)
    customer: str | None = None
    customer_id: UUID | None = None
    customer_code: str | None = None
    customer_group: str | None = None
    product_code: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=256)
    planned_quantity: str | float | int
    uom: str = Field(default="Nos", max_length=32)
    target_period: str = Field(min_length=1, max_length=32)
    planning_version: str = Field(default="V1", max_length=32)
    revision: str | None = None
    section_type: str = "STANDARD"
    status: str = "SAVED"
    remarks: str | None = None


class PRDWorkspaceSaveRequest(BaseModel):
    records: list[PRDWorkspaceRecordInput]
    deleted_ids: list[UUID] = []
    reason: str = Field(default="PRD Workspace update", min_length=1, max_length=512)


class PRDWorkspaceSaveResponse(BaseModel):
    saved_count: int
    deleted_count: int
    records: list[PRDWorkspaceRecordResponse]


class PRDWorkspaceBulkDeleteRequest(BaseModel):
    ids: list[UUID] = []
    delete_all_matching: bool = False
    search: str | None = None
    plant: str | None = None
    target_period: str | None = None
    planning_version: str | None = None
    status: str | None = None
    reason: str = Field(default="Bulk delete PRD records", min_length=1, max_length=512)


class PRDWorkspaceBulkDeleteResponse(BaseModel):
    deleted_count: int


class PRDExcelSheetInspectInfo(BaseModel):
    name: str
    row_count: int
    column_count: int
    headers: list[str]
    sample_rows: list[dict[str, str]]


class PRDExcelInspectResponse(BaseModel):
    filename: str
    sheets: list[PRDExcelSheetInspectInfo]


class PRDExcelImportResponse(BaseModel):
    sheet_name: str
    imported_count: int
    records: list[PRDWorkspaceRecordResponse]


class SalesScheduleRevisionInfo(BaseModel):
    col_index: int
    month_label: str
    planning_period: str
    revision_label: str
    schedule_given_on: Optional[str] = None
    month_date: Optional[str] = None


class SalesScheduleBlockInfo(BaseModel):
    block_index: int
    heading_text: str
    closing_label: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    customer_id: Optional[str] = None
    group_label: Optional[str] = None
    section_type: str
    part_count: int
    quantities: dict[str, str]
    sheet_totals: dict[str, str]
    reconciliation_ok: bool
    reconciliation_diff: dict[str, str] = {}
    is_mapped: bool


class SalesScheduleGrandTotal(BaseModel):
    parts_sum: dict[str, str]
    sheet_grand_total: dict[str, str]
    reconciliation_ok: bool
    diffs: dict[str, str] = {}


class SalesScheduleImportPreviewResponse(BaseModel):
    filename: str
    sheet_name: str
    sheet_names: list[str]
    header_row_index: int
    available_revisions: list[SalesScheduleRevisionInfo]
    active_revisions: list[SalesScheduleRevisionInfo]
    blocks: list[SalesScheduleBlockInfo]
    unmapped_aliases: list[str]
    grand_total: SalesScheduleGrandTotal
    total_part_rows: int
    sample_rows: list[dict[str, Any]]
    can_confirm: bool
    warnings: list[str] = []
    errors: list[str] = []
    file_token: str


class SalesScheduleImportConfirmRequest(BaseModel):
    file_token: str
    sheet_name: str
    target_period: Optional[str] = None
    revision_label: Optional[str] = None
    plant_code: Optional[str] = "Plant 1"
    mode: str = "APPEND"
    reason: str = Field(default="Confirmed KNL sales schedule import", max_length=512)
    alias_mappings: Optional[dict[str, UUID]] = None
