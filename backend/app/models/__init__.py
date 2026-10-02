"""Import shared ORM models so Alembic can discover their metadata."""

from app.models.audit import AuditLog
from app.models.auth import Permission, Role, User, role_permissions, user_roles
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.masters import Customer, Product
from app.models.prd import ImportBatch, ImportError, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.models.production import Plant, Process, Route, RouteStep
from app.models.requirements import CalculatedRequirement, RequirementCalculationError
from app.models.rules import ConsumptionNorm

__all__ = [
    "AuditLog",
    "Permission",
    "Role",
    "User",
    "role_permissions",
    "user_roles",
    "Consumable",
    "Supplier",
    "SupplierConsumable",
    "Unit",
    "ProductPlant",
    "ProductProcessConsumable",
    "Customer",
    "Product",
    "ImportBatch",
    "ImportError",
    "PlanningVersion",
    "PRDOrderHeader",
    "PRDOrderItem",
    "Plant",
    "Process",
    "Route",
    "RouteStep",
    "ConsumptionNorm",
    "CalculatedRequirement",
    "RequirementCalculationError",
]
