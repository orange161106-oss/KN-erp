from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import Role, User


def find_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def find_user_with_permissions(session: Session, user_id: UUID) -> User | None:
    return session.scalar(
        select(User).where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
