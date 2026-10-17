from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.inventory import Timestamp, Quantity
from app.schemas.inventory_masters import Page


class ReportOption(BaseModel):
    id: UUID
    label: str
    detail: str | None = None


class PurchaseFlowItem(BaseModel):
    approval_id: UUID
    evidence_id: UUID | None
    submitted_at: datetime | None
    supplier_id: UUID
    supplier_code: str
    supplier_name: str
    consumable_id: UUID
    consumable_code: str
    consumable_name: str
    unit_code: str
    planning_version_id: UUID | None
    recommendation_status: Literal['RECOMMENDED', 'INCOMPLETE', 'CONFLICT', 'NO_SAVED_EVIDENCE', 'INVALID_SAVED_EVIDENCE']
    recommended_quantity: Quantity | None
    approval_status: str
    reviewed_at: datetime | None
    approved_quantity: Quantity | None
    draft_allocated_quantity: Quantity
    issued_ordered_quantity: Quantity
    cancelled_order_quantity: Quantity
    received_quantity: Quantity
    accepted_quantity: Quantity
    rejected_quantity: Quantity
    pending_quantity: Quantity
    pending_basis: Literal['IMPORTED_ACCEPTED_GRNS', 'NOT_ISSUED']
    is_live: Literal[False] = False


class PurchaseFlowPage(BaseModel):
    items: list[PurchaseFlowItem]
    total: int
    limit: int
    offset: int
    pending_only: bool
    submitted_from: datetime | None
    submitted_until: datetime | None
    po_status: Literal['DRAFT', 'ISSUED', 'CANCELLED'] | None
    po_date_from: date | None
    po_date_until: date | None
    receipt_coverage: Literal['IMPORTED_NONLIVE'] = 'IMPORTED_NONLIVE'
    is_live: Literal[False] = False


class GRNReportItem(BaseModel):
    grn_id: UUID
    source_grn_id: str
    purchase_order_id: UUID
    po_number: str
    supplier_id: UUID
    supplier_code: str
    supplier_name: str
    consumable_id: UUID
    consumable_code: str
    consumable_name: str
    unit_id: UUID
    unit_code: str
    source_line_id: str
    event_at: datetime
    imported_at: datetime
    received_quantity: Quantity
    accepted_quantity: Quantity
    rejected_quantity: Quantity
    stock_transaction_id: UUID | None
    stock_snapshot_id: UUID
    is_live: Literal[False] = False


class GRNReportPage(BaseModel):
    items: list[GRNReportItem]
    total: int
    limit: int
    offset: int
    event_from: datetime | None
    event_until: datetime | None
    source: Literal['EXISTING_ERP'] = 'EXISTING_ERP'
    is_live: Literal[False] = False
