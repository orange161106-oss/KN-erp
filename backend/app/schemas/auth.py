from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.security.identity import normalize_username


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(min_length=1, max_length=128, strict=True)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_identity(cls, value):
        return normalize_username(value) if isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    """Explicit public identity; ORM credential columns cannot be serialized here."""

    id: UUID
    username: str
    is_super_admin: bool = False
    roles: list[str]
    permissions: list[str]
    plant_ids: list[UUID] = Field(default_factory=list)

    # Granular Feature Access
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

    # Plant Scope Access
    can_access_plant_1: bool = False
    can_access_plant_2: bool = False
    can_access_plant_3: bool = False
    can_access_plant_4: bool = False
    can_access_plant_5: bool = False
