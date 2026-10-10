// TypeScript types for M5.2 — Purchase Recommendation Review & Approval Queue
// Mirrors backend schemas/purchase_approval.py

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'MODIFIED' | 'REJECTED';

export interface SubmitPurchaseApprovalRequest {
  consumable_id: string;
  supplier_id: string;
  planning_version_id?: string | null;
  raw_calculated_qty: string;
  system_recommended_qty: string;
  uom: string;
  reason?: string | null;
}

export interface ReviewPurchaseApprovalRequest {
  action: 'APPROVE' | 'MODIFY' | 'REJECT';
  approved_qty?: string | null;
  reason?: string | null;
}

export interface PurchasePlanItem {
  id: string;
  plan_id: string;
  s_no?: number | null;
  item_id: string;
  description: string;
  req_type?: string | null;
  category?: string | null;
  type_of_material?: string | null;
  unit: string;
  purchasing_unit?: string | null;
  output_per_unit?: string | number | null;
  rate?: string | number | null;
  moq?: string | number | null;
  min_stock_level?: string | number | null;
  max_stock_level?: string | number | null;
  lead_time_days?: number | null;
  prev_opening_qty?: string | number | null;
  prev_opening_val?: string | number | null;
  prev_receipt_qty?: string | number | null;
  prev_issue_qty?: string | number | null;
  prev_closing_qty?: string | number | null;
  prev_closing_val?: string | number | null;
  prev_prd_qty?: string | number | null;
  sch_qty?: string | number | null;
  req_qty?: string | number | null;
  order_qty?: string | number | null;
  order_value?: string | number | null;
  receipt_qty?: string | number | null;
  receipt_value?: string | number | null;
  sch_qty_r2?: string | number | null;
  req_qty_r2?: string | number | null;
  order_qty_r2?: string | number | null;
  order_value_r2?: string | number | null;
  receipt_qty_r2?: string | number | null;
  receipt_val_r2?: string | number | null;
  pur_qty?: string | number | null;
  pur_value?: string | number | null;
  bal_pur_qty?: string | number | null;
  bal_pur_value?: string | number | null;
  supplier_id?: string | null;
  supplier_name?: string | null;
  part_no_saleable?: string | null;
  saleable_part_name?: string | null;
  used_part_no?: string | null;
  process_name?: string | null;
  thickness_gsm?: string | null;
  no_of_process_per_part?: string | number | null;
  plant_allocations?: Record<string, any>;
  consumption_analysis?: Record<string, any>;
  override_reason?: string | null;
  is_modified?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PurchasePlanResponse {
  id: string;
  planning_period: string;
  planning_version_id?: string | null;
  revision_label: string;
  status: string;
  msl_days_gas: number | string;
  msl_days_general: number | string;
  month_days: number;
  working_days: number;
  source_filename?: string | null;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
  modified_by?: string | null;
  modified_by_name?: string | null;
  modified_at?: string | null;
  total_items: number;
  total_order_value: number | string;
  items: PurchasePlanItem[];
}

export interface PurchaseApprovalResponse {
  id: string;
  consumable_id: string;
  consumable_code: string | null;
  consumable_name: string | null;
  supplier_id: string;
  supplier_code: string | null;
  supplier_name: string | null;
  planning_version_id: string | null;
  rule_version: string;
  raw_calculated_qty: string;
  system_recommended_qty: string;
  approved_qty: string | null;
  uom: string;
  status: ApprovalStatus;
  reason: string | null;
  requested_by: string | null;
  requested_by_username: string | null;
  reviewed_by: string | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanInspectResult {
  filename: string;
  detected_view: 'NORMAL_VIEW' | 'MD_VIEW' | 'UNKNOWN';
  sheet_name: string;
  total_rows: number;
  total_columns: number;
  headers: string[];
  missing_required_headers: string[];
  validation_errors: Array<{ row: number; column: string; error: string }>;
  sample_rows: Array<Record<string, any>>;
}

