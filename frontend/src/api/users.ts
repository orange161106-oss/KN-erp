import { apiClient } from './client';

export interface UserPermissionFlags {
  // 10 Granular Feature Flags
  can_view_master_data: boolean;
  can_edit_master_data: boolean;
  can_view_planning: boolean;
  can_run_calculations: boolean;
  can_confirm_demand: boolean;
  can_approve_extra_demand: boolean;
  can_create_po: boolean;
  can_approve_po: boolean;
  can_upload_grn: boolean;
  can_view_reports: boolean;

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
