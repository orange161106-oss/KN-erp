export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type Movement = 'RECEIPT' | 'ISSUE' | 'RETURN';
export type InventoryStatus = { source: string; mode: string; is_live: false; import_enabled: boolean; warehouse_posting: false; msl_alert_policy: 'TBD' };
export type Balance = {
  consumable_id: string; code: string; name: string; is_active: boolean; unit_id: string; unit_code: string;
  usable_quantity: string | null; as_of: string | null; imported_at: string | null;
  source_export_id: string | null; availability: 'REPORTED' | 'NOT_IMPORTED'; is_live: false;
};
export type StockTransaction = {
  id: string; source_event_id: string; consumable_id: string; code: string; name: string;
  unit_id: string; unit_code: string; source_unit_id: string; source_unit_code: string;
  source_quantity: string; conversion_factor: string; conversion_reference: string | null;
  movement: Movement; quantity: string; signed_quantity: string; event_at: string; source_actor: string;
  imported_at: string; imported_by: string; source_export_id: string;
};
export type ImportResult = { id: string; export_id: string; movement_count: number; snapshot_count: number; replayed: boolean; imported_at: string };
export const endpoint = '/api/v1/inventory';
