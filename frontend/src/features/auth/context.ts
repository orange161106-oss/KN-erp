import { createContext, useContext } from 'react';
import type { UserPermissionFlags } from '../../api/users';

export interface CurrentUser extends Partial<UserPermissionFlags> {
  plant_ids?: string[];
  id: string;
  username: string;
  roles: string[];
  permissions: string[];
  is_super_admin?: boolean;

  can_access_masters?: boolean;
  can_access_production_mappings?: boolean;
  can_access_consumption_norms?: boolean;
  can_access_prd_planning?: boolean;
  can_access_requirements?: boolean;
  can_access_plant_workflow?: boolean;
  can_access_inventory?: boolean;
  can_access_purchase?: boolean;
  can_access_purchase_orders?: boolean;
  can_access_goods_receipts?: boolean;
  can_access_plant_1?: boolean;
  can_access_plant_2?: boolean;
  can_access_plant_3?: boolean;
  can_access_plant_4?: boolean;
  can_access_plant_5?: boolean;

  can_view_master_data?: boolean;
  can_view_planning?: boolean;
  can_run_calculations?: boolean;
  can_confirm_demand?: boolean;
  can_approve_po?: boolean;
  can_create_po?: boolean;
  can_upload_grn?: boolean;
  can_view_reports?: boolean;
}

interface AuthState {
  user: CurrentUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('Authentication provider is missing');
  }

  return context;
}