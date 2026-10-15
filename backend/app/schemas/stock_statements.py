from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Stock Statement Schemas ───────────────────────────────────────────


class StockStatementLineResponse(BaseModel):
    id: str
    item_id: str
    consumable_id: Optional[str] = None
    item_class: str = "CONSUMABLE"
    store_group: Optional[str] = None
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
    location_text: Optional[str] = None
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
    missing_consumables_count: int = 0
    grand_total_opening_value: Optional[Decimal] = Decimal("0.0000")
    grand_total_receipt_value: Optional[Decimal] = Decimal("0.0000")
    grand_total_issue_value: Optional[Decimal] = Decimal("0.0000")
    grand_total_closing_value: Optional[Decimal] = Decimal("0.0000")
    grand_total_warnings_count: int = 0
    store_groups_found: list[str] = Field(default_factory=list)


class StockStatementResponse(BaseModel):
    metadata: StockStatementMetadata
    summary: StockStatementSummary
    records: list[StockStatementLineResponse]


class MissingConsumableItem(BaseModel):
    item_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit_code: Optional[str] = None
    rate: Optional[Decimal] = None


class MissingConsumablesResponse(BaseModel):
    statement_month: int
    statement_year: int
    count: int
    items: list[MissingConsumableItem]


class PromoteConsumableItem(BaseModel):
    item_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    type_of_material: Optional[str] = None
    unit_code: Optional[str] = "NOS"
    rate: Optional[Decimal] = None
    supplier_id: Optional[UUID] = None


class PromoteConsumablesRequest(BaseModel):
    items: list[PromoteConsumableItem] = Field(min_length=1, max_length=1000)


class PromoteConsumablesResponse(BaseModel):
    promoted_count: int
    promoted_items: list[str]
    message: str


class DemoteConsumableRequest(BaseModel):
    item_id: str
    reason: Optional[str] = None


class DemoteConsumableResponse(BaseModel):
    item_id: str
    demoted: bool
    message: str


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
    location_text: Optional[str] = None
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
    missing_consumables_count: int = 0
    store_groups_found: list[dict[str, Any]] = Field(default_factory=list)
    lines_preview: list[StockStatementLineResponse] = Field(default_factory=list)
    can_confirm: bool = False


class StockStatementConfirmRequest(BaseModel):
    file_token: str
    statement_month: int
    statement_year: int
    replace_confirmed: bool = False


class StockStatementDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class StockStatementDeleteResponse(BaseModel):
    batch_id: UUID
    statement_month: int
    statement_year: int
    deleted_row_count: int
    replayed: bool = False


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


StockQuantityDecimal = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
StockEditDecimal = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=4)]


class StockParameterUpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    description: Optional[str] = Field(default=None, max_length=2000)
    min_stock_level: Optional[StockQuantityDecimal] = None
    max_stock_level: Optional[StockQuantityDecimal] = None
    min_order_qty: Optional[StockQuantityDecimal] = None
    lead_time_days: Optional[Annotated[int, Field(ge=0, strict=True)]] = None


class StockParameterBatchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    batch_id: Optional[UUID] = None
    updates: list[StockParameterUpdateItem] = Field(min_length=1, max_length=5000)


class StockStatementUpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    item_description: Optional[str] = Field(default=None, max_length=2000)
    cust_part_no: Optional[str] = Field(default=None, max_length=128)
    opening_qty: Optional[StockQuantityDecimal] = None
    opening_value: Optional[StockEditDecimal] = None
    receipt_qty: Optional[StockQuantityDecimal] = None
    receipt_value: Optional[StockEditDecimal] = None
    issue_qty: Optional[StockQuantityDecimal] = None
    issue_value: Optional[StockEditDecimal] = None
    closing_qty: Optional[StockQuantityDecimal] = None
    closing_value: Optional[StockEditDecimal] = None


class StockStatementBatchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    batch_id: UUID
    updates: list[StockStatementUpdateItem] = Field(min_length=1, max_length=5000)


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



class StockParameterDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class StockParameterDeleteResponse(BaseModel):
    batch_id: UUID
    month: int
    year: int
    deleted_row_count: int
    replayed: bool = False

