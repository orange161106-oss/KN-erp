"""Pydantic schemas for M6.3 — Executive Management Dashboard."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PipelineSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_calculated_quantity: Decimal
    total_approved_additions: Decimal
    total_final_requirement: Decimal
    total_recommended_quantity: Decimal
    total_approved_purchase_quantity: Decimal
    total_ordered_quantity: Decimal
    total_accepted_grn_quantity: Decimal


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    active_critical_alerts: int
    active_warning_alerts: int
    pending_purchase_approvals: int
    pending_plant_adjustments: int
    issued_pending_pos: int
    total_active_consumables: int
    pipeline_summary: PipelineSummarySchema
    as_of: datetime
