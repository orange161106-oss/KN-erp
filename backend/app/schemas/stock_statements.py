from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Stock Statement Schemas ───────────────────────────────────────────


class StockStatementLineResponse(BaseModel):
    id: str
    item_id: str
    consumable_id: Optional[str] = None
    item_class: str = "CONSUMABLE"
    item_description: Optional[str] = None
    cust_part_no: Optional[str] = None
    unit: Optional[str] = None
    opening_qty: Optional[Decimal] = None
    opening_value: Optional[Decimal] = None
    receipt_qty: Optional[Decimal] = None
    receipt_value: Optional[Decimal] = None
    issue_qty: Optional[Decimal] = None
    issue_value: Optional[Decimal] = None
    closing_qty: Optional[Decimal] = None
    closing_value: Optional[Decimal] = None
    source_row: int
    warning_codes: list[str] = Field(default_factory=list)
    diff_closing_qty: Optional[Decimal] = None
    diff_closing_value: Optional[Decimal] = None


class StockStatementSummary(BaseModel):
    item_count: int = 0
    consumable_count: int = 0
    product_or_other_count: int = 0
    unknown_count: int = 0
    total_opening_value: Decimal = Decimal("0.0000")
    total_receipt_value: Decimal = Decimal("0.0000")
    total_issue_value: Decimal = Decimal("0.0000")
    total_closing_value: Decimal = Decimal("0.0000")
    warning_rows_count: int = 0


class StockStatementMetadata(BaseModel):
    has_statement: bool
    batch_id: Optional[str] = None
    statement_month: int
    statement_year: int
    statement_date: str  # YYYY-MM-DD
    source_filename: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None
    row_count: int = 0
    warning_count: int = 0
    consumable_count: int = 0
    product_or_other_count: int = 0
    unknown_count: int = 0


class StockStatementResponse(BaseModel):
    metadata: StockStatementMetadata
    summary: StockStatementSummary
    records: list[StockStatementLineResponse]


class RowIssue(BaseModel):
    row: int
    column: str
    description: str
    severity: str = "ERROR"  # ERROR or WARNING
    code: Optional[str] = None
    item_id: Optional[str] = None
    item_class: Optional[str] = None
    suggested_action: Optional[str] = None
    row_content: Optional[dict[str, Any]] = None
    conflicting_row: Optional[int] = None
    conflicting_row_content: Optional[dict[str, Any]] = None
    possible_matches: list[dict[str, Any]] = Field(default_factory=list)
    resolvable: bool = False
    allowed_actions: list[str] = Field(default_factory=list)
    default_action: Optional[str] = None


class GroupedWarningResponse(BaseModel):
    code: str
    description: str
    count: int
    sample_rows: list[int] = Field(default_factory=list)


class StockStatementPreviewResponse(BaseModel):
    statement_month: int
    statement_year: int
    statement_date: str
    detected_title: Optional[str] = None
    source_filename: str
    file_token: str
    is_existing_batch: bool = False
    existing_batch_filename: Optional[str] = None
    existing_batch_date: Optional[datetime] = None
    errors: list[RowIssue] = Field(default_factory=list)
    warnings: list[RowIssue] = Field(default_factory=list)
    grouped_warnings: list[GroupedWarningResponse] = Field(default_factory=list)
    unknown_items: list[str] = Field(default_factory=list)
    total_rows: int = 0
    warning_count: int = 0
    consumable_count: int = 0
    product_or_other_count: int = 0
    unknown_count: int = 0
    lines_preview: list[StockStatementLineResponse] = Field(default_factory=list)
    can_confirm: bool = False


class StockStatementConfirmRequest(BaseModel):
    file_token: str
    statement_month: int
    statement_year: int
    replace_confirmed: bool = False


class StockStatementHistoryItem(BaseModel):
    batch_id: str
    statement_month: int
    statement_year: int
    statement_date: str
    source_filename: str
    status: str
    row_count: int
    warning_count: int
    uploaded_at: datetime
    uploaded_by_name: Optional[str] = None


