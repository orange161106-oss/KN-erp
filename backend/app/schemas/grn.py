from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.inventory import Actor, Input, Key, PositiveQuantity, Quantity, SourceImport, Timestamp
from app.schemas.inventory_masters import Reason
from app.domain.inventory_engine.ledger import stock_quantity


class ReceiptLine(Input):
    source_line_id: Key
    purchase_order_item_id: UUID
    consumable_id: UUID
    unit_id: UUID
    received_quantity: PositiveQuantity
    accepted_quantity: Quantity
    rejected_quantity: Quantity
    source_event_id: Key | None = None

    @model_validator(mode='after')
    def quantities(self):
        if self.received_quantity != self.accepted_quantity + self.rejected_quantity:
            raise ValueError('Received quantity must equal accepted plus rejected; unresolved inspection is not supported')
        if bool(self.accepted_quantity) != (self.source_event_id is not None):
            raise ValueError('Only positive accepted quantity must have a source stock event')
        return self


class GRNImport(Input):
    source_grn_id: Key
    purchase_order_id: UUID
    supplier_id: UUID
    event_at: Timestamp
    source_actor: Actor
    source_status: Literal['POSTED']
    reason: Reason
    items: list[ReceiptLine] = Field(min_length=1, max_length=100)
    stock: SourceImport

    @model_validator(mode='after')
    def source_links(self):
        for field in ('source_line_id', 'purchase_order_item_id'):
            if len({getattr(row, field) for row in self.items}) != len(self.items):
                raise ValueError('Duplicate GRN line or PO item')
        events = [row.source_event_id for row in self.items if row.source_event_id is not None]
        movements = {row.source_event_id: row for row in self.stock.movements}
        if len(set(events)) != len(events) or set(events) != set(movements):
            raise ValueError('Stock events must match accepted GRN lines exactly')
        materials = {row.consumable_id for row in self.items}
        snapshots = {row.consumable_id: row for row in self.stock.snapshots}
        if set(snapshots) != materials or len(snapshots) != len(self.stock.snapshots):
            raise ValueError('Provide one authoritative post-receipt usable snapshot per GRN material')
        if self.event_at > self.stock.generated_at:
            raise ValueError('GRN event cannot follow export generation')
        for row in self.items:
            snapshot = snapshots[row.consumable_id]
            if snapshot.unit_id != row.unit_id or snapshot.as_of < self.event_at:
                raise ValueError('Snapshot unit/time must cover the GRN receipt')
            if row.source_event_id is not None:
                movement = movements[row.source_event_id]
                # The adapter normalizes GRN quantities into the PO stock unit.
                if (movement.movement.value != 'RECEIPT' or movement.consumable_id != row.consumable_id
                        or movement.unit_id != row.unit_id or movement.event_at != self.event_at
                        or movement.source_actor != self.source_actor
                        or stock_quantity(movement.source_quantity, movement.conversion_factor) != row.accepted_quantity):
                    raise ValueError('Receipt event must match accepted material, quantity, unit, actor and time')
        return self


class ReceiptLineResponse(BaseModel):
    id: UUID
    source_line_id: str
    purchase_order_item_id: UUID
    consumable_id: UUID
    unit_id: UUID
    consumable_code: str
    consumable_name: str
    unit_code: str
    received_quantity: Quantity
    accepted_quantity: Quantity
    rejected_quantity: Quantity
    stock_transaction_id: UUID | None
    stock_snapshot_id: UUID

    model_config = {'from_attributes': True}


class GRNResponse(BaseModel):
    id: UUID
    source_grn_id: str
    purchase_order_id: UUID
    po_number: str
    supplier_name: str
    supplier_id: UUID
    stock_batch_id: UUID
    event_at: datetime
    source_actor: str
    imported_by: UUID
    imported_at: datetime
    reason: str
    items: list[ReceiptLineResponse]
    source: Literal['EXISTING_ERP'] = 'EXISTING_ERP'
    is_live: Literal[False] = False
    replayed: bool = False
