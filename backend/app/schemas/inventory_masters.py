from datetime import datetime
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def trim(value):
    return value.strip() if isinstance(value, str) else value


def code(value):
    return value.strip().upper() if isinstance(value, str) else value


def nonblank(value: str) -> str:
    if not value:
        raise ValueError("Value cannot be blank")
    return value


Name = Annotated[str, BeforeValidator(trim), Field(strict=True, min_length=1, max_length=255), AfterValidator(nonblank)]
Code = Annotated[str, BeforeValidator(code), Field(strict=True, min_length=1, max_length=64), AfterValidator(nonblank)]
UnitCode = Annotated[str, BeforeValidator(code), Field(strict=True, min_length=1, max_length=16), AfterValidator(nonblank)]
Reason = Annotated[str, BeforeValidator(trim), Field(strict=True, min_length=1, max_length=1000), AfterValidator(nonblank)]
Description = Annotated[str, BeforeValidator(trim), Field(strict=True, max_length=10000)]


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    change_reason: Reason


class Update(Mutation):
    @model_validator(mode="after")
    def validate_changes(self):
        fields = self.model_fields_set - {"change_reason"}
        if not fields:
            raise ValueError("At least one changed field is required")
        if any(getattr(self, field) is None for field in fields - {"description"}):
            raise ValueError("Required fields cannot be null")
        return self


class UnitCreate(Mutation):
    code: UnitCode
    name: Name


class UnitUpdate(Update):
    code: UnitCode | None = None
    name: Name | None = None


class ConsumableCreate(Mutation):
    code: Code
    name: Name
    description: Description | None = None
    unit_id: UUID


class ConsumableUpdate(Update):
    code: Code | None = None
    name: Name | None = None
    description: Description | None = None
    unit_id: UUID | None = None


class SupplierCreate(Mutation):
    code: Code
    name: Name


class SupplierUpdate(Update):
    code: Code | None = None
    name: Name | None = None


class SupplierConsumableCreate(Mutation):
    supplier_id: UUID
    consumable_id: UUID


class SupplierConsumableUpdate(Update):
    supplier_id: UUID | None = None
    consumable_id: UUID | None = None


class StatusChange(Mutation):
    is_active: bool = Field(strict=True)


class MasterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UnitResponse(MasterResponse):
    code: str
    name: str


class ConsumableResponse(UnitResponse):
    description: str | None
    unit_id: UUID


class SupplierResponse(UnitResponse):
    pass


class SupplierConsumableResponse(MasterResponse):
    supplier_id: UUID
    consumable_id: UUID


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
