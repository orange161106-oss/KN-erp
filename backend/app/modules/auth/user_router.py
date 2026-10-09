from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.auth import Role, User
from app.schemas.auth import CurrentUser
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.security.dependencies import get_current_user
from app.security.passwords import PasswordService

router = APIRouter(prefix="/users", tags=["user-management"])
passwords = PasswordService()

CRUD_MODULES = [
    "masters", "production_mappings", "consumption_norms",
    "prd_planning", "requirements", "plant_workflow",
    "inventory", "purchase", "purchase_orders", "goods_receipts",
]
CRUD_FLAGS = [f"{m}_{op}" for m in CRUD_MODULES for op in ("read", "create", "update", "delete")]
PLANT_FLAGS = [f"can_access_plant_{i}" for i in range(1, 6)]
GLOBAL_FLAGS = ["can_access_dashboard", "can_access_reports"]
ALERT_FLAGS = ["alert_production", "alert_inventory", "alert_purchasing", "alert_system"]
ALL_PERMISSION_FLAGS = CRUD_FLAGS + PLANT_FLAGS + GLOBAL_FLAGS + ALERT_FLAGS


def check_admin_access(current_user: CurrentUser):
    if not current_user.is_super_admin and "ADMIN" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin or Admin access required for user management",
        )


@router.get("", response_model=list[UserResponse])
def list_users(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    check_admin_access(current_user)
    users = session.scalars(select(User).options(selectinload(User.roles))).all()
    
    result = []
    for u in users:
        result.append(UserResponse.model_validate(u))
    return result


@router.post("", response_model=UserResponse)
def create_user(
    data: UserCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    check_admin_access(current_user)
    existing = session.scalar(select(User).where(User.username == data.username))
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    if data.employee_id:
        existing_emp = session.scalar(select(User).where(User.employee_id == data.employee_id))
        if existing_emp:
            raise HTTPException(status_code=400, detail="Employee ID already exists")

    roles = session.scalars(select(Role).where(Role.code.in_(data.roles))).all() if data.roles else []
    p_hash = passwords.hash(data.password.get_secret_value())

    user_kwargs = {
        "username": data.username,
        "full_name": data.full_name,
        "employee_id": data.employee_id,
        "password_hash": p_hash,
        "is_active": True,
        "is_super_admin": False,
        "roles": roles,
    }
    for flag in ALL_PERMISSION_FLAGS:
        user_kwargs[flag] = getattr(data, flag, False)

    user = User(**user_kwargs)
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    data: UserUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    check_admin_access(current_user)
    user = session.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.password:
        user.password_hash = passwords.hash(data.password.get_secret_value())
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.employee_id is not None:
        if data.employee_id != user.employee_id:
            existing_emp = session.scalar(select(User).where(User.employee_id == data.employee_id))
            if existing_emp:
                raise HTTPException(status_code=400, detail="Employee ID already exists")
        user.employee_id = data.employee_id
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.roles is not None:
        roles = session.scalars(select(Role).where(Role.code.in_(data.roles))).all()
        user.roles = roles

    # Update permission flags if specified
    for field in ALL_PERMISSION_FLAGS:
        val = getattr(data, field, None)
        if val is not None:
            setattr(user, field, val)

    session.commit()
    session.refresh(user)

    return UserResponse.model_validate(user)
