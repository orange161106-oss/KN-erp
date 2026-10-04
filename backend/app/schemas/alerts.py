"""Pydantic request/response schemas for M4.4 — Inventory Alerts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AlertType = Literal["BELOW_MSL", "LOW_STOCK", "REORDER_REQUIRED", "PO_DELAY"]
AlertSeverity = Literal["CRITICAL", "WARNING", "INFO"]
AlertStatus = Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED"]


class AcknowledgeAlertRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=2000)


class InventoryAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consumable_id: UUID
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    alert_type: AlertType
    severity: AlertSeverity
    current_stock: Decimal
    threshold_qty: Decimal
    uom: str
    message: str
    status: AlertStatus
    acknowledged_by: Optional[UUID] = None
    acknowledged_by_username: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AlertEvaluationSummaryResponse(BaseModel):
    total_evaluated: int
    alerts_created: int
    alerts_updated: int
    active_critical_count: int
    active_warning_count: int
    active_info_count: int
