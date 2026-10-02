// TypeScript types for M3.4 — Plant Workflow
// Mirrors backend schemas/plant_workflow.py

export type AdjustmentCategory =
  | 'SPECIAL'
  | 'MAINTENANCE'
  | 'TRIAL'
  | 'REWORK'
  | 'PLANT_REQUEST'
  | 'OTHER';

export type AdjustmentStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

// ── User↔Plant ──────────────────────────────────────────────────────────────

export interface UserPlantResponse {
  id: string;
  user_id: string;
  plant_id: string;
  assigned_at: string;
  assigned_by: string | null;
}

// ── Plant Confirmation ───────────────────────────────────────────────────────

export interface ConfirmRequirementRequest {
  calculated_requirement_id: string;
  notes?: string | null;
}

export interface PlantConfirmationResponse {
  id: string;
  calculated_requirement_id: string;
  planning_version_id: string;
  plant_id: string;
  plant_name: string | null;
  confirmed_by: string;
  confirmed_by_username: string | null;
  confirmed_at: string;
  notes: string | null;
}

// ── Requirement Adjustment ───────────────────────────────────────────────────

export interface SubmitAdjustmentRequest {
  planning_version_id: string;
  plant_id: string;
  consumable_id: string;
  category: AdjustmentCategory;
  requested_qty: string; // send as string to preserve decimal precision
  reason: string;
}

export interface RequirementAdjustmentResponse {
  id: string;
  planning_version_id: string;
  plant_id: string;
  plant_name: string | null;
  consumable_id: string;
  consumable_code: string | null;
  consumable_name: string | null;
  category: AdjustmentCategory;
  requested_qty: string;
  uom: string;
  reason: string;
  requested_by: string;
  requested_by_username: string | null;
  requested_at: string;
  status: AdjustmentStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  reviewer_comment: string | null;
}

// ── Calculated Requirement (read from Yathish's domain, read-only) ───────────

export interface CalculatedRequirementItem {
  id: string;
  planning_version_id: string;
  plant_id: string;
  plant_name: string | null;
  consumable_id: string;
  consumable_code: string | null;
  consumable_name: string | null;
  process_id: string;
  process_name: string | null;
  calculated_qty: string;
  uom: string;
  rule_type: string;
  explanation_payload: Record<string, unknown>;
}

export interface ReviewAdjustmentRequest {
  status: 'APPROVED' | 'REJECTED';
  reviewer_comment?: string | null;
}

export interface FinalRequirementItemResponse {
  planning_version_id: string;
  plant_id: string;
  plant_name: string | null;
  consumable_id: string;
  consumable_code: string | null;
  consumable_name: string | null;
  uom: string;
  calculated_qty: string;
  approved_adjustment_qty: string;
  final_required_qty: string;
  is_fully_confirmed: boolean;
}

