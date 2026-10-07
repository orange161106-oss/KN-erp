from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class PRDWorkspaceRecordResponse(BaseModel):
    id: UUID
    row_index: int | None = None
    plant: str
    customer: str | None = None
    product_code: str
    description: str
    planned_quantity: str
    uom: str = "Nos"
    target_period: str
    planning_version: str = "V1"
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
    product_code: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=256)
    planned_quantity: str | float | int
    uom: str = Field(default="Nos", max_length=32)
    target_period: str = Field(min_length=1, max_length=32)
    planning_version: str = Field(default="V1", max_length=32)
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

