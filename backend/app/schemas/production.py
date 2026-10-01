from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

# --- Plant Schemas ---
class PlantBase(BaseModel):
    name: str = Field(..., min_length=1)
    location: Optional[str] = None
    is_active: bool = True

class PlantCreate(PlantBase):
    pass

class PlantUpdate(PlantBase):
    name: Optional[str] = Field(None, min_length=1)

class PlantResponse(PlantBase):
    id: UUID

    class Config:
        from_attributes = True

# --- Process Schemas ---
class ProcessBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_active: bool = True

class ProcessCreate(ProcessBase):
    pass

class ProcessUpdate(ProcessBase):
    name: Optional[str] = Field(None, min_length=1)

class ProcessResponse(ProcessBase):
    id: UUID

    class Config:
        from_attributes = True

# --- Route Schemas ---
class RouteStepBase(BaseModel):
    process_id: UUID
    sequence_order: int

class RouteStepCreate(RouteStepBase):
    pass

class RouteStepResponse(RouteStepBase):
    id: UUID
    route_id: UUID

    class Config:
        from_attributes = True

class RouteBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_active: bool = True

class RouteCreate(RouteBase):
    steps: List[RouteStepCreate] = []

class RouteUpdate(RouteBase):
    name: Optional[str] = Field(None, min_length=1)
    steps: Optional[List[RouteStepCreate]] = None

class RouteResponse(RouteBase):
    id: UUID
    steps: List[RouteStepResponse] = []

    class Config:
        from_attributes = True