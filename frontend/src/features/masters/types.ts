export type Resource = 'units' | 'consumables' | 'suppliers';
export interface Master { id: string; code: string; name: string; is_active: boolean; created_at: string; updated_at: string; description?: string | null; unit_id?: string; }
export interface Mapping { id: string; supplier_id: string; consumable_id: string; is_active: boolean; }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number; }
export const titles: Record<Resource, string> = { units: 'Units', consumables: 'Consumables', suppliers: 'Suppliers' };
export const endpoint = (resource: string) => `/api/v1/masters/${resource}`;
