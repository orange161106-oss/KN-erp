"""Security helper for M8.1 & Granular Matrix — Plant-Scoped Data Isolation."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.plant_workflow import UserPlant
from app.schemas.auth import CurrentUser


def get_user_authorized_plant_ids(session: Session, user: CurrentUser) -> list[UUID] | None:
    """Return authorized plant IDs for the user.

    - Returns None if the user has global plant access (Super Admin).
    - Returns list of assigned plant UUIDs for plant-constrained users.
    """
    if user.is_super_admin:
        return None  # Unrestricted access across all plants

    if user.plant_ids:
        return list(user.plant_ids)

    # Query assigned plants from user_plants table
    stmt = select(UserPlant.plant_id).where(UserPlant.user_id == user.id)
    assigned_plant_ids = list(session.execute(stmt).scalars().all())
    return assigned_plant_ids


def validate_plant_access(
    session: Session,
    user: CurrentUser,
    target_plant_id: UUID | None,
) -> None:
    """Validate that the user is authorized to access target_plant_id."""
    if user.is_super_admin:
        return

    authorized_plant_ids = get_user_authorized_plant_ids(session, user)
    if authorized_plant_ids is None:
        return

    if target_plant_id is not None:
        if target_plant_id not in authorized_plant_ids:
            raise ApplicationError(
                "PERMISSION_DENIED",
                "User is not authorized to access data for this plant.",
                403,
            )
