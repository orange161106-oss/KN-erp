"""Account administration with immutable Super Admin and atomic audit records."""
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.auth import Role, User
from app.schemas.auth import CurrentUser
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.security.passwords import PasswordService

ROLE_CODES = frozenset({"ADMIN", "PLANNER", "PLANT_INCHARGE", "STORE", "PURCHASE", "APPROVER", "MANAGEMENT"})
FLAG_FIELDS = tuple(name for name in UserCreate.model_fields if name.startswith("can_"))


def require_super_admin(actor: CurrentUser) -> None:
    if not actor.is_super_admin:
        raise ApplicationError("PERMISSION_DENIED", "Only Super Admin can manage employee accounts.", 403)


def response(user: User) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, full_name=user.full_name,
        employee_id=user.employee_id, is_active=user.is_active, is_super_admin=user.is_super_admin,
        is_superuser=user.is_super_admin,
        roles=sorted(r.code for r in user.roles), **{f: getattr(user, f) for f in FLAG_FIELDS})


def _roles(session: Session, codes: list[str]) -> list[Role]:
    if set(codes) - ROLE_CODES:
        raise ApplicationError("INVALID_ROLE", "Select a supported base role.", 422)
    roles = list(session.scalars(select(Role).where(Role.code.in_(codes))))
    # Templates identify employees; they do not fabricate operation grants.
    for code in sorted(set(codes) - {r.code for r in roles}):
        role = Role(code=code, name=code.replace("_", " ").title())
        session.add(role)
        roles.append(role)
    return roles


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApplicationError("USER_CONFLICT", "Username or employee ID already exists.", 409) from None


def list_users(session: Session, actor: CurrentUser) -> list[UserResponse]:
    require_super_admin(actor)
    return [response(u) for u in session.scalars(select(User).where(User.is_super_admin.is_(False))
        .options(selectinload(User.roles)).order_by(User.username))]


def create_user(session: Session, data: UserCreate, actor: CurrentUser) -> UserResponse:
    require_super_admin(actor)
    if not data.reason.strip():
        raise ApplicationError("REASON_REQUIRED", "An account-change reason is required.", 422)
    user = User(id=uuid4(), **data.model_dump(exclude={"password", "roles", "reason"}),
        password_hash=PasswordService().hash(data.password.get_secret_value()),
        is_super_admin=False, roles=_roles(session, data.roles))
    session.add(user)
    session.add(AuditLog(actor_id=actor.id, action="CREATE", entity_type="user", entity_id=user.id,
        old_values=None, new_values=response(user).model_dump(mode="json"), reason=data.reason.strip()))
    _commit(session)
    return response(user)


def update_user(session: Session, identity: UUID, data: UserUpdate, actor: CurrentUser) -> UserResponse:
    require_super_admin(actor)
    user = session.scalar(select(User).where(User.id == identity).options(selectinload(User.roles)).with_for_update())
    if user is None:
        raise ApplicationError("USER_NOT_FOUND", "Employee account not found.", 404)
    if user.is_super_admin:
        raise ApplicationError("SUPER_ADMIN_IMMUTABLE", "Super Admin cannot be changed through employee management.", 403)
    if not data.reason.strip():
        raise ApplicationError("REASON_REQUIRED", "An account-change reason is required.", 422)
    old = response(user).model_dump(mode="json")
    fields = data.model_fields_set
    if any(getattr(data, name) is None for name in fields - {"password", "roles", "reason", "full_name", "employee_id"}):
        raise ApplicationError("INVALID_USER_UPDATE", "Permission and active-status values cannot be null.", 422)
    if "roles" in fields and data.roles is None:
        raise ApplicationError("INVALID_ROLE", "Roles cannot be null.", 422)
    updated_roles = _roles(session, data.roles) if "roles" in fields else None
    for name in fields - {"password", "roles", "reason"}:
        value = getattr(data, name)
        if value is None and name not in {"full_name", "employee_id"}:
            raise ApplicationError("INVALID_USER_UPDATE", f"{name} cannot be null.", 422)
        setattr(user, name, value)
    if "roles" in fields:
        user.roles = updated_roles
    if "password" in fields and data.password is not None:
        user.password_hash = PasswordService().hash(data.password.get_secret_value())
    new = response(user).model_dump(mode="json")
    new["password_changed"] = "password" in fields and data.password is not None
    session.add(AuditLog(actor_id=actor.id, action="UPDATE", entity_type="user", entity_id=user.id,
        old_values=old, new_values=new, reason=data.reason.strip()))
    _commit(session)
    return response(user)