# ── Stock Management Schemas ──────────────────────────────────────────


class RowResolutionInput(BaseModel):
    row: int
    action: str  # "SKIP_ROW", "SKIP_DUPLICATE", "KEEP_FIRST", "KEEP_SECOND", "KEEP_BOTH", "ASSIGN_ITEM_ID"
    assigned_item_id: Optional[str] = None
    note: Optional[str] = None


class StockParameterRecord(BaseModel):
    id: str
    item_id: str
    consumable_id: Optional[str] = None
    category: Optional[str] = None
    type_of_material: Optional[str] = None
    description: Optional[str] = None
    min_stock_level: Optional[Decimal] = None
    max_stock_level: Optional[Decimal] = None
    min_order_qty: Optional[Decimal] = None
    lead_time_days: Optional[int] = None
    edited_after_import: bool = False
    source_row: int = 0
    resolution_applied: Optional[str] = "NONE"
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    category_count: int = 1
    has_conflicting_limits: bool = False


class StockManagementSummary(BaseModel):
    item_count: int = 0
    missing_limits_count: int = 0
    min_exceeds_max_count: int = 0
    multi_category_items_count: int = 0
    ambiguous_limits_items_count: int = 0
    skipped_rows_count: int = 0
    resolved_rows_count: int = 0


class StockManagementMetadata(BaseModel):
    has_parameters: bool
    batch_id: Optional[str] = None
    month: int
    year: int
    effective_date: str
    source_filename: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None
    row_count: int = 0
    skipped_rows: list[dict[str, Any]] = Field(default_factory=list)
    resolutions_applied: list[dict[str, Any]] = Field(default_factory=list)


class StockManagementResponse(BaseModel):
    metadata: StockManagementMetadata
    summary: StockManagementSummary
    records: list[StockParameterRecord]


class ComparisonSummary(BaseModel):
    has_previous_month: bool = False
    previous_month_label: Optional[str] = None
    new_items_count: int = 0
    removed_items_count: int = 0
    changed_items_count: int = 0
    changes_sample: list[dict[str, Any]] = Field(default_factory=list)


class StockParameterPreviewResponse(BaseModel):
    month: int
    year: int
    effective_date: str
    detected_title: Optional[str] = None
    source_filename: str
    file_token: str
    uniqueness_mode: str = "ITEM_AND_CATEGORY"
    is_existing_batch: bool = False
    existing_batch_filename: Optional[str] = None
    errors: list[RowIssue] = Field(default_factory=list)
    warnings: list[RowIssue] = Field(default_factory=list)
    issue_counts_by_code: dict[str, int] = Field(default_factory=dict)
    unknown_items: list[str] = Field(default_factory=list)
    consumable_options: list[dict[str, Any]] = Field(default_factory=list)
    comparison: ComparisonSummary
    total_rows: int = 0
    unresolved_blocking_count: int = 0
    lines_preview: list[StockParameterRecord] = Field(default_factory=list)
    can_confirm: bool = False


class StockParameterConfirmRequest(BaseModel):
    file_token: str
    month: int
    year: int
    replace_confirmed: bool = False
    resolutions: list[RowResolutionInput] = Field(default_factory=list)


class StockParameterUpdateItem(BaseModel):
    id: str
    min_stock_level: Optional[Decimal] = None
    max_stock_level: Optional[Decimal] = None
    min_order_qty: Optional[Decimal] = None
    lead_time_days: Optional[int] = None


class StockParameterBatchUpdateRequest(BaseModel):
    month: int
    year: int
    updates: list[StockParameterUpdateItem]


class StockParameterHistoryItem(BaseModel):
    batch_id: str
    month: int
    year: int
    effective_date: str
    source_filename: str
    status: str
    row_count: int
    uploaded_at: datetime
    uploaded_by_name: Optional[str] = None


