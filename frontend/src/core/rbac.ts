/**
 * Centralized RBAC permission checks on the frontend.
 * Mirrors the backend RBAC matrix: role x module x action.
 */

export type RoleName =
  | 'ADMIN'
  | 'PLANNER'
  | 'PURCHASE'
  | 'STORE'
  | 'PLANT_INCHARGE'
  | 'APPROVER'
  | 'MANAGEMENT'
  | string;

export type ActionName = 'create' | 'read' | 'update' | 'delete' | 'import' | 'export';

export interface UserContextData {
  roles: string[];
  permissions: string[];
}

export const PERMISSION_MATRIX: Record<string, Record<string, ActionName[]>> = {
  ADMIN: {
    grns: ['create', 'read', 'update', 'delete', 'import', 'export'],
    purchase_orders: ['create', 'read', 'update', 'delete', 'import', 'export'],
    masters: ['create', 'read', 'update', 'delete', 'import', 'export'],
    mappings: ['create', 'read', 'update', 'delete', 'import', 'export'],
    rules: ['create', 'read', 'update', 'delete', 'import', 'export'],
    prd: ['create', 'read', 'update', 'delete', 'import', 'export'],
    requirements: ['create', 'read', 'update', 'delete', 'import', 'export'],
    inventory: ['create', 'read', 'update', 'delete', 'import', 'export'],
  },
  PLANNER: {
    grns: ['create', 'read', 'update', 'delete', 'import', 'export'],
    purchase_orders: ['create', 'read', 'update', 'delete', 'import', 'export'],
    masters: ['create', 'read', 'update', 'delete', 'import', 'export'],
    mappings: ['create', 'read', 'update', 'delete', 'import', 'export'],
    rules: ['create', 'read', 'update', 'delete', 'import', 'export'],
    prd: ['create', 'read', 'update', 'delete', 'import', 'export'],
    requirements: ['create', 'read', 'update', 'delete', 'import', 'export'],
    inventory: ['read', 'export'],
  },
  PURCHASE: {
    grns: ['create', 'read', 'update', 'delete', 'import', 'export'],
    purchase_orders: ['create', 'read', 'update', 'delete', 'import', 'export'],
    masters: ['create', 'read', 'update', 'delete', 'import', 'export'],
    mappings: ['read', 'export'],
    rules: ['read', 'export'],
    prd: ['read', 'export'],
    requirements: ['create', 'read', 'update', 'delete', 'import', 'export'],
    inventory: ['create', 'read', 'update', 'delete', 'import', 'export'],
  },
  STORE: {
    grns: ['create', 'read', 'update', 'delete', 'import', 'export'],
    purchase_orders: ['read', 'export'],
    masters: ['create', 'read', 'update', 'delete', 'import', 'export'],
    mappings: ['read'],
    rules: ['read'],
    prd: ['read'],
    requirements: ['read', 'export'],
    inventory: ['create', 'read', 'update', 'delete', 'import', 'export'],
  },
  PLANT_INCHARGE: {
    grns: ['create', 'read', 'update', 'delete', 'import', 'export'],
    purchase_orders: ['read'],
    masters: ['read'],
    mappings: ['create', 'read', 'update', 'delete', 'import', 'export'],
    rules: ['read'],
    prd: ['read', 'export'],
    requirements: ['create', 'read', 'update', 'delete', 'import', 'export'],
    inventory: ['read', 'export'],
  },
  APPROVER: {
    grns: ['read', 'export'],
    purchase_orders: ['read', 'update', 'export'],
    masters: ['read'],
    mappings: ['read'],
    rules: ['read'],
    prd: ['read'],
    requirements: ['read', 'update', 'export'],
    inventory: ['read'],
  },
  MANAGEMENT: {
    grns: ['read', 'export'],
    purchase_orders: ['read', 'export'],
    masters: ['read', 'export'],
    mappings: ['read', 'export'],
    rules: ['read', 'export'],
    prd: ['read', 'export'],
    requirements: ['read', 'export'],
    inventory: ['read', 'export'],
  },
};

export function canPerform(user: UserContextData | null | undefined, module: string, action: ActionName): boolean {
  if (!user) return false;
  if (user.roles.includes('ADMIN')) return true;

  // Direct permission match
  const explicitCodes = [
    `${module}:${action}`,
    `${module}.${action}`,
    `purchase.${module}.${action}`,
    `purchase.grns.${action}`,
    `purchase.orders.${action}`,
    `prd.records.${action}`,
    `requirements.records.${action}`,
  ];
  if (explicitCodes.some(c => user.permissions.includes(c))) return true;

  // Matrix match based on user roles
  for (const role of user.roles) {
    const roleUpper = role.toUpperCase();
    const actions = PERMISSION_MATRIX[roleUpper]?.[module] || [];
    if (actions.includes(action)) return true;
  }

  return false;
}

