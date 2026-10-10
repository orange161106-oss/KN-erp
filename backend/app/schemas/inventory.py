from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.domain.inventory_engine.ledger import Movement
from app.schemas.inventory_masters import Reason


def exact_decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Use an exact decimal string or integer")
    if len(str(value)) > 50:
        raise ValueError("Decimal input is too long")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError("Use an exact decimal") from None


def trim(value):
    return value.strip() if isinstance(value, str) else value


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def four_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


Key = Annotated[str, BeforeValidator(trim), Field(strict=True, min_length=1, max_length=192)]
Actor = Annotated[str, BeforeValidator(trim), Field(strict=True, min_length=1, max_length=128)]
Timestamp = Annotated[AwareDatetime, AfterValidator(utc)]
Quantity = Annotated[Decimal, BeforeValidator(exact_decimal), Field(ge=0, lt=Decimal("100000000000000"), max_digits=18, decimal_places=4, allow_inf_nan=False), AfterValidator(four_places)]
PositiveQuantity = Annotated[Decimal, BeforeValidator(exact_decimal), Field(gt=0, lt=Decimal("100000000000000"), max_digits=18, decimal_places=4, allow_inf_nan=False), AfterValidator(four_places)]
Factor = Annotated[Decimal, BeforeValidator(exact_decimal), Field(gt=0, lt=Decimal("1000000000000"), max_digits=24, decimal_places=12, allow_inf_nan=False), AfterValidator(lambda value: value.quantize(Decimal("0.000000000001")))]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class SourceMovement(Input):
    source_event_id: Key
    consumable_id: UUID
    unit_id: UUID
    source_unit_id: UUID
    source_quantity: PositiveQuantity
    conversion_factor: Factor | None = None
    conversion_reference: Key | None = None
    movement: Movement
    event_at: Timestamp
    source_actor: Actor
    condition: Literal["USABLE"]
    source_status: Literal["POSTED"]

    @model_validator(mode="after")
    def validate_conversion(self):
        if self.source_unit_id == self.unit_id:
            if self.conversion_factor is not None and self.conversion_factor != 1:
                raise ValueError("Same-unit conversion factor must be one")
            if self.conversion_reference is not None:
                raise ValueError("Same-unit input needs no conversion reference")
            self.conversion_factor = Decimal("1.000000000000")
        elif self.conversion_factor is None or self.conversion_reference is None:
            raise ValueError("Different units require an approved conversion factor and reference")
        return self


class SourceSnapshot(Input):
    source_snapshot_id: Key
    consumable_id: UUID
    unit_id: UUID
    usable_quantity: Quantity
    as_of: Timestamp
    nonusable_excluded: Literal[True]
    reservations_excluded: Literal[True]

    @field_validator("nonusable_excluded", "reservations_excluded", mode="before")
    @classmethod
    def explicit_exclusions(cls, value):
        if value is not True:
            raise ValueError("The source must explicitly confirm usable-stock exclusions")
        return value


class SourceImport(Input):
    export_id: Key
    generated_at: Timestamp
    import_reason: Reason
    movements: list[SourceMovement] = Field(default_factory=list, max_length=500)
    snapshots: list[SourceSnapshot] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_export(self):
        if not self.movements and not self.snapshots:
            raise ValueError("At least one source record is required")
        for records, field in ((self.movements, "source_event_id"), (self.snapshots, "source_snapshot_id")):
            keys = [getattr(item, field) for item in records]
            if len(set(keys)) != len(keys):
                raise ValueError("Source identifiers must be unique within the export")
        if len({(row.consumable_id, row.as_of) for row in self.snapshots}) != len(self.snapshots):
            raise ValueError("A material can have only one source snapshot at each timestamp")
        if any(row.event_at > self.generated_at for row in self.movements) or any(row.as_of > self.generated_at for row in self.snapshots):
            raise ValueError("Source records cannot occur after export generation")
        return self


class InventoryStatus(BaseModel):
    source: Literal["EXISTING_ERP"] = "EXISTING_ERP"
    mode: Literal["READ_ONLY_REPLICA"] = "READ_ONLY_REPLICA"
    is_live: Literal[False] = False
    import_enabled: bool
    balance_basis: Literal["SOURCE_USABLE_SNAPSHOT"] = "SOURCE_USABLE_SNAPSHOT"
    movement_types: list[Movement] = Field(default_factory=lambda: list(Movement))
    warehouse_posting: Literal[False] = False
    msl_alert_policy: Literal["TBD"] = "TBD"


class ImportResult(BaseModel):
    id: UUID
    export_id: str
    generated_at: datetime
    imported_at: datetime
    imported_by: UUID
    movement_count: int
    snapshot_count: int
    replayed: bool


class Balance(BaseModel):
    consumable_id: UUID
    code: str
    name: str
    is_active: bool
    unit_id: UUID
    unit_code: str
    usable_quantity: Decimal | None
    as_of: datetime | None
    imported_at: datetime | None
    source_export_id: str | None
    availability: Literal["REPORTED", "NOT_IMPORTED"]
    is_live: Literal[False] = False

    @field_serializer("usable_quantity")
    def serialize_quantity(self, value):
        return None if value is None else format(value, ".4f")


class TransactionResponse(BaseModel):
    id: UUID
    source_event_id: str
    consumable_id: UUID
    code: str
    name: str
    unit_id: UUID
    unit_code: str
    source_unit_id: UUID
    source_unit_code: str
    source_quantity: Decimal
    conversion_factor: Decimal
    conversion_reference: str | None
    movement: Movement
    quantity: Decimal
    signed_quantity: Decimal
    event_at: datetime
    source_actor: str
    imported_at: datetime
    imported_by: UUID
    source_export_id: str

    @field_serializer("quantity", "signed_quantity", "source_quantity")
    def serialize_quantity(self, value):
        return format(value, ".4f")
