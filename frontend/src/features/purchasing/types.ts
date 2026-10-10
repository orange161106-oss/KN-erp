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
