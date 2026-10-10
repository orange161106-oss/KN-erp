from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.inventory import Input, Key, Quantity, Timestamp
from app.schemas.projection import Amount, ProjectionReport
from app.schemas.reorder import ReorderLeadTime, ReorderLimitation


class QuantityConstraint(Input):
    state: Literal['APPLICABLE', 'NOT_APPLICABLE', 'UNKNOWN'] = 'UNKNOWN'
    value: Quantity | None = None
    approval_reference: Key | None = None

    @model_validator(mode='after')
    def evidence(self):
        if self.state == 'APPLICABLE' and self.value is None:
            raise ValueError('Applicable constraints require a quantity')
        if self.state != 'APPLICABLE' and self.value is not None:
            raise ValueError('Only applicable constraints may contain a quantity')
        if self.state != 'UNKNOWN' and self.approval_reference is None:
            raise ValueError('Applicable and not-applicable decisions require a reference')
        return self


class SupplierConstraints(Input):
    moq: QuantityConstraint = Field(default_factory=QuantityConstraint)
    pack_size: QuantityConstraint = Field(default_factory=QuantityConstraint)
    order_multiple: QuantityConstraint = Field(default_factory=QuantityConstraint)
    max_order_quantity: QuantityConstraint = Field(default_factory=QuantityConstraint)
    max_stock_quantity: QuantityConstraint = Field(default_factory=QuantityConstraint)
    other_constraints: Literal['CONFIRMED_NONE', 'UNKNOWN'] = 'UNKNOWN'
    other_constraints_reference: Key | None = None

    @model_validator(mode='after')
    def semantics(self):
        for row in (self.pack_size, self.order_multiple):
            if row.state == 'APPLICABLE' and row.value == 0:
                raise ValueError('Pack size and order multiple must be positive')
        if self.other_constraints == 'CONFIRMED_NONE' and self.other_constraints_reference is None:
            raise ValueError('Confirming no additional supplier constraints requires a reference')
        return self


class TargetStock(Input):
    quantity: Quantity
    approval_reference: Key


class PurchaseRequest(Input):
    consumable_id: UUID
    planning_version_id: UUID
    source_set_id: Key | None = None
    supplier_id: UUID
    unit_id: UUID
    initiated_at: Timestamp
    receipt_at: Timestamp
    evidence_from: Timestamp
    evidence_until: Timestamp
    target: TargetStock | None = None
    constraints: SupplierConstraints = Field(default_factory=SupplierConstraints)
    lead_time: ReorderLeadTime | None = None

    @model_validator(mode='after')
    def times(self):
        if self.receipt_at < self.initiated_at:
            raise ValueError('Receipt cannot precede initiation')
        if self.evidence_until <= self.evidence_from:
            raise ValueError('Evidence interval must have positive coverage')
        return self


class PurchaseStep(BaseModel):
    code: str
    quantity: Amount
    explanation: str


class PurchaseReport(BaseModel):
    engine_version: Literal['M5.1_V1'] = 'M5.1_V1'
    policy_basis: Literal['OWNER_APPROVED_PROVISIONAL'] = 'OWNER_APPROVED_PROVISIONAL'
    assessment_basis: Literal['SUPPLIED_EVIDENCE'] = 'SUPPLIED_EVIDENCE'
    is_live: Literal[False] = False
    status: Literal['RECOMMENDED', 'INCOMPLETE', 'CONFLICT']
    supplier_id: UUID
    supplier_code: str
    supplier_name: str
    final_requirement: Amount | None
    current_stock: Amount | None
    projected_stock_at_receipt: Amount | None
    confirmed_incoming_before_receipt: Amount | None
    msl_at_receipt: Amount | None
    target_stock: Amount | None
    lead_time: ReorderLeadTime | None
    constraints: SupplierConstraints
    raw_quantity: Amount | None = None
    quantity_after_moq: Amount | None = None
    combined_increment: Amount | None = None
    candidate_quantity: Amount | None = None
    recommended_quantity: Amount | None = None
    stock_after_receipt: Amount | None = None
    explanation: str
    limitations: list[ReorderLimitation] = Field(default_factory=list)
    steps: list[PurchaseStep] = Field(default_factory=list)
    request: PurchaseRequest
    projection: ProjectionReport
