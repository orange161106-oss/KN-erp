"""Import shared ORM models so Alembic can discover their metadata."""

from app.models.auth import Permission, Role, User, role_permissions, user_roles

__all__ = ["Permission", "Role", "User", "role_permissions", "user_roles"]
from app.models.production import Plant, Process, Route, RouteStep
from app.models.masters import Customer, Product
from app.models.prd import ImportBatch, ImportError, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.audit import AuditLog

__all__ += ["Plant", "Process", "Route", "RouteStep", "Customer", "Product", "ImportBatch", "ImportError", "PlanningVersion", "PRDOrderHeader", "PRDOrderItem", "Consumable", "Supplier", "SupplierConsumable", "Unit", "AuditLog"]
