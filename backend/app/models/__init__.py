"""Import shared ORM models so Alembic can discover their metadata."""

from app.models.auth import Permission, Role, User, role_permissions, user_roles

__all__ = ["Permission", "Role", "User", "role_permissions", "user_roles"]
