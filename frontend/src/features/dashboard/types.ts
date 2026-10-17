// TypeScript types for M6.3 — Executive Management Dashboard

export interface PipelineSummary {
  total_calculated_quantity: string;
  total_approved_additions: string;
  total_final_requirement: string;
  total_recommended_quantity: string;
  total_approved_purchase_quantity: string;
  total_ordered_quantity: string;
  total_accepted_grn_quantity: string;
}

export interface DashboardSummaryResponse {
  active_critical_alerts: number;
  active_warning_alerts: number;
  pending_purchase_approvals: number;
  pending_plant_adjustments: number;
  issued_pending_pos: number;
  total_active_consumables: number;
  pipeline_summary: PipelineSummary;
  as_of: string;
}
