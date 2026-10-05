export interface ConsumptionNorm {
  id: string;
  rule_type: string;
  consumable_id: string;
  product_id?: string;
  process_id?: string;
  plant_id?: string;
  version: number;
  parameters: Record<string, any>;
  unit_id: string;
  rounding_policy: string;
  rounding_precision: number;
  effective_from: string;
  effective_to?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  consumable_code?: string;
  consumable_name?: string;
  product_code?: string;
  product_name?: string;
  process_name?: string;
  plant_name?: string;
  unit_code?: string;
}

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
