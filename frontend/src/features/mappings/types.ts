export interface ProductPlant {
  id: string;
  product_id: string;
  plant_id: string;
  route_id: string;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  product_code?: string;
  product_name?: string;
  plant_name?: string;
  route_name?: string;
}

export interface ProductProcessConsumable {
  id: string;
  product_id: string;
  process_id: string;
  consumable_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  product_code?: string;
  product_name?: string;
  process_name?: string;
  consumable_code?: string;
  consumable_name?: string;
  unit?: string;
}

export interface ResolvedConsumable {
  id: string;
  code: string;
  name: string;
  unit: string;
  is_active: boolean;
}

export interface ResolvedProcessStep {
  sequence_order: number;
  process_id: string;
  process_name: string;
  process_description?: string;
  consumables: ResolvedConsumable[];
}

export interface ResolvedPlantMapping {
  plant_id: string;
  plant_name: string;
  location?: string;
  is_primary: boolean;
  route_id: string;
  route_name: string;
  steps: ResolvedProcessStep[];
}

export interface ProductResolutionResponse {
  product_id: string;
  product_code: string;
  product_name: string;
  uom: string;
  plant_mappings: ResolvedPlantMapping[];
}

export interface MappingValidationIssue {
  issue_type: string;
  severity: string;
  product_id?: string;
  product_code?: string;
  plant_id?: string;
  process_id?: string;
  consumable_id?: string;
  message: string;
}

export interface MappingValidationReport {
  is_valid: boolean;
  total_products_checked: number;
  unmapped_products_count: number;
  issues: MappingValidationIssue[];
}

export interface MasterOption {
  id: string;
  code?: string;
  name: string;
}
