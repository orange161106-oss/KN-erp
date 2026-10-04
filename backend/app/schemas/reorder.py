"""Read-only timing assessment inputs; references do not grant approval authority."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.inventory import Input, Key, Timestamp
from app.schemas.projection import ProjectionReport


class TimingPolicy(Input):
    approval_reference: Key
    effective_from: Timestamp
    effective_until: Timestamp
    violation: Literal['BELOW_MSL', 'AT_OR_BELOW_MSL']
    availability_boundary: Literal['BEFORE_CROSSING', 'AT_CROSSING_ALLOWED']

    @model_validator(mode='after')
    def ordered(self):
        if self.effective_until <= self.effective_from:
            raise ValueError('Policy coverage must have a positive interval')
        return self


class WorkingCalendar(Input):
    reference: Key
    approval_reference: Key
    first_date: date
    last_date: date
    working_dates: list[date] = Field(max_length=3661)
    # Explicit supported convention, never inferred from supplier or locale.
    convention: Literal['UTC_DATES_START_EXCLUDED_END_INCLUDED']

    @model_validator(mode='after')
    def coverage(self):
        if not 0 <= (self.last_date - self.first_date).days <= 3660:
            raise ValueError('Calendar coverage must be ordered and at most 3661 dates')
        if len(set(self.working_dates)) != len(self.working_dates):
            raise ValueError('Duplicate working dates')
        if any(not self.first_date <= day <= self.last_date for day in self.working_dates):
            raise ValueError('Working dates must lie within calendar coverage')
        return self


class ReorderLeadTime(Input):
    supplier_id: UUID
    approval_reference: Key
    start_event: Literal['ORDER_INITIATED']
    end_event: Literal['MATERIAL_USABLE']
    days: Annotated[int, Field(strict=True, ge=0, le=3660)]
    basis: Literal['ELAPSED_24_HOUR_DAYS', 'WORKING_DAYS']
    effective_from: Timestamp
    effective_until: Timestamp
    calendar: WorkingCalendar | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.effective_until <= self.effective_from:
            raise ValueError('Lead-time validity must have a positive interval')
        if self.basis == 'ELAPSED_24_HOUR_DAYS' and self.calendar is not None:
            raise ValueError('An elapsed-time duration does not use a working calendar')
        return self


class ReorderRequest(Input):
    consumable_id: UUID
    planning_version_id: UUID
    source_set_id: Key | None = None
    evaluated_at: Timestamp
    cutoff: Timestamp
    policy: TimingPolicy | None = None
    lead_time: ReorderLeadTime | None = None

    @model_validator(mode='after')
    def evaluation_precedes_cutoff(self):
        if self.evaluated_at >= self.cutoff:
            raise ValueError('Evaluation must precede the exclusive cutoff')
        return self


class ReorderLimitation(BaseModel):
    code: str
    message: str


class ReorderReport(BaseModel):
    engine_version: Literal['M4.3_V1'] = 'M4.3_V1'
    assessment_basis: Literal['SUPPLIED_EVIDENCE'] = 'SUPPLIED_EVIDENCE'
    is_live: Literal[False] = False
    status: Literal['DETERMINED', 'INCOMPLETE']
    reorder_required: bool | None = None
    already_breached: bool | None = None
    expected_msl_crossing_at: datetime | None = None
    crossing_time_kind: Literal['EXACT_EVENT', 'AT_OR_BEFORE_EVALUATION'] | None = None
    latest_safe_order_at: datetime | None = None
    latest_safe_order_inclusive: bool | None = None
    earliest_usable_at_if_ordered_now: datetime | None = None
    explanation: str
    limitations: list[ReorderLimitation] = Field(default_factory=list)
    request: ReorderRequest
    projection: ProjectionReport
