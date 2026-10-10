import { apiClient } from './client';

export interface UserPermissionFlags {
  // 40 Granular CRUD Feature Flags
  masters_read: boolean;
  masters_create: boolean;
  masters_update: boolean;
  masters_delete: boolean;

  production_mappings_read: boolean;
  production_mappings_create: boolean;
  production_mappings_update: boolean;
  production_mappings_delete: boolean;

  consumption_norms_read: boolean;
  consumption_norms_create: boolean;
  consumption_norms_update: boolean;
  consumption_norms_delete: boolean;

  prd_planning_read: boolean;
  prd_planning_create: boolean;
  prd_planning_update: boolean;
  prd_planning_delete: boolean;

  requirements_read: boolean;
  requirements_create: boolean;
  requirements_update: boolean;
  requirements_delete: boolean;

  plant_workflow_read: boolean;
  plant_workflow_create: boolean;
  plant_workflow_update: boolean;
  plant_workflow_delete: boolean;

  inventory_read: boolean;
  inventory_create: boolean;
  inventory_update: boolean;
  inventory_delete: boolean;

  purchase_read: boolean;
  purchase_create: boolean;
  purchase_update: boolean;
  purchase_delete: boolean;

  purchase_orders_read: boolean;
  purchase_orders_create: boolean;
  purchase_orders_update: boolean;
  purchase_orders_delete: boolean;

  goods_receipts_read: boolean;
  goods_receipts_create: boolean;
  goods_receipts_update: boolean;
  goods_receipts_delete: boolean;

  // 5 Plant Access Flags
  can_access_plant_1: boolean;
  can_access_plant_2: boolean;
  can_access_plant_3: boolean;
  can_access_plant_4: boolean;
  can_access_plant_5: boolean;

  // Global Module Access Flags
  can_access_dashboard: boolean;

  // Categorized Alert Subscriptions
  alert_production: boolean;
  alert_inventory: boolean;
  alert_purchasing: boolean;
  alert_system: boolean;
}

export interface UserResponse extends UserPermissionFlags {
  id: string;
  username: string;
  full_name?: string | null;
  employee_id?: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  is_superuser?: boolean;
  roles: string[];
}

export interface UserCreate extends UserPermissionFlags {
  is_active: boolean;
  reason?: string;
  username: string;
  password: string;
  full_name?: string | null;
  employee_id?: string | null;
  roles: string[];
}

export interface UserUpdate extends Partial<UserPermissionFlags> {
  reason?: string;
  password?: string;
  full_name?: string | null;
  employee_id?: string | null;
  is_active?: boolean;
  roles?: string[];
}

export const usersApi = {
  /** Fetch list of all system users */
  getUsers: (): Promise<UserResponse[]> => {
    return apiClient.get<UserResponse[]>('/api/v1/users');
  },

  /** Create a new user with granular permissions & plant flags */
  createUser: (data: UserCreate): Promise<UserResponse> => {
    return apiClient.post<UserResponse>('/api/v1/users', data);
  },

  /** Update an existing user's credentials, active status, roles, or permissions */
  updateUser: (userId: string, data: UserUpdate): Promise<UserResponse> => {
    return apiClient.put<UserResponse>(`/api/v1/users/${userId}`, data);
  },
};
