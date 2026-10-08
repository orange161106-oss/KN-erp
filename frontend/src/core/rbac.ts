/** UI hints use the backend's effective permission list; roles are labels only. */
export type ActionName = 'create' | 'read' | 'update' | 'delete' | 'import' | 'export';
export interface UserContextData { roles: string[]; permissions: string[]; is_super_admin?: boolean; }

export function canPerform(user: UserContextData | null | undefined, module: string, action: ActionName): boolean {
  if (!user) return false;
  if (user.is_super_admin) return true;
  const prefix: Record<string, string> = {
    grns: 'purchase.grns', purchase_orders: 'purchase.orders', prd: 'prd.plan',
    inventory: 'inventory.stock', requirements: 'requirements',
  };
  const code = `${prefix[module] || module}.${action}`;
  if (user.permissions.includes(code)) return true;
  if (module === 'prd') return user.permissions.includes(action === 'read' || action === 'export' ? 'planning.read' : 'planning.write');
  if (module === 'requirements') return user.permissions.includes(action === 'read' || action === 'export' ? 'planning.read' : 'requirements.calculate');
  return false;
}

export function canOpen(user: UserContextData, path: string): boolean {
  if (user.is_super_admin || path === '/status') return true;
  const codes: Record<string, string[]> = {
    '/': ['reports.inventory.read'], '/dashboard': ['reports.inventory.read'],
    '/masters': ['masters.read', 'masters.units.read', 'masters.consumables.read', 'masters.suppliers.read'],
    '/mappings': ['masters.read'], '/rules': ['masters.read'],
    '/prd': ['planning.read', 'prd.plan.read'], '/requirements': ['planning.read'],
    '/plant-workflow': ['plant_workflow:view', 'plant_workflow:confirm', 'plant_workflow:approve'],
    '/inventory': ['inventory.stock.read'], '/purchase': ['purchasing:view'],
    '/purchase-orders': ['purchase.orders.read'], '/grns': ['purchase.grns.read'],
    '/alerts': ['alerts:view'], '/reports': ['reports.inventory.read', 'reports.purchase.read'],
    '/admin': [],
  };
  return (codes[path] || []).some(code => user.permissions.includes(code));
}
