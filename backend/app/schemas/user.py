from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.security.identity import normalize_username


class UserPermissionFlags(BaseModel):
    # Feature Flags
    can_view_master_data: bool = False
    can_edit_master_data: bool = False
    can_view_planning: bool = False
    can_run_calculations: bool = False
    can_confirm_demand: bool = False
    can_approve_extra_demand: bool = False
    can_create_po: bool = False
    can_approve_po: bool = False
    can_upload_grn: bool = False
    can_view_reports: bool = False

    # Plant Access Flags
    can_access_plant_1: bool = False
    can_access_plant_2: bool = False
    can_access_plant_3: bool = False
    can_access_plant_4: bool = False
    can_access_plant_5: bool = False


class UserCreate(UserPermissionFlags):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128, strict=True)
    password: SecretStr = Field(min_length=6, max_length=1024)
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_identity(cls, value):
        return normalize_username(value) if isinstance(value, str) else value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: Optional[SecretStr] = None
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[list[str]] = None

    # Optional Feature Flags
    can_view_master_data: Optional[bool] = None
    can_edit_master_data: Optional[bool] = None
    can_view_planning: Optional[bool] = None
    can_run_calculations: Optional[bool] = None
    can_confirm_demand: Optional[bool] = None
    can_approve_extra_demand: Optional[bool] = None
    can_create_po: Optional[bool] = None
    can_approve_po: Optional[bool] = None
    can_upload_grn: Optional[bool] = None
    can_view_reports: Optional[bool] = None

    # Optional Plant Access Flags
    can_access_plant_1: Optional[bool] = None
    can_access_plant_2: Optional[bool] = None
    can_access_plant_3: Optional[bool] = None
    can_access_plant_4: Optional[bool] = None
    can_access_plant_5: Optional[bool] = None


class UserResponse(UserPermissionFlags):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: bool
    is_super_admin: bool
    roles: list[str]
