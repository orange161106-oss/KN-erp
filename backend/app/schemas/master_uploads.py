from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["consumables", "sales_parts", "assemble"]


class ExistingMasterView(BaseModel):
    category: Category
    row_count: int
    review_token: str
    records: list[dict[str, str | None]]


class ExistingMasterDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_required(cls, reason):
        if not reason.strip():
            raise ValueError("Enter a deletion reason")
        return reason.strip()


class MasterPeriodView(BaseModel):
    batch_id: UUID | None = None
    version: int = 0
    category: Category
    month: int
    year: int
    filename: str | None = None
    updated_at: datetime | None = None
    records: list[dict[str, str | None]] = Field(default_factory=list)


class MasterRowEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    changes: dict[str, str | None] = Field(min_length=1, max_length=10)


class MasterPeriodSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    version: int = Field(ge=1)
    updates: list[MasterRowEdit] = Field(min_length=1, max_length=10000)

    @field_validator("updates")
    @classmethod
    def distinct_rows(cls, rows):
        if len({row.id for row in rows}) != len(rows):
            raise ValueError("Save each row only once")
        return rows


class MasterPeriodDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_required(cls, reason):
        if not reason.strip():
            raise ValueError("Enter a deletion reason")
        return reason.strip()


class MasterCatalogView(BaseModel):
    category: Category
    review_token: str
    row_count: int
    records: list[dict[str, str | None]]
    filename: str | None = None
    report: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[dict[str, str]] = Field(default_factory=list)


class MasterCatalogSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    updates: list[MasterRowEdit] = Field(default_factory=list, max_length=10000)

    @field_validator("updates")
    @classmethod
    def distinct_rows(cls, rows):
        if len({row.id for row in rows}) != len(rows):
            raise ValueError("Save each row only once")
        return rows
