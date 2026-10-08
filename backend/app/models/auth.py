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

    # Granular Feature Flags (10 Flags)
    can_view_master_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_edit_master_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_view_planning: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_run_calculations: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_confirm_demand: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_approve_extra_demand: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_create_po: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_approve_po: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_upload_grn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    can_view_reports: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

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
