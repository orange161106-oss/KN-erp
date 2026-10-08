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


# Workflow visibility complements the existing operation grants. Checking a
# workflow must not grant imports, approvals, or employee administration.
WORKFLOW_READ_PERMISSIONS = {
    "masters.read": ("can_access_masters",),
    "mappings.read": ("can_access_production_mappings",),
    "norms.read": ("can_access_consumption_norms",),
    "planning.read": ("can_access_prd_planning",),
    "requirements.read": ("can_access_requirements",),
    "plant_workflow:view": ("can_access_plant_workflow",),
    "inventory.stock.read": ("can_access_inventory",),
    "inventory.projection.read": ("can_access_inventory",),
    "purchasing:view": ("can_access_purchase",),
    "purchase.orders.read": ("can_access_purchase_orders", "can_access_purchase"),
    "purchase.grns.read": ("can_access_goods_receipts",),
}
for resource in ("units", "consumables", "suppliers", "supplier_consumables"):
    WORKFLOW_READ_PERMISSIONS[f"masters.{resource}.read"] = ("can_access_masters",)
for resource in ("plan", "records"):
    for action in ("read", "export"):
        WORKFLOW_READ_PERMISSIONS[f"prd.{resource}.{action}"] = ("can_access_prd_planning",)
FEATURE_PERMISSIONS.update({
    "mappings.read": ("can_view_master_data",),
    "mappings.write": ("can_edit_master_data",),
    "norms.read": ("can_view_master_data",),
    "norms.write": ("can_edit_master_data",),
    "requirements.read": ("can_view_planning",),
})


def allows(user, code: str) -> bool:
    if user.is_super_admin:
        return True
    if code == "admin:manage":
        return False
    if any(getattr(user, flag, False) for flag in WORKFLOW_READ_PERMISSIONS.get(code, ())):
        return True
    if code in ANY_FEATURE_PERMISSIONS:
        return any(getattr(user, f, False) for f in ANY_FEATURE_PERMISSIONS[code])
    flags = FEATURE_PERMISSIONS.get(code)
    if flags is not None:
        return all(getattr(user, flag, False) for flag in flags)
    return code in user.permissions


def effective_permissions(user, legacy: set[str]) -> list[str]:
    from types import SimpleNamespace

    candidates = legacy | set(FEATURE_PERMISSIONS) | set(ANY_FEATURE_PERMISSIONS) | set(WORKFLOW_READ_PERMISSIONS) | {"admin:manage"}
    if user.is_super_admin:
        candidates |= {"inventory.stock.read", "inventory.stock.import", "inventory.projection.read",
            "inventory.projection.import", "purchase.orders.cancel", "purchase.orders.price",
            "purchase.demand.submit", "alerts:view", "alerts:acknowledge"}
    # ORM users have role relationships; the policy consumes explicit codes.
    identity = SimpleNamespace(**{flag: getattr(user, flag, False)
        for flags in [*FEATURE_PERMISSIONS.values(), *ANY_FEATURE_PERMISSIONS.values(), *WORKFLOW_READ_PERMISSIONS.values()]
        for flag in flags}, is_super_admin=user.is_super_admin, permissions=legacy)
    return sorted(code for code in candidates if allows(identity, code))
