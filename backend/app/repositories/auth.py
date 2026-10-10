from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.auth import Role, User


def find_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def find_user_with_permissions(session: Session, user_id: UUID) -> User | None:
    # Each remote round trip is costly. Load grants in the same query while
    # still re-reading the active account and its permissions on every request.
    return session.scalars(
        select(User).where(User.id == user_id)
        .options(joinedload(User.roles).joinedload(Role.permissions))
        .execution_options(populate_existing=True)
    ).unique().one_or_none()
