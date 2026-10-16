import axios from 'axios';
import { getAccessToken, getApiBaseUrl } from '../../api/client';

export interface RequirementLineItem {
  id: string;
  plan_id: string;
  consumable_id: string;
  serial_no?: number | null;
  part_no?: string | null;
  formula_qty?: number;
  requested_qty: number;
  approved_qty?: number;
  is_modified?: boolean;
  modification_reason?: string | null;
  item_id?: string | null;
  item_code?: string | null;
  consumable_name?: string | null;
  unit?: string | null;
  description?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SingleLineItemPayload {
  consumable_id?: string;
  item_code?: string;
  item_description?: string;
  part_no?: string;
  unit?: string;
  serial_no?: number;
  formula_qty?: number;
  requested_qty: number;
  approved_qty?: number;
  is_modified?: boolean;
  modification_reason?: string;
}

export interface UpdateLineItemPayload {
  formula_qty?: number;
  requested_qty?: number;
  approved_qty?: number;
  is_modified?: boolean;
  modification_reason?: string;
  serial_no?: number;
  part_no?: string;
  unit?: string;
  item_description?: string;
}

export type RequirementPlanStatus = 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED' | string;

export interface MonthlyRequirementPlan {
  id: string;
  plant_id: string;
  month: number;
  year: number;
  status: RequirementPlanStatus;
  created_at?: string | null;
  updated_at?: string | null;
  line_items: RequirementLineItem[];
}

export interface BulkUploadResponse {
  total_rows: number;
  upserted: number;
  errors: string[];
  items: RequirementLineItem[];
  plants_affected?: string[];
}

export interface AggregatedRequirementRecord {
  id: string;
  month: number;
  year: number;
  consumable_id: string;
  total_gross_qty: number;
  net_purchase_qty: number;
  consumable_name?: string | null;
  item_id?: string | null;
  item_code?: string | null;
  item_description?: string | null;
  part_no?: string | null;
  unit?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AggregationRunResponse {
  month: number;
  year: number;
  total_approved_plans: number;
  total_aggregated_consumables: number;
  records: AggregatedRequirementRecord[];
}

export const requirementsClient = axios.create({
  baseURL: getApiBaseUrl(),
});

requirementsClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function fetchPlans(month?: number, year?: number): Promise<MonthlyRequirementPlan[]> {
  const hasParams = (month !== undefined && month !== null) || (year !== undefined && year !== null);
  const response = hasParams
    ? await requirementsClient.get<MonthlyRequirementPlan[]>('/api/v1/requirements/plans', {
        params: {
          ...(month !== undefined && month !== null ? { month } : {}),
          ...(year !== undefined && year !== null ? { year } : {}),
        },
      })
    : await requirementsClient.get<MonthlyRequirementPlan[]>('/api/v1/requirements/plans');
  return response.data;
}

export async function createPlan(plantId: string, month: number, year: number): Promise<MonthlyRequirementPlan> {
  const response = await requirementsClient.post<MonthlyRequirementPlan>('/api/v1/requirements/plans', {
    plant_id: plantId,
    month,
    year,
  });
  return response.data;
}

export async function createSingleLineItem(
  planId: string,
  payload: SingleLineItemPayload
): Promise<RequirementLineItem> {
  const response = await requirementsClient.post<RequirementLineItem>(
    `/api/v1/requirements/plans/${planId}/items/single`,
    payload
  );
  return response.data;
}

export async function updateLineItem(
  planId: string,
  itemId: string,
  payload: UpdateLineItemPayload
): Promise<RequirementLineItem> {
  const response = await requirementsClient.put<RequirementLineItem>(
    `/api/v1/requirements/plans/${planId}/items/${itemId}`,
    payload
  );
  return response.data;
}

export async function deleteLineItem(
  planId: string,
  itemId: string
): Promise<{ message: string; id: string }> {
  const response = await requirementsClient.delete<{ message: string; id: string }>(
    `/api/v1/requirements/plans/${planId}/items/${itemId}`
  );
  return response.data;
}

export async function bulkUploadItems(
  planId: string,
  file: File,
  uploadAllPlants: boolean = false
): Promise<BulkUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const url = uploadAllPlants
    ? `/api/v1/requirements/plans/${planId}/items/bulk?upload_all_plants=true`
    : `/api/v1/requirements/plans/${planId}/items/bulk`;
  const response = await requirementsClient.post<BulkUploadResponse>(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
}

export async function submitPlan(planId: string): Promise<MonthlyRequirementPlan> {
  const response = await requirementsClient.patch<MonthlyRequirementPlan>(`/api/v1/requirements/plans/${planId}/submit`);
  return response.data;
}

export async function approvePlan(planId: string): Promise<MonthlyRequirementPlan> {
  const response = await requirementsClient.patch<MonthlyRequirementPlan>(`/api/v1/requirements/plans/${planId}/approve`);
  return response.data;
}

export async function rejectPlan(planId: string, reason?: string): Promise<MonthlyRequirementPlan> {
  const response = await requirementsClient.patch<MonthlyRequirementPlan>(`/api/v1/requirements/plans/${planId}/reject`, { reason });
  return response.data;
}

export async function reopenPlan(planId: string): Promise<MonthlyRequirementPlan> {
  const response = await requirementsClient.patch<MonthlyRequirementPlan>(`/api/v1/requirements/plans/${planId}/reopen`);
  return response.data;
}

export interface FormulaGenerationResponse {
  month: number;
  year: number;
  plans_updated: string[];
  total_items_computed: number;
  message: string;
}

export async function calculateFormulas(
  month: number,
  year: number,
  plantId?: string
): Promise<FormulaGenerationResponse> {
  const response = await requirementsClient.post<FormulaGenerationResponse>(
    '/api/v1/requirements/plans/calculate-formulas',
    null,
    {
      params: {
        month,
        year,
        ...(plantId ? { plant_id: plantId } : {}),
      },
    }
  );
  return response.data;
}

export async function runAggregation(month: number, year: number): Promise<AggregationRunResponse> {
  const response = await requirementsClient.post<AggregationRunResponse>(`/api/v1/requirements/aggregate/${month}/${year}`);
  return response.data;
}

export async function fetchAggregatedRequirements(
  month: number,
  year: number
): Promise<AggregatedRequirementRecord[]> {
  const response = await requirementsClient.get<AggregatedRequirementRecord[]>(
    `/api/v1/requirements/aggregate/${month}/${year}`
  );
  return response.data;
}
