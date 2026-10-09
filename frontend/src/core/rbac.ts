/** UI hints use the backend's effective permission list; roles are labels only. */
export type ActionName = 'create' | 'read' | 'update' | 'delete' | 'import' | 'export';
export interface UserContextData { roles: string[]; permissions: string[]; is_super_admin?: boolean; [key: string]: any; }

export function canPerform(user: (UserContextData & Record<string, any>) | null | undefined, module: string, action: ActionName): boolean {
  if (!user) return false;
  if (user.is_super_admin) return true;

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
  if (user[`${modKey}_${crudOp}`] === true) return true;

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
  if (user.is_super_admin || path === '/status') return true;
  if (path === '/admin') return Boolean(user.is_super_admin);

  // Check 40-point CRUD flags
  if ((path === '/' || path === '/dashboard') && (user.inventory_read || user.purchase_read || user.requirements_read)) return true;
  if (path === '/masters' && user.masters_read) return true;
  if (path === '/mappings' && user.production_mappings_read) return true;
  if (path === '/rules' && user.consumption_norms_read) return true;
  if (path === '/prd' && user.prd_planning_read) return true;
  if (path === '/requirements' && user.requirements_read) return true;
  if (path === '/plant-workflow' && (user.plant_workflow_read || user.can_access_plant_1 || user.can_access_plant_2 || user.can_access_plant_3 || user.can_access_plant_4 || user.can_access_plant_5)) return true;
  if (path === '/inventory' && user.inventory_read) return true;
  if (path === '/purchase' && user.purchase_read) return true;
  if (path === '/purchase-orders' && user.purchase_orders_read) return true;
  if (path === '/grns' && user.goods_receipts_read) return true;
  if ((path === '/alerts' || path === '/reports') && (user.inventory_read || user.purchase_read || user.requirements_read)) return true;

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
