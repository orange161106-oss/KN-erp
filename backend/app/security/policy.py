"""Feature grants override legacy role grants for explicitly mapped operations.

Unmapped capabilities retain their existing explicit permission requirement. In
particular, a GRN checkbox does not silently grant stock-import authority.
"""

FEATURE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "masters.read": ("can_view_master_data",),
    "masters.write": ("can_edit_master_data",),
    "planning.read": ("can_view_planning",),
    "planning.write": ("can_view_planning", "can_run_calculations"),
    "requirements.calculate": ("can_run_calculations",),
    "plant_workflow:confirm": ("can_confirm_demand",),
    "plant_workflow:request": ("can_confirm_demand",),
    "plant_workflow:approve": ("can_approve_extra_demand",),
    "purchase.orders.create": ("can_create_po",),
    "purchase.orders.issue": ("can_approve_po",),
    "purchasing:approve": ("can_approve_po",),
    "reports.inventory.read": ("can_view_reports",),
    "reports.purchase.read": ("can_view_reports",),
    "reports:view": ("can_view_reports",),
}
for resource in ("units", "consumables", "suppliers", "supplier_consumables"):
    FEATURE_PERMISSIONS[f"masters.{resource}.read"] = ("can_view_master_data",)
    FEATURE_PERMISSIONS[f"masters.{resource}.write"] = ("can_edit_master_data",)
for action in ("read", "export"):
    FEATURE_PERMISSIONS[f"prd.plan.{action}"] = ("can_view_planning",)
    FEATURE_PERMISSIONS[f"prd.records.{action}"] = ("can_view_planning",)
for action in ("create", "update", "delete", "import"):
    FEATURE_PERMISSIONS[f"prd.plan.{action}"] = ("can_view_planning", "can_run_calculations")
    FEATURE_PERMISSIONS[f"prd.records.{action}"] = ("can_view_planning", "can_run_calculations")
for action in ("read", "export", "create", "update", "delete", "import"):
    FEATURE_PERMISSIONS[f"purchase.grns.{action}"] = ("can_upload_grn",)

ANY_FEATURE_PERMISSIONS = {
    "plant_workflow:view": ("can_confirm_demand", "can_approve_extra_demand"),
    "purchase.orders.read": ("can_create_po", "can_approve_po"),
    "purchasing:view": ("can_create_po", "can_approve_po"),
}


def allows(user, code: str) -> bool:
    if user.is_super_admin:
        return True
    if code == "admin:manage":
        return False
    if code in ANY_FEATURE_PERMISSIONS:
        return any(getattr(user, f, False) for f in ANY_FEATURE_PERMISSIONS[code])
    flags = FEATURE_PERMISSIONS.get(code)
    if flags is not None:
        return all(getattr(user, flag, False) for flag in flags)
    return code in user.permissions


def effective_permissions(user, legacy: set[str]) -> list[str]:
    # Super Admin need not rely on a seeded ADMIN role.
    candidates = legacy | set(FEATURE_PERMISSIONS) | set(ANY_FEATURE_PERMISSIONS) | {"admin:manage"}
    if user.is_super_admin:
        return sorted(candidates | {"inventory.stock.read", "inventory.stock.import", "inventory.projection.read",
            "inventory.projection.import", "purchase.orders.cancel", "purchase.orders.price",
            "purchase.demand.submit", "alerts:view", "alerts:acknowledge"})
    result = []
    for code in candidates:
        if code in ANY_FEATURE_PERMISSIONS:
            permitted = any(getattr(user, f, False) for f in ANY_FEATURE_PERMISSIONS[code])
        elif code in FEATURE_PERMISSIONS:
            permitted = all(getattr(user, f, False) for f in FEATURE_PERMISSIONS[code])
        else:
            permitted = code in legacy and code != "admin:manage"
        if permitted:
            result.append(code)
    return sorted(result)
