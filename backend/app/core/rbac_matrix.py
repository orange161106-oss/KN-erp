"""Role-Based Access Control (RBAC) Permission Matrix Configuration.

This single configuration defines:
Role x Module x Action (create, read, update, delete, import, export)
All endpoints and frontend checks can consult this matrix or permissions derived from it.
"""
from typing import Dict, List, Set

MODULES = [
    "grns",
    "purchase_orders",
    "masters",
    "mappings",
    "rules",
    "prd",
    "requirements",
    "inventory",
]

ACTIONS = ["create", "read", "update", "delete", "import", "export"]

# Permission matrix: Role -> Module -> List of allowed actions
ROLE_MODULE_PERMISSIONS: Dict[str, Dict[str, List[str]]] = {
    "ADMIN": {
        "grns": ["create", "read", "update", "delete", "import", "export"],
        "purchase_orders": ["create", "read", "update", "delete", "import", "export"],
        "masters": ["create", "read", "update", "delete", "import", "export"],
        "mappings": ["create", "read", "update", "delete", "import", "export"],
        "rules": ["create", "read", "update", "delete", "import", "export"],
        "prd": ["create", "read", "update", "delete", "import", "export"],
        "requirements": ["create", "read", "update", "delete", "import", "export"],
        "inventory": ["create", "read", "update", "delete", "import", "export"],
    },
    "PLANNER": {
        "grns": ["create", "read", "update", "delete", "import", "export"],
        "purchase_orders": ["create", "read", "update", "delete", "import", "export"],
        "masters": ["create", "read", "update", "delete", "import", "export"],
        "mappings": ["create", "read", "update", "delete", "import", "export"],
        "rules": ["create", "read", "update", "delete", "import", "export"],
        "prd": ["create", "read", "update", "delete", "import", "export"],
        "requirements": ["create", "read", "update", "delete", "import", "export"],
        "inventory": ["read", "export"],
    },
    "PURCHASE": {
        "grns": ["create", "read", "update", "delete", "import", "export"],
        "purchase_orders": ["create", "read", "update", "delete", "import", "export"],
        "masters": ["create", "read", "update", "delete", "import", "export"],
        "mappings": ["read", "export"],
        "rules": ["read", "export"],
        "prd": ["read", "export"],
        "requirements": ["create", "read", "update", "delete", "import", "export"],
        "inventory": ["create", "read", "update", "delete", "import", "export"],
    },
    "STORE": {
        "grns": ["create", "read", "update", "delete", "import", "export"],
        "purchase_orders": ["read", "export"],
        "masters": ["create", "read", "update", "delete", "import", "export"],
        "mappings": ["read"],
        "rules": ["read"],
        "prd": ["read"],
        "requirements": ["read", "export"],
        "inventory": ["create", "read", "update", "delete", "import", "export"],
    },
    "PLANT_INCHARGE": {
        "grns": ["create", "read", "update", "delete", "import", "export"],
        "purchase_orders": ["read"],
        "masters": ["read"],
        "mappings": ["create", "read", "update", "delete", "import", "export"],
        "rules": ["read"],
        "prd": ["read", "export"],
        "requirements": ["create", "read", "update", "delete", "import", "export"],
        "inventory": ["read", "export"],
    },
    "APPROVER": {
        "grns": ["read", "export"],
        "purchase_orders": ["read", "update", "export"],
        "masters": ["read"],
        "mappings": ["read"],
        "rules": ["read"],
        "prd": ["read"],
        "requirements": ["read", "update", "export"],
        "inventory": ["read"],
    },
    "MANAGEMENT": {
        "grns": ["read", "export"],
        "purchase_orders": ["read", "export"],
        "masters": ["read", "export"],
        "mappings": ["read", "export"],
        "rules": ["read", "export"],
        "prd": ["read", "export"],
        "requirements": ["read", "export"],
        "inventory": ["read", "export"],
    },
}


def get_matrix_permissions_for_roles(roles: List[str]) -> Set[str]:
    """Calculate the set of explicit fine-grained permission codes for given roles."""
    perms: Set[str] = set()
    for role in roles:
        role_upper = role.upper()
        if role_upper not in ROLE_MODULE_PERMISSIONS:
            continue
        modules = ROLE_MODULE_PERMISSIONS[role_upper]
        for mod, actions in modules.items():
            for action in actions:
                # Standardized code format: module:action or module.action
                perms.add(f"{mod}:{action}")
                perms.add(f"{mod}.{action}")

                # Compatibility mappings for existing backend permission names
                if mod == "grns":
                    perms.add(f"purchase.grns.{action}")
                elif mod == "purchase_orders":
                    perms.add(f"purchase.orders.{action}")
                elif mod == "masters":
                    for sub in ["consumables", "units", "suppliers", "supplier_consumables"]:
                        if action in ["read", "export"]:
                            perms.add(f"masters.{sub}.read")
                        if action in ["create", "update", "delete", "import"]:
                            perms.add(f"masters.{sub}.write")
                elif mod == "inventory":
                    if action in ["read", "export"]:
                        perms.add("inventory.stock.read")
                        perms.add("inventory.projection.read")
                    if action in ["create", "update", "import"]:
                        perms.add("inventory.stock.import")
                        perms.add("inventory.projection.import")

    return perms


def has_permission(roles: List[str], module: str, action: str) -> bool:
    """Check if any of the given roles has permission to perform action on module."""
    if "ADMIN" in [r.upper() for r in roles]:
        return True
    for role in roles:
        role_upper = role.upper()
        allowed = ROLE_MODULE_PERMISSIONS.get(role_upper, {}).get(module, [])
        if action in allowed:
            return True
    return False

