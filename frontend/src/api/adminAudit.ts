import { apiClient } from './client';

export interface AuditLogItem {
  id: string;
  user_id?: string;
  username: string;
  action: string;
  module?: string;
  record_id?: string;
  changes_summary?: Record<string, any>;
  timestamp: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserSessionItem {
  id: string;
  user_id: string;
  username: string;
  full_name?: string;
  employee_id?: string;
  role: string;
  ip_address?: string;
  login_at: string;
  logout_at?: string;
  status: string;
}

export interface UserSessionListResponse {
  items: UserSessionItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogQueryParams {
  user_id?: string;
  action?: string;
  module?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface UserSessionQueryParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export const adminAuditApi = {
  getAuditLogs: (params: AuditLogQueryParams = {}): Promise<AuditLogListResponse> => {
    const q = new URLSearchParams();
    if (params.user_id) q.set('user_id', params.user_id);
    if (params.action) q.set('action', params.action);
    if (params.module) q.set('module', params.module);
    if (params.date_from) q.set('date_from', params.date_from);
    if (params.date_to) q.set('date_to', params.date_to);
    if (params.limit !== undefined) q.set('limit', String(params.limit));
    if (params.offset !== undefined) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<AuditLogListResponse>(`/api/v1/admin/audit-logs${qs ? `?${qs}` : ''}`);
  },

  getActiveSessions: (params: UserSessionQueryParams = {}): Promise<UserSessionListResponse> => {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.limit !== undefined) q.set('limit', String(params.limit));
    if (params.offset !== undefined) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<UserSessionListResponse>(`/api/v1/admin/active-sessions${qs ? `?${qs}` : ''}`);
  },
};
