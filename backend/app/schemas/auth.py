from __future__ import annotations

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
    user: CurrentUser | None = None


class CurrentUser(BaseModel):
    """Explicit public identity; ORM credential columns cannot be serialized here."""

    id: UUID
    username: str
    is_super_admin: bool = False
    is_superuser: bool = False
    roles: list[str]
    permissions: list[str]
    plant_ids: list[UUID] = Field(default_factory=list)

    # 40-Point Granular CRUD Permission Matrix
    masters_read: bool = False
    masters_create: bool = False
    masters_update: bool = False
    masters_delete: bool = False

    production_mappings_read: bool = False
    production_mappings_create: bool = False
    production_mappings_update: bool = False
    production_mappings_delete: bool = False

    consumption_norms_read: bool = False
    consumption_norms_create: bool = False
    consumption_norms_update: bool = False
    consumption_norms_delete: bool = False

    prd_planning_read: bool = False
    prd_planning_create: bool = False
    prd_planning_update: bool = False
    prd_planning_delete: bool = False

    requirements_read: bool = False
    requirements_create: bool = False
    requirements_update: bool = False
    requirements_delete: bool = False

    plant_workflow_read: bool = False
    plant_workflow_create: bool = False
    plant_workflow_update: bool = False
    plant_workflow_delete: bool = False

    inventory_read: bool = False
    inventory_create: bool = False
    inventory_update: bool = False
    inventory_delete: bool = False

    purchase_read: bool = False
    purchase_create: bool = False
    purchase_update: bool = False
    purchase_delete: bool = False

    purchase_orders_read: bool = False
    purchase_orders_create: bool = False
    purchase_orders_update: bool = False
    purchase_orders_delete: bool = False

    goods_receipts_read: bool = False
    goods_receipts_create: bool = False
    goods_receipts_update: bool = False
    goods_receipts_delete: bool = False

    # Plant Scope Access
    can_access_plant_1: bool = False
    can_access_plant_2: bool = False
    can_access_plant_3: bool = False
    can_access_plant_4: bool = False
    can_access_plant_5: bool = False

    # Global Module Access & Categorized Alerts
    can_access_dashboard: bool = False
    alert_production: bool = False
    alert_inventory: bool = False
    alert_purchasing: bool = False
    alert_system: bool = False
