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
        result.append(
            UserResponse(
                id=u.id,
                username=u.username,
                full_name=u.full_name,
                employee_id=u.employee_id,
                is_active=u.is_active,
                is_super_admin=u.is_super_admin,
                roles=[r.code for r in u.roles],
                can_view_master_data=u.can_view_master_data,
                can_edit_master_data=u.can_edit_master_data,
                can_view_planning=u.can_view_planning,
                can_run_calculations=u.can_run_calculations,
                can_confirm_demand=u.can_confirm_demand,
                can_approve_extra_demand=u.can_approve_extra_demand,
                can_create_po=u.can_create_po,
                can_approve_po=u.can_approve_po,
                can_upload_grn=u.can_upload_grn,
                can_view_reports=u.can_view_reports,
                can_access_plant_1=u.can_access_plant_1,
                can_access_plant_2=u.can_access_plant_2,
                can_access_plant_3=u.can_access_plant_3,
                can_access_plant_4=u.can_access_plant_4,
                can_access_plant_5=u.can_access_plant_5,
            )
        )
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

    user = User(
        username=data.username,
        full_name=data.full_name,
        employee_id=data.employee_id,
        password_hash=p_hash,
        is_active=True,
        is_super_admin=False,
        roles=roles,
        can_view_master_data=data.can_view_master_data,
        can_edit_master_data=data.can_edit_master_data,
        can_view_planning=data.can_view_planning,
        can_run_calculations=data.can_run_calculations,
        can_confirm_demand=data.can_confirm_demand,
        can_approve_extra_demand=data.can_approve_extra_demand,
        can_create_po=data.can_create_po,
        can_approve_po=data.can_approve_po,
        can_upload_grn=data.can_upload_grn,
        can_view_reports=data.can_view_reports,
        can_access_plant_1=data.can_access_plant_1,
        can_access_plant_2=data.can_access_plant_2,
        can_access_plant_3=data.can_access_plant_3,
        can_access_plant_4=data.can_access_plant_4,
        can_access_plant_5=data.can_access_plant_5,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        employee_id=user.employee_id,
        is_active=user.is_active,
        is_super_admin=user.is_super_admin,
        roles=[r.code for r in user.roles],
        can_view_master_data=user.can_view_master_data,
        can_edit_master_data=user.can_edit_master_data,
        can_view_planning=user.can_view_planning,
        can_run_calculations=user.can_run_calculations,
        can_confirm_demand=user.can_confirm_demand,
        can_approve_extra_demand=user.can_approve_extra_demand,
        can_create_po=user.can_create_po,
        can_approve_po=user.can_approve_po,
        can_upload_grn=user.can_upload_grn,
        can_view_reports=user.can_view_reports,
        can_access_plant_1=user.can_access_plant_1,
        can_access_plant_2=user.can_access_plant_2,
        can_access_plant_3=user.can_access_plant_3,
        can_access_plant_4=user.can_access_plant_4,
        can_access_plant_5=user.can_access_plant_5,
    )


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
    flag_fields = [
        "can_view_master_data", "can_edit_master_data", "can_view_planning", "can_run_calculations",
        "can_confirm_demand", "can_approve_extra_demand", "can_create_po", "can_approve_po",
        "can_upload_grn", "can_view_reports", "can_access_plant_1", "can_access_plant_2",
        "can_access_plant_3", "can_access_plant_4", "can_access_plant_5",
    ]
    for field in flag_fields:
        val = getattr(data, field)
        if val is not None:
            setattr(user, field, val)

    session.commit()
    session.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        employee_id=user.employee_id,
        is_active=user.is_active,
        is_super_admin=user.is_super_admin,
        roles=[r.code for r in user.roles],
        can_view_master_data=user.can_view_master_data,
        can_edit_master_data=user.can_edit_master_data,
        can_view_planning=user.can_view_planning,
        can_run_calculations=user.can_run_calculations,
        can_confirm_demand=user.can_confirm_demand,
        can_approve_extra_demand=user.can_approve_extra_demand,
        can_create_po=user.can_create_po,
        can_approve_po=user.can_approve_po,
        can_upload_grn=user.can_upload_grn,
        can_view_reports=user.can_view_reports,
        can_access_plant_1=user.can_access_plant_1,
        can_access_plant_2=user.can_access_plant_2,
        can_access_plant_3=user.can_access_plant_3,
        can_access_plant_4=user.can_access_plant_4,
        can_access_plant_5=user.can_access_plant_5,
    )
