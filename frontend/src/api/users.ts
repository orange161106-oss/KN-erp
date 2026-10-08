import { apiClient } from './client';

export interface UserPermissionFlags {
  // 10 Granular Workflow Feature Flags
  can_access_masters: boolean;
  can_access_production_mappings: boolean;
  can_access_consumption_norms: boolean;
  can_access_prd_planning: boolean;
  can_access_requirements: boolean;
  can_access_plant_workflow: boolean;
  can_access_inventory: boolean;
  can_access_purchase: boolean;
  can_access_purchase_orders: boolean;
  can_access_goods_receipts: boolean;

  // 5 Plant Access Flags
  can_access_plant_1: boolean;
  can_access_plant_2: boolean;
  can_access_plant_3: boolean;
  can_access_plant_4: boolean;
  can_access_plant_5: boolean;
}

export interface UserResponse extends UserPermissionFlags {
  id: string;
  username: string;
  full_name?: string | null;
  employee_id?: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  roles: string[];
}

export interface UserCreate extends UserPermissionFlags {
  username: string;
  password: string;
  full_name?: string | null;
  employee_id?: string | null;
  roles: string[];
}

export interface UserUpdate extends Partial<UserPermissionFlags> {
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
