// TypeScript types for M4.4 — Inventory Alerts Workflow
// Mirrors backend schemas/alerts.py

export type AlertType = 'BELOW_MSL' | 'LOW_STOCK' | 'REORDER_REQUIRED' | 'PO_DELAY' | 'PO_DUE_SOON' | 'PO_OVERDUE';
export type AlertSeverity = 'CRITICAL' | 'WARNING' | 'INFO';
export type AlertStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';

export interface InventoryAlertResponse {
  id: string;
  consumable_id: string;
  consumable_code: string | null;
  consumable_name: string | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  current_stock: string;
  threshold_qty: string;
  uom: string;
  message: string;
  status: AlertStatus;
  acknowledged_by: string | null;
  acknowledged_by_username: string | null;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertEvaluationSummaryResponse {
  total_evaluated: number;
  alerts_created: number;
  alerts_updated: number;
  active_critical_count: number;
  active_warning_count: number;
  active_info_count: number;
}
