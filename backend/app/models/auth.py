from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Table, Text, Uuid, false, func, true, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.security.identity import normalize_username

user_roles = Table(
    "user_roles", Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)

role_permissions = Table(
    "role_permissions", Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    Column("permission_id", Uuid, ForeignKey("permissions.id", ondelete="RESTRICT"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(btrim(username)) AND length(username) > 0", name="normalized_username"),
        Index("uq_users_single_super_admin", "is_super_admin", unique=True,
              postgresql_where=text("is_super_admin = true"), sqlite_where=text("is_super_admin = 1")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    # 40-Point Granular CRUD Permission Matrix (10 Workflow Modules x 4 CRUD Operations)
    # 1. Masters
    masters_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    masters_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    masters_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    masters_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 2. Production Mappings
    production_mappings_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    production_mappings_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    production_mappings_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    production_mappings_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 3. Consumption Norms
    consumption_norms_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    consumption_norms_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    consumption_norms_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    consumption_norms_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 4. PRD / Planning
    prd_planning_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    prd_planning_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    prd_planning_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    prd_planning_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 5. Requirements
    requirements_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    requirements_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    requirements_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    requirements_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 6. Plant Workflow
    plant_workflow_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    plant_workflow_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    plant_workflow_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    plant_workflow_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 7. Inventory
    inventory_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    inventory_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    inventory_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    inventory_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 8. Purchase
    purchase_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 9. Purchase Orders
    purchase_orders_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_orders_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_orders_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    purchase_orders_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # 10. Goods Receipts
    goods_receipts_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    goods_receipts_create: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    goods_receipts_update: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    goods_receipts_delete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # Plant Access Flags (5 Plants)
    can_access_plant_1: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_access_plant_2: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_access_plant_3: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_access_plant_4: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_access_plant_5: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, passive_deletes=True)

    @validates("username")
    def normalize_identity(self, key: str, value: str) -> str:
        normalized = normalize_username(value)
        if not normalized or len(normalized) > 128:
            raise ValueError("Username must contain between 1 and 128 characters")
        return normalized


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, passive_deletes=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text)
