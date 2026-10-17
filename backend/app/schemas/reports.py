from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlannedVsActualItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consumable_id: UUID
    consumable_code: str
    consumable_name: str
    uom: str
    plant_id: Optional[UUID] = None
    plant_name: Optional[str] = None
    process_id: Optional[UUID] = None
    process_name: Optional[str] = None
    calculated_qty: Decimal
    approved_additions_qty: Decimal
    final_required_qty: Decimal
    actual_consumed_qty: Optional[Decimal] = None
    variance_amount: Optional[Decimal] = None
    variance_percentage: Optional[Decimal] = None
    actual_status: str  # "AVAILABLE", "NO_STOCK_DATA", "PLANT_GRAIN_UNAVAILABLE", "PROCESS_GRAIN_UNAVAILABLE"


class PlannedVsActualTotals(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_calculated_qty: Decimal
    total_approved_additions_qty: Decimal
    total_final_required_qty: Decimal
    total_actual_consumed_qty: Optional[Decimal] = None
    total_variance_amount: Optional[Decimal] = None
    total_variance_percentage: Optional[Decimal] = None


class PlannedVsActualReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str
    planning_version_id: Optional[UUID] = None
    revision_label: Optional[str] = None
    version_status: Optional[str] = None
    items: list[PlannedVsActualItem]
    totals: PlannedVsActualTotals

