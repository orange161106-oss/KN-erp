from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class RequirementWorkspaceRecord(BaseModel):
    id: str
    plant: str
    process: str
    consumable_code: str
    description: str
    unit: str
    required_qty: str
    stock_qty: str
    shortage_qty: str
    po_pending_qty: str
    status: str  # 'Normal', 'Low', 'Critical shortage'
    remarks: str | None = None
    msl: str = "0.0000"
    created_at: datetime | None = None


class RequirementRecalculateResponse(BaseModel):
    message: str
    record_count: int
    critical_shortages: int
    low_stock: int
    records: list[RequirementWorkspaceRecord]

