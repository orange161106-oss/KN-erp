"""Normalized, source-approved M4.2 inputs; no company defaults."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer, model_validator

from app.schemas.inventory import Input, Key, Quantity, Timestamp
from app.schemas.inventory_masters import Reason

Amount = Annotated[Decimal, PlainSerializer(lambda value: format(value, '.4f'), return_type=str)]


class DemandEvent(Input):
    source_id: Key
    at: Timestamp
    quantity: Quantity


class DemandPlan(Input):
    plant_id: UUID
    fulfilled_quantity: Quantity
    reserved_quantity: Quantity
    events: list[DemandEvent] | None = Field(default=None, max_length=500)


class IncomingSupply(Input):
    source_id: Key
    status: Literal['CONFIRMED', 'UNCONFIRMED', 'CANCELLED']
    scheduled_quantity: Quantity
    received_quantity: Quantity
    cancelled_quantity: Quantity
    available_at: Timestamp | None = None

    @model_validator(mode='after')
    def outstanding_is_valid(self):
        if self.received_quantity + self.cancelled_quantity > self.scheduled_quantity:
            raise ValueError('Received and cancelled quantities exceed the source total')
        return self


class MslRevision(Input):
    source_id: Key
    effective_at: Timestamp
    quantity: Quantity
    approval_reference: Key


class LeadTime(Input):
    supplier_id: UUID
    starts_at: Timestamp
    usable_at: Timestamp
    start_event: Key
    calendar_basis: Literal['CALENDAR_DAYS', 'WORKING_DAYS']
    calendar_reference: Key
    approval_reference: Key

    @model_validator(mode='after')
    def ordered_interval(self):
        if self.usable_at < self.starts_at:
            raise ValueError('Usable availability must not precede the lead-time start')
        return self


class ProjectionInputs(Input):
    schema_version: Literal['M4.2_V1'] = 'M4.2_V1'
    source_set_id: Key
    source_reference: Key
    import_reason: Reason
    planning_version_id: UUID
    stock_snapshot_id: UUID
    consumable_id: UUID
    unit_id: UUID
    reconciled_as_of: Timestamp
    coverage_until: Timestamp
    reconciliation_reference: Key | None = None
    demand: list[DemandPlan] | None = Field(default=None, max_length=500)
    incoming: list[IncomingSupply] | None = Field(default=None, max_length=500)
    msl_history: list[MslRevision] = Field(default_factory=list, max_length=200)
    lead_time: LeadTime | None = None

    @model_validator(mode='after')
    def unique_source_and_coverage(self):
        if self.coverage_until <= self.reconciled_as_of:
            raise ValueError('Coverage must end after the stock snapshot')
        plans = self.demand or []
        events = [event for plan in plans for event in (plan.events or [])]
        if len(events) > 500:
            raise ValueError('At most 500 demand events may be imported')
        for values in ([plan.plant_id for plan in plans], [event.source_id for event in events],
                       [row.source_id for row in self.incoming or []],
                       [row.source_id for row in self.msl_history], [row.effective_at for row in self.msl_history]):
            if len(values) != len(set(values)):
                raise ValueError('Duplicate plant, source identity or MSL effective time')
        if any(event.at <= self.reconciled_as_of for event in events):
            raise ValueError('Remaining demand must occur after the reconciled snapshot')
        return self


class Limitation(BaseModel):
    code: str
    message: str
    blocks_projection: bool = True


class TimelineRow(BaseModel):
    at: datetime
    balance_before: Amount
    receipts: Amount
    requirements: Amount
    balance_after: Amount
    msl: Amount | None
    msl_condition: Literal['BELOW_MSL', 'AT_MSL', 'ABOVE_MSL', 'UNKNOWN']
    sources: list[str]


class ExcludedInput(BaseModel):
    source_id: str
    reason: str
    quantity: Amount


class ProjectionResult(BaseModel):
    status: Literal['COMPLETE', 'INCOMPLETE']
    cutoff: datetime
    opening_stock: Amount | None
    projected_stock: Amount | None = None
    current_msl: Amount | None = None
    current_msl_condition: Literal['BELOW_MSL', 'AT_MSL', 'ABOVE_MSL', 'UNKNOWN'] = 'UNKNOWN'
    projected_msl: Amount | None = None
    projected_msl_condition: Literal['BELOW_MSL', 'AT_MSL', 'ABOVE_MSL', 'UNKNOWN'] = 'UNKNOWN'
    first_future_breach_at: datetime | None = None
    future_breach: bool | None = None
    lead_time_balance: Amount | None = None
    timeline: list[TimelineRow] = Field(default_factory=list)
    excluded: list[ExcludedInput] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)


class RequirementTotal(BaseModel):
    plant_id: UUID
    final_quantity: Amount
    is_fully_confirmed: bool


class ProjectionReport(ProjectionResult):
    engine_version: Literal['M4.2_V1'] = 'M4.2_V1'
    scope: Literal['SELECTED_PLANNING_VERSION'] = 'SELECTED_PLANNING_VERSION'
    consumable_id: UUID
    unit_id: UUID
    planning_version_id: UUID
    planning_period: str
    stock_snapshot_id: UUID | None
    stock_as_of: datetime | None
    source_set_id: str | None
    requirement_fingerprint: str
    requirement_totals: list[RequirementTotal]
    inputs: ProjectionInputs | None
    is_live: Literal[False] = False
    formula: str = 'P(t) = usable snapshot + outstanding confirmed receipts (t0 < time < t) - reconciled remaining demand (t0 < time < t)'


class ProjectionImportResult(BaseModel):
    id: UUID
    source_set_id: str
    replayed: bool
    imported_at: datetime


class ProjectionCapability(BaseModel):
    import_enabled: bool
    requirement_timing: Literal['SOURCE_SCHEDULE_REQUIRED'] = 'SOURCE_SCHEDULE_REQUIRED'
    local_msl_editing: Literal[False] = False
    automatically_spreads_monthly_demand: Literal[False] = False
