export interface ConsumptionNorm {
  id: string;
  rule_type: string;
  consumable_id: string;
  product_id?: string | null;
  process_id?: string | null;
  plant_id?: string | null;
  version: number;
  parameters: Record<string, any>;
  unit_id: string;
  rounding_policy: string;
  rounding_precision: number;
  effective_from: string;
  effective_to?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  consumable_code?: string;
  consumable_name?: string;
  product_code?: string;
  product_name?: string;
  product_part_number?: string | null;
  product_item_id?: string | null;
  process_name?: string;
  plant_name?: string;
  unit_code?: string;
  reference_data?: NormReferenceData | null;
}

export interface NormReferenceData {
  part_number?: string | null;
  part_name?: string | null;
  used_part_number?: string | null;
  thickness?: string | null;
  process_count?: string | null;
  reference_production_qty?: string | null;
  reference_schedule_qty?: string | null;
  source_filename?: string | null;
  source_sha256?: string | null;
  source_row?: number | null;
}

export interface NormImportRow {
  row_number: number;
  part_number: string | null;
  part_name: string | null;
  used_part_number: string | null;
  consumable_code: string | null;
  consumable_name: string | null;
  process_name: string | null;
  thickness: string | null;
  process_count: string | null;
  reference_production_qty: string | null;
  reference_schedule_qty: string | null;
  product_id?: string | null;
  consumable_id?: string | null;
  process_id?: string | null;
  unit_id?: string | null;
  unit_code?: string | null;
  action: 'CREATE' | 'EXISTING' | 'CONFLICT' | 'INVALID';
  errors: Array<{ field: string; code: string; message: string }>;
}

export interface NormImportPreview {
  filename: string;
  source_sha256: string;
  review_token: string;
  sheet_name: string;
  row_count: number;
  valid_count: number;
  invalid_count: number;
  duplicate_count: number;
  existing_count: number;
  conflict_count: number;
  rows: NormImportRow[];
}

export const NORM_ENDPOINT = '/api/v1/consumption-norms';

export interface EvaluationResult {
  norm_id: string;
  calculation: {
    rule_type: string;
    rule_version: number;
    parameters: Record<string, any>;
    source_production_qty: number | string;
    calculation_steps: Array<{
      step_number: number;
      description: string;
      formula: string;
      result: number | string;
    }>;
    raw_requirement: number | string;
    rounding_policy: string;
    rounding_precision: number;
    final_calculated_requirement: number | string;
    unit: string;
  };
}
