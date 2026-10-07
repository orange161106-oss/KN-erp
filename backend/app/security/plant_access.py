"""Security helper for M8.1 — Plant-Scoped Data Isolation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.plant_workflow import UserPlant
from app.schemas.auth import CurrentUser

# Roles with global access to all plants
GLOBAL_PLANT_ROLES = {"ADMIN", "PLANNER", "MANAGEMENT"}


def get_user_authorized_plant_ids(session: Session, user: CurrentUser) -> list[UUID] | None:
    """Return authorized plant IDs for the user.

    - Returns None if the user has global plant access (ADMIN, PLANNER, MANAGEMENT).
    - Returns list of assigned plant UUIDs for PLANT_INCHARGE.
    """
    if any(role in GLOBAL_PLANT_ROLES for role in user.roles):
        return None  # None indicates unrestricted access across all plants

    # Query assigned plants from user_plants table
    stmt = select(UserPlant.plant_id).where(UserPlant.user_id == user.id)
    assigned_plant_ids = list(session.execute(stmt).scalars().all())
    return assigned_plant_ids


def validate_plant_access(
    session: Session,
    user: CurrentUser,
    target_plant_id: UUID | None,
) -> None:
    """Validate that the user is authorized to access target_plant_id.

    Raises HTTP 403 PERMISSION_DENIED if a PLANT_INCHARGE user attempts to access,
    confirm, or request adjustments for a plant not assigned to them in user_plants.
    """
    authorized_plant_ids = get_user_authorized_plant_ids(session, user)

    # Global roles (authorized_plant_ids is None) can access any plant
    if authorized_plant_ids is None:
        return

    # If target_plant_id is specified, verify it is in user's assigned plants
    if target_plant_id is not None:
        if target_plant_id not in authorized_plant_ids:
            raise ApplicationError(
                "PERMISSION_DENIED",
                "User is not authorized to access data for this plant.",
                403,
            )
