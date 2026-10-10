/** UI hints use the backend's effective permission list; roles are labels only. */
export type ActionName = 'create' | 'read' | 'update' | 'delete' | 'import' | 'export';
export interface UserContextData { roles: string[]; permissions: string[]; is_super_admin?: boolean; is_superuser?: boolean; [key: string]: any; }

export function isSuperAdmin(user: (UserContextData & Record<string, any>) | null | undefined): boolean {
  if (!user) return false;
  return Boolean(user.is_super_admin || user.is_superuser);
}

export function canPerform(user: (UserContextData & Record<string, any>) | null | undefined, module: string, action: ActionName): boolean {
  if (!user) return false;
  if (isSuperAdmin(user)) return true;

  // Check 40-point CRUD flags
  const crudOp = action === 'import' ? 'create' : action === 'export' ? 'read' : action;
  const moduleMap: Record<string, string> = {
    prd: 'prd_planning',
    requirements: 'requirements',
    grns: 'goods_receipts',
    purchase_orders: 'purchase_orders',
    inventory: 'inventory',
    masters: 'masters',
    mappings: 'production_mappings',
    rules: 'consumption_norms',
    plant_workflow: 'plant_workflow',
    purchase: 'purchase',
  };
  const modKey = moduleMap[module] || module;

  // If modern 40-point CRUD flags exist on user, strictly enforce them
  const hasModernFlags =
    'masters_read' in user ||
    'prd_planning_read' in user ||
    'inventory_read' in user ||
    'can_access_dashboard' in user;

  if (hasModernFlags) {
    return Boolean(user[`${modKey}_${crudOp}`]);
  }

  // Legacy fallback ONLY for mock test objects that omit modern flags
  const prefix: Record<string, string> = {
    grns: 'purchase.grns', purchase_orders: 'purchase.orders', prd: 'prd.plan',
    inventory: 'inventory.stock', requirements: 'requirements',
  };
  const code = `${prefix[module] || module}.${action}`;
  if (user.permissions?.includes(code)) return true;
  if (module === 'prd') return Boolean(user.permissions?.includes(action === 'read' || action === 'export' ? 'planning.read' : 'planning.write'));
  if (module === 'requirements') {
    if (action === 'read' || action === 'export') return Boolean(user.permissions?.includes('requirements.read'));
    return Boolean(user.permissions?.includes('requirements.calculate'));
  }
  return false;
}

export function canOpen(user: (UserContextData & Record<string, any>) | null | undefined, path: string): boolean {
  if (!user) return false;
  if (isSuperAdmin(user) || path === '/status') return true;
  if (path === '/admin') return isSuperAdmin(user);

  // If modern 40-point CRUD / global flags are defined on the user object, strictly evaluate them
  const hasModernFlags =
    'masters_read' in user ||
    'prd_planning_read' in user ||
    'inventory_read' in user ||
    'can_access_dashboard' in user;

  if (hasModernFlags) {
    if (path === '/' || path === '/dashboard') return Boolean(user.can_access_dashboard);
    if (path === '/alerts') return Boolean(user.alert_production || user.alert_inventory || user.alert_purchasing || user.alert_system);

    if (path === '/masters') return Boolean(user.masters_read);
    if (path === '/mappings') return Boolean(user.production_mappings_read);
    if (path === '/rules') return Boolean(user.consumption_norms_read);
    if (path === '/prd') return Boolean(user.prd_planning_read);
    if (path === '/requirements') return Boolean(user.requirements_read);
    if (path === '/plant-workflow') return Boolean(
      user.plant_workflow_read ||
      user.can_access_plant_1 ||
      user.can_access_plant_2 ||
      user.can_access_plant_3 ||
      user.can_access_plant_4 ||
      user.can_access_plant_5
    );
    if (path === '/inventory') return Boolean(user.inventory_read);
    if (path === '/purchase') return Boolean(user.purchase_read);
    if (path === '/purchase-orders') return Boolean(user.purchase_orders_read);
    if (path === '/grns') return Boolean(user.goods_receipts_read);

    return false;
  }

  // Legacy fallback ONLY for mock test objects that omit modern CRUD flags
  const codes: Record<string, string[]> = {
    '/': ['reports.inventory.read'], '/dashboard': ['reports.inventory.read'],
    '/masters': ['masters.read', 'masters.units.read', 'masters.consumables.read', 'masters.suppliers.read'],
    '/mappings': ['mappings.read'], '/rules': ['norms.read'],
    '/prd': ['planning.read', 'prd.plan.read'], '/requirements': ['requirements.read'],
    '/plant-workflow': ['plant_workflow:view', 'plant_workflow:confirm', 'plant_workflow:approve'],
    '/inventory': ['inventory.stock.read'], '/purchase': ['purchasing:view'],
    '/purchase-orders': ['purchase.orders.read'], '/grns': ['purchase.grns.read'],
    '/alerts': ['alerts:view'], '/reports': ['reports.inventory.read', 'reports.purchase.read'],
    '/admin': [],
  };
  return (codes[path] || []).some(code => user.permissions?.includes(code));
}

export function canCreate(user: (UserContextData & Record<string, any>) | null | undefined, module: string): boolean {
  if (isSuperAdmin(user)) return true;
  return canPerform(user, module, 'create');
}

export function canRead(user: (UserContextData & Record<string, any>) | null | undefined, module: string): boolean {
  if (isSuperAdmin(user)) return true;
  return canPerform(user, module, 'read');
}

export function canEdit(user: (UserContextData & Record<string, any>) | null | undefined, module: string): boolean {
  if (isSuperAdmin(user)) return true;
  return canPerform(user, module, 'update');
}

export function canUpdate(user: (UserContextData & Record<string, any>) | null | undefined, module: string): boolean {
  if (isSuperAdmin(user)) return true;
  return canPerform(user, module, 'update');
}

export function canDelete(user: (UserContextData & Record<string, any>) | null | undefined, module: string): boolean {
  if (isSuperAdmin(user)) return true;
  return canPerform(user, module, 'delete');
}

export function hasAccess(user: (UserContextData & Record<string, any>) | null | undefined, pathOrModule: string): boolean {
  if (isSuperAdmin(user)) return true;
  if (pathOrModule.startsWith('/')) {
    return canOpen(user, pathOrModule);
  }
  return canPerform(user, pathOrModule, 'read');
}
