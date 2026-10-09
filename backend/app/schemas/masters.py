from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    uom: str = Field("PCS", max_length=16)
    description: Optional[str] = None
    item_id: Optional[str] = Field(default=None, max_length=128)
    part_number: Optional[str] = Field(default=None, max_length=128)


class ProductCreate(ProductBase):
    pass


class ProductSourceCandidate(BaseModel):
    item_id: str
    part_number: str
    code: str
    name: str
    uom: str
    source_rows: list[int]
    description_options: list[str] = Field(default_factory=list)
    unit_options: list[str] = Field(default_factory=list)


class ProductSourcePreview(BaseModel):
    filename: str
    sheet: str
    sha256: str
    products: list[ProductSourceCandidate]
    message: str


class ProductBulkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    products: list[ProductCreate] = Field(min_length=1, max_length=1000)
    source_reference: str = Field(min_length=1, max_length=1024)


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime


class CustomerBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)


class CustomerCreate(CustomerBase):
    pass


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
