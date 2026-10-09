import { createContext, useContext } from 'react';

export interface CurrentUser {
  id: string;
  username: string;
  roles: string[];
  permissions: string[];
  is_super_admin?: boolean;

  // 40 Granular CRUD Feature Flags
  masters_read?: boolean;
  masters_create?: boolean;
  masters_update?: boolean;
  masters_delete?: boolean;

  production_mappings_read?: boolean;
  production_mappings_create?: boolean;
  production_mappings_update?: boolean;
  production_mappings_delete?: boolean;

  consumption_norms_read?: boolean;
  consumption_norms_create?: boolean;
  consumption_norms_update?: boolean;
  consumption_norms_delete?: boolean;

  prd_planning_read?: boolean;
  prd_planning_create?: boolean;
  prd_planning_update?: boolean;
  prd_planning_delete?: boolean;

  requirements_read?: boolean;
  requirements_create?: boolean;
  requirements_update?: boolean;
  requirements_delete?: boolean;

  plant_workflow_read?: boolean;
  plant_workflow_create?: boolean;
  plant_workflow_update?: boolean;
  plant_workflow_delete?: boolean;

  inventory_read?: boolean;
  inventory_create?: boolean;
  inventory_update?: boolean;
  inventory_delete?: boolean;

  purchase_read?: boolean;
  purchase_create?: boolean;
  purchase_update?: boolean;
  purchase_delete?: boolean;

  purchase_orders_read?: boolean;
  purchase_orders_create?: boolean;
  purchase_orders_update?: boolean;
  purchase_orders_delete?: boolean;

  goods_receipts_read?: boolean;
  goods_receipts_create?: boolean;
  goods_receipts_update?: boolean;
  goods_receipts_delete?: boolean;

  // Plant Scope Access
  can_access_plant_1?: boolean;
  can_access_plant_2?: boolean;
  can_access_plant_3?: boolean;
  can_access_plant_4?: boolean;
  can_access_plant_5?: boolean;
}

interface AuthState {
  user: CurrentUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('Authentication provider is missing');
  return context;
}
