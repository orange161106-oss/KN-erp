from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer, model_validator

from app.schemas.inventory import Input, Key, PositiveQuantity, Quantity, Timestamp
from app.schemas.inventory_masters import Reason
from app.schemas.projection import Amount
from app.schemas.purchase_recommendation import PurchaseRequest

Money = Annotated[Decimal, PlainSerializer(lambda value: format(value, 'f'), return_type=str)]


class DemandSubmission(Input):
    submission_key: Key
    reason: Reason
    recommendation: PurchaseRequest


class DemandSubmissionResponse(BaseModel):
    approval_id: UUID
    evidence_id: UUID
    replayed: bool


class PriceTerms(Input):
    unit_rate: Quantity
    currency: Annotated[str, Field(strict=True, pattern=r'^[A-Z]{3}$')]
    decimal_places: Annotated[int, Field(strict=True, ge=0, le=4)]
    rounding: Literal['HALF_UP', 'HALF_EVEN', 'DOWN']
    approval_reference: Key


class OrderLine(Input):
    approval_id: UUID
    ordered_quantity: PositiveQuantity
    expected_delivery: Timestamp
    pricing: PriceTerms | None = None


class OrderCreate(Input):
    creation_key: Key
    supplier_id: UUID
    po_date: date
    reason: Reason
    items: list[OrderLine] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def distinct(self):
        if len({row.approval_id for row in self.items}) != len(self.items):
            raise ValueError('Use each approved recommendation at most once per PO')
        if any(row.expected_delivery.date() < self.po_date for row in self.items):
            raise ValueError('Expected delivery cannot precede the PO date')
        prices = [row.pricing for row in self.items if row.pricing]
        if len({(p.currency, p.decimal_places, p.rounding) for p in prices}) > 1:
            raise ValueError('Priced lines in one PO must share currency and rounding policy')
        return self


class OrderAction(Input):
    reason: Reason


class OrderItemResponse(BaseModel):
    id: UUID
    approval_id: UUID
    evidence_id: UUID
    consumable_id: UUID
    planning_version_id: UUID
    code: str
    name: str
    unit_id: UUID
    unit_code: str
    ordered_quantity: Amount
    pending_quantity: Amount | None
    received_quantity: Amount
    accepted_quantity: Amount
    rejected_quantity: Amount
    expected_delivery: datetime
    pricing: PriceTerms | None
    line_value: Money | None
    approval_snapshot: dict
    recommendation_evidence: dict


class OrderResponse(BaseModel):
    id: UUID
    po_number: str
    supplier_id: UUID
    supplier_code: str
    supplier_name: str
    po_date: date
    status: Literal['DRAFT', 'ISSUED', 'CANCELLED']
    created_at: datetime
    issued_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemResponse]
    currency: str | None
    total_value: Money | None
    pending_basis: Literal['NOT_COMMITTED', 'IMPORTED_ACCEPTED_GRNS', 'CANCELLED_DRAFT']
    fulfilment_status: Literal['NOT_APPLICABLE', 'NOT_RECEIVED', 'PARTIAL', 'COMPLETE']
    fulfilment_is_live: Literal[False] = False
    replayed: bool = False
    history: list[dict]


class EligibleDemand(BaseModel):
    approval_id: UUID
    supplier_id: UUID
    supplier_name: str
    consumable_code: str
    consumable_name: str
    unit_code: str
    approved_quantity: Amount | None
    remaining_quantity: Amount | None
    eligible: bool
    limitation: str | None
