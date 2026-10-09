from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.security.identity import normalize_username


class UserPermissionFlags(BaseModel):
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
    full_name: Optional[str] = Field(default=None, max_length=256)
    employee_id: Optional[str] = Field(default=None, max_length=64)
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    reason: str = Field(default="Employee account provisioned by Super Admin", min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_identity(cls, value):
        return normalize_username(value) if isinstance(value, str) else value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: Optional[SecretStr] = Field(default=None, min_length=6, max_length=1024)
    full_name: Optional[str] = Field(default=None, max_length=256)
    employee_id: Optional[str] = Field(default=None, max_length=64)
    is_active: Optional[bool] = None
    roles: Optional[list[str]] = None
    reason: str = Field(default="Employee account updated by Super Admin", min_length=1, max_length=1024)

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

    # Optional 40 CRUD Permissions
    masters_read: Optional[bool] = None
    masters_create: Optional[bool] = None
    masters_update: Optional[bool] = None
    masters_delete: Optional[bool] = None

    production_mappings_read: Optional[bool] = None
    production_mappings_create: Optional[bool] = None
    production_mappings_update: Optional[bool] = None
    production_mappings_delete: Optional[bool] = None

    consumption_norms_read: Optional[bool] = None
    consumption_norms_create: Optional[bool] = None
    consumption_norms_update: Optional[bool] = None
    consumption_norms_delete: Optional[bool] = None

    prd_planning_read: Optional[bool] = None
    prd_planning_create: Optional[bool] = None
    prd_planning_update: Optional[bool] = None
    prd_planning_delete: Optional[bool] = None

    requirements_read: Optional[bool] = None
    requirements_create: Optional[bool] = None
    requirements_update: Optional[bool] = None
    requirements_delete: Optional[bool] = None

    plant_workflow_read: Optional[bool] = None
    plant_workflow_create: Optional[bool] = None
    plant_workflow_update: Optional[bool] = None
    plant_workflow_delete: Optional[bool] = None

    inventory_read: Optional[bool] = None
    inventory_create: Optional[bool] = None
    inventory_update: Optional[bool] = None
    inventory_delete: Optional[bool] = None

    purchase_read: Optional[bool] = None
    purchase_create: Optional[bool] = None
    purchase_update: Optional[bool] = None
    purchase_delete: Optional[bool] = None

    purchase_orders_read: Optional[bool] = None
    purchase_orders_create: Optional[bool] = None
    purchase_orders_update: Optional[bool] = None
    purchase_orders_delete: Optional[bool] = None

    goods_receipts_read: Optional[bool] = None
    goods_receipts_create: Optional[bool] = None
    goods_receipts_update: Optional[bool] = None
    goods_receipts_delete: Optional[bool] = None

    # Optional Plant Access Flags
    can_access_plant_1: Optional[bool] = None
    can_access_plant_2: Optional[bool] = None
    can_access_plant_3: Optional[bool] = None
    can_access_plant_4: Optional[bool] = None
    can_access_plant_5: Optional[bool] = None


class UserResponse(UserPermissionFlags):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    username: str
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: bool
    is_super_admin: bool
    roles: list[str]

    @field_validator("roles", mode="before")
    @classmethod
    def extract_role_codes(cls, v):
        if isinstance(v, list):
            return [r.code if hasattr(r, "code") else str(r) for r in v]
        return v
