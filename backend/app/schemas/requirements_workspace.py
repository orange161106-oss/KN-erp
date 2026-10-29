from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field


class RequirementWorkspaceRecord(BaseModel):
    id: str
    planning_period: str = ""
    planning_month: Optional[int] = None
    planning_year: Optional[int] = None
    revision: str = "R0"
    plan_id: Optional[str] = None

    # Group 1: For Component (Frozen left columns)
    part_name: str = ""  # Used For – Part Name
    part_number: str = ""  # Used Part No. (Production Order)

    # Group 2: For Consumables
    consumable_code: str = ""  # Consumable Item ID
    consumable_name: str = ""  # Consumable Name
    process_name: str = ""  # Process Name
    part_thickness: str = "0.0000"  # Part Thickness (mm)
    process_count: int = 1  # Number of Processes
    production_order_qty: str = "0.0000"  # Production Order for Selected Month
    scheduled_consumable_qty: str = "0.0000"  # Scheduled Consumable Quantity for Selected Month

    # Group 3: Inventory, Unit & Operational Status
    plant: str = "Plant 1"
    process: str = ""  # alias for process_name
    description: str = ""  # alias for consumable_name
    unit: str = "NOS"
    rule_type: str = "PRODUCTION_RATE"
    required_qty: str = "0.0000"  # alias for scheduled_consumable_qty
    stock_qty: str = "0.0000"
    shortage_qty: str = "0.0000"
    po_pending_qty: str = "0.0000"
    msl: str = "0.0000"
    status: str = "Normal"  # 'Normal', 'Low', 'Critical shortage', 'Calculated', 'Configuration required'
    remarks: Optional[str] = None

    # Month-End Overwrite & MRP Balance Tracking
    opening_stock: str = "0.0000"
    grn_received_qty: str = "0.0000"
    consumed_qty: str = "0.0000"
    closing_stock: str = "0.0000"
    gross_requirement: str = "0.0000"
    net_order_requirement: str = "0.0000"
    last_synced_at: Optional[datetime] = None
    grn_source_file: Optional[str] = None
    invoice_no: Optional[str] = None
    grn_date: Optional[datetime] = None

    # Historical Rolling Average & Documentation
    historical_avg_qty: Optional[str] = "0.0000"
    active_month_count: Optional[int] = 0
    doc_ref: Optional[str] = None

    # Metadata & Auditing
    created_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None


class MonthlyPlanMetadata(BaseModel):
    has_plan: bool = False
    plan_id: Optional[str] = None
    planning_month: Optional[int] = None
    planning_year: Optional[int] = None
    planning_period: str = ""
    status: str = "DRAFT"
    revision_label: str = "R0"
    source_filename: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    record_count: int = 0
    issue_count: int = 0
    source_workflow: Optional[str] = None
    grn_reconciled: bool = False
    last_grn_synced_at: Optional[datetime] = None


class MRPGRNUploadResponse(BaseModel):
    status: str = "success"
    updated_count: int
    inserted_count: int
    period: str
    consumables_updated_count: int = 0


class RequirementRowError(BaseModel):
    row_number: int
    column_name: str
    error_description: str


class RequirementExcelInspectResponse(BaseModel):
    filename: str
    total_rows: int
    valid_rows: int
    error_count: int
    planning_month: int
    planning_year: int
    planning_period: str
    plan_already_exists: bool
    errors: list[RequirementRowError]
    preview_rows: list[dict[str, Any]]


class RequirementImportRequest(BaseModel):
    planning_month: int = Field(..., ge=1, le=12)
    planning_year: int = Field(..., ge=2020, le=2050)
    source_filename: str
    records: list[dict[str, Any]]
    overwrite: bool = False


class RequirementUpdateItem(BaseModel):
    id: str
    scheduled_consumable_qty: Optional[str] = None
    gross_requirement: Optional[str] = None
    production_order_qty: Optional[str] = None
    part_thickness: Optional[str] = None
    process_count: Optional[int] = None
    remarks: Optional[str] = None
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    unit: Optional[str] = None
    part_number: Optional[str] = None
    plant: Optional[str] = None
    month: Optional[int] = None
    year: Optional[int] = None


class RequirementBatchUpdateRequest(BaseModel):
    records: list[RequirementUpdateItem]


class RequirementBatchUpdateResponse(BaseModel):
    message: str
    updated_count: int
    records: list[RequirementWorkspaceRecord]
    plan_metadata: MonthlyPlanMetadata


class RequirementRecalculateResponse(BaseModel):
    message: str
    record_count: int
    critical_shortages: int
    low_stock: int
    records: list[RequirementWorkspaceRecord]
    plan_metadata: Optional[MonthlyPlanMetadata] = None


class RequirementBulkDeleteRequest(BaseModel):
    record_ids: list[str]
    reason: Optional[str] = None


class RequirementBulkDeleteResponse(BaseModel):
    message: str
    deleted_count: int
    plan_metadata: Optional[MonthlyPlanMetadata] = None

class DepartmentalRowCreateRequest(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2050)
    plant: str
    consumable_code: str
    consumable_name: str
    part_number: Optional[str] = "DEPARTMENT_INDENT"
    unit: Optional[str] = "NOS"
    scheduled_consumable_qty: Decimal = Decimal("0.0000")
    remarks: Optional[str] = None


class RequirementDeleteBatchRequest(BaseModel):
    record_ids: list[str]
    month: Optional[int] = None
    year: Optional[int] = None
    reason: Optional[str] = None
