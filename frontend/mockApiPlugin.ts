import type { Plugin } from 'vite';

const MOCK_USER = {
  id: 'usr-admin-01',
  username: 'admin',
  roles: ['ADMIN', 'PLANNER', 'PLANT_INCHARGE', 'STORE', 'PURCHASE', 'APPROVER', 'MANAGEMENT'],
  permissions: [
    'masters.units.read', 'masters.units.write',
    'masters.consumables.read', 'masters.consumables.write',
    'masters.suppliers.read', 'masters.suppliers.write',
    'masters.supplier_consumables.read', 'masters.supplier_consumables.write',
    'inventory.stock.read', 'inventory.stock.import',
    'purchase.orders.read', 'purchase.orders.write',
    'purchase.grns.read', 'purchase.grns.import',
    'alerts:view', 'purchasing:view',
  ],
  is_super_admin: true,
  is_superuser: true,
  masters_read: true,
  masters_create: true,
  masters_update: true,
  masters_delete: true,
  production_mappings_read: true,
  production_mappings_create: true,
  production_mappings_update: true,
  production_mappings_delete: true,
  consumption_norms_read: true,
  consumption_norms_create: true,
  consumption_norms_update: true,
  consumption_norms_delete: true,
  prd_planning_read: true,
  prd_planning_create: true,
  prd_planning_update: true,
  prd_planning_delete: true,
  requirements_read: true,
  requirements_create: true,
  requirements_update: true,
  requirements_delete: true,
  plant_workflow_read: true,
  plant_workflow_create: true,
  plant_workflow_update: true,
  plant_workflow_delete: true,
  inventory_read: true,
  inventory_create: true,
  inventory_update: true,
  inventory_delete: true,
  purchase_read: true,
  purchase_create: true,
  purchase_update: true,
  purchase_delete: true,
  purchase_orders_read: true,
  purchase_orders_create: true,
  purchase_orders_update: true,
  purchase_orders_delete: true,
  goods_receipts_read: true,
  goods_receipts_create: true,
  goods_receipts_update: true,
  goods_receipts_delete: true,
  can_access_plant_1: true,
  can_access_plant_2: true,
  can_access_plant_3: true,
  can_access_plant_4: true,
  can_access_plant_5: true,
  can_access_dashboard: true,
  alert_production: true,
  alert_inventory: true,
  alert_purchasing: true,
  alert_system: true,
  can_view_master_data: true,
  can_view_planning: true,
  can_run_calculations: true,
  can_confirm_demand: true,
  can_approve_po: true,
  can_create_po: true,
  can_upload_grn: true,
  can_view_reports: true,
};

const MOCK_UNITS = [
  { id: 'u-1', code: 'KG', name: 'Kilograms', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'u-2', code: 'L', name: 'Litres', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'u-3', code: 'PCS', name: 'Pieces', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'u-4', code: 'M', name: 'Metres', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'u-5', code: 'BOX', name: 'Boxes', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
];

const MOCK_CONSUMABLES = [
  { id: 'c-1', code: 'CS-ST-004', name: 'Cold-Rolled Steel Strip 1.2mm', unit_id: 'u-1', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'c-2', code: 'CS-FAST-018', name: 'Hex Flange Bolt M8x35 Grade 8.8', unit_id: 'u-3', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'c-3', code: 'CS-LUB-002', name: 'Industrial Synthetic Gear Oil ISO VG 220', unit_id: 'u-2', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'c-4', code: 'CS-PKG-012', name: 'Heavy-Duty Corrugated Carton Box (Box-L)', unit_id: 'u-5', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'c-5', code: 'CS-WELD-007', name: 'MIG Welding Wire ER70S-6 1.2mm Spool', unit_id: 'u-1', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
];

const MOCK_SUPPLIERS = [
  { id: 's-1', code: 'SUP-TATA-01', name: 'Tata Steel Special Materials Ltd', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 's-2', code: 'SUP-SNDR-02', name: 'Sundram Fasteners Industrial Corp', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 's-3', code: 'SUP-CAST-03', name: 'Castrol Lubricants India Pvt Ltd', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 's-4', code: 'SUP-MOD-04', name: 'Modern Pack & Boxes Ltd', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
];

const MOCK_PRODUCTS = [
  { id: 'p-1', code: 'PRD-FRAME-01', name: 'Automotive Sub-Frame Assembly Mark II', is_active: true, uom: 'PCS' },
  { id: 'p-2', code: 'PRD-GEAR-02', name: 'Heavy Transmission Gearbox Casing 4WD', is_active: true, uom: 'PCS' },
  { id: 'p-3', code: 'PRD-BRAKE-03', name: 'Ventilated Disc Brake Rotor High-Carbon', is_active: true, uom: 'PCS' },
];

const MOCK_ALERTS = [
  {
    id: 'alt-1',
    consumable_id: 'c-1',
    consumable_code: 'CS-ST-004',
    consumable_name: 'Cold-Rolled Steel Strip 1.2mm',
    alert_type: 'BELOW_MSL',
    severity: 'CRITICAL',
    current_stock: '142.50',
    threshold_qty: '350.00',
    uom: 'KG',
    message: 'Stock level 142.50 KG has breached the Minimum Stock Level (MSL) floor of 350.00 KG.',
    status: 'ACTIVE',
    acknowledged_by: null,
    acknowledged_by_username: null,
    acknowledged_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'alt-2',
    consumable_id: 'c-2',
    consumable_code: 'CS-FAST-018',
    consumable_name: 'Hex Flange Bolt M8x35 Grade 8.8',
    alert_type: 'LOW_STOCK',
    severity: 'CRITICAL',
    current_stock: '420.00',
    threshold_qty: '800.00',
    uom: 'PCS',
    message: 'Production run consumption exceeds standard norm. Remaining stock below floor.',
    status: 'ACTIVE',
    acknowledged_by: null,
    acknowledged_by_username: null,
    acknowledged_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'alt-3',
    consumable_id: 'c-3',
    consumable_code: 'CS-LUB-002',
    consumable_name: 'Industrial Synthetic Gear Oil ISO VG 220',
    alert_type: 'REORDER_REQUIRED',
    severity: 'WARNING',
    current_stock: '65.00',
    threshold_qty: '100.00',
    uom: 'L',
    message: 'Current stock 65.00 L is within lead-time threshold. Purchase reorder advised.',
    status: 'ACTIVE',
    acknowledged_by: null,
    acknowledged_by_username: null,
    acknowledged_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const MOCK_APPROVALS = [
  {
    id: 'appr-1',
    recommendation_id: 'rec-1',
    consumable_id: 'c-1',
    consumable_code: 'CS-ST-004',
    consumable_name: 'Cold-Rolled Steel Strip 1.2mm',
    recommended_quantity: '250.00',
    approved_quantity: '250.00',
    uom: 'KG',
    target_supplier_id: 's-1',
    target_supplier_name: 'Tata Steel Special Materials Ltd',
    status: 'PENDING',
    urgency: 'HIGH',
    created_at: new Date().toISOString(),
  },
  {
    id: 'appr-2',
    recommendation_id: 'rec-2',
    consumable_id: 'c-2',
    consumable_code: 'CS-FAST-018',
    consumable_name: 'Hex Flange Bolt M8x35 Grade 8.8',
    recommended_quantity: '600.00',
    approved_quantity: '600.00',
    uom: 'PCS',
    target_supplier_id: 's-2',
    target_supplier_name: 'Sundram Fasteners Industrial Corp',
    status: 'PENDING',
    urgency: 'HIGH',
    created_at: new Date().toISOString(),
  },
];

const MOCK_PLAN_ITEMS = [
  {
    id: 'plan-item-1',
    plan_id: 'plan-2026-10',
    s_no: 1,
    item_id: 'CS-ST-004',
    description: 'Cold-Rolled Steel Strip 1.2mm Grade D',
    req_type: 'PRODUCTION CONSUMABLES',
    category: 'Sheet Metal & Coil',
    type_of_material: 'Steel Strip',
    unit: 'KG',
    purchasing_unit: 'KG',
    output_per_unit: '1.00',
    rate: '45.00',
    moq: '200.00',
    min_stock_level: '350.00',
    max_stock_level: '800.00',
    lead_time_days: 12,
    prev_opening_qty: '220.00',
    prev_opening_val: '9900.00',
    prev_receipt_qty: '180.00',
    prev_issue_qty: '257.50',
    prev_closing_qty: '142.50',
    prev_closing_val: '6412.50',
    prev_prd_qty: '500.00',
    sch_qty: '500.00',
    req_qty: '225.00',
    order_qty: '432.50',
    order_value: '19462.50',
    receipt_qty: '0.00',
    receipt_value: '0.00',
    sch_qty_r2: '500.00',
    req_qty_r2: '225.00',
    order_qty_r2: '432.50',
    order_value_r2: '19462.50',
    receipt_qty_r2: '0.00',
    receipt_val_r2: '0.00',
    pur_qty: '0.00',
    pur_value: '0.00',
    bal_pur_qty: '432.50',
    bal_pur_value: '19462.50',
    supplier_id: 'SUP-TATA-01',
    supplier_name: 'Tata Steel Special Materials Ltd',
    part_no_saleable: 'PRD-FRAME-01',
    saleable_part_name: 'Sub-Frame Assembly Mark II',
    used_part_no: 'PO-2026-90',
    process_name: 'Stamping & Seam Welding',
    thickness_gsm: '1.20 mm',
    no_of_process_per_part: '2.00',
    plant_allocations: {
      p1: '180.00', p2: '120.00', p3: '80.00', p4: '52.50', p5: '0.00',
      tool_room: '0.00', quality: '0.00', pmd: '0.00', npd: '0.00', hrd: '0.00',
      accounts: '0.00', admin: '0.00', sales: '0.00', req_by_users: '432.50', total_value: '19462.50'
    },
    consumption_analysis: {
      avg_monthly_con: '240.00', avg_daily_con: '8.89', hold_days: 16, lead_time_qty: '106.67',
      reorder_level: '456.67', cost_of_msl: '15750.00', prev_plan_val: '18000.00', prev_actual_val: '17200.00'
    },
    override_reason: null,
    is_modified: false,
    created_at: '2026-10-01T04:00:00Z',
    updated_at: '2026-10-01T04:00:00Z',
  },
  {
    id: 'plan-item-2',
    plan_id: 'plan-2026-10',
    s_no: 2,
    item_id: 'CS-FAST-018',
    description: 'Hex Flange Bolt M8x35 Grade 8.8 Zinc Plated',
    req_type: 'PRODUCTION CONSUMABLES',
    category: 'Fasteners & Hardware',
    type_of_material: 'Fasteners',
    unit: 'PCS',
    purchasing_unit: 'PCS',
    output_per_unit: '8.00',
    rate: '3.50',
    moq: '500.00',
    min_stock_level: '800.00',
    max_stock_level: '2000.00',
    lead_time_days: 7,
    prev_opening_qty: '750.00',
    prev_opening_val: '2625.00',
    prev_receipt_qty: '500.00',
    prev_issue_qty: '830.00',
    prev_closing_qty: '420.00',
    prev_closing_val: '1470.00',
    prev_prd_qty: '100.00',
    sch_qty: '120.00',
    req_qty: '960.00',
    order_qty: '1340.00',
    order_value: '4690.00',
    receipt_qty: '0.00',
    receipt_value: '0.00',
    sch_qty_r2: '120.00',
    req_qty_r2: '960.00',
    order_qty_r2: '1340.00',
    order_value_r2: '4690.00',
    receipt_qty_r2: '0.00',
    receipt_val_r2: '0.00',
    pur_qty: '0.00',
    pur_value: '0.00',
    bal_pur_qty: '1340.00',
    bal_pur_value: '4690.00',
    supplier_id: 'SUP-SNDR-02',
    supplier_name: 'Sundram Fasteners Industrial Corp',
    part_no_saleable: 'PRD-FRAME-01',
    saleable_part_name: 'Sub-Frame Assembly Mark II',
    used_part_no: 'PO-2026-90',
    process_name: 'Final Chassis Bolting',
    thickness_gsm: 'M8 x 35',
    no_of_process_per_part: '8.00',
    plant_allocations: {
      p1: '600.00', p2: '400.00', p3: '340.00', p4: '0.00', p5: '0.00',
      tool_room: '0.00', quality: '0.00', pmd: '0.00', npd: '0.00', hrd: '0.00',
      accounts: '0.00', admin: '0.00', sales: '0.00', req_by_users: '1340.00', total_value: '4690.00'
    },
    consumption_analysis: {
      avg_monthly_con: '900.00', avg_daily_con: '33.33', hold_days: 12, lead_time_qty: '233.33',
      reorder_level: '1033.33', cost_of_msl: '2800.00', prev_plan_val: '4200.00', prev_actual_val: '4500.00'
    },
    override_reason: null,
    is_modified: false,
    created_at: '2026-10-01T04:00:00Z',
    updated_at: '2026-10-01T04:00:00Z',
  },
  {
    id: 'plan-item-3',
    plan_id: 'plan-2026-10',
    s_no: 3,
    item_id: 'CS-LUB-002',
    description: 'Industrial Synthetic Gear Oil ISO VG 220 Drum',
    req_type: 'MAINTENANCE CONSUMABLES',
    category: 'Lubricants & Coolants',
    type_of_material: 'Gear Oil',
    unit: 'L',
    purchasing_unit: 'L',
    output_per_unit: '0.50',
    rate: '280.00',
    moq: '50.00',
    min_stock_level: '100.00',
    max_stock_level: '300.00',
    lead_time_days: 10,
    prev_opening_qty: '95.00',
    prev_opening_val: '26600.00',
    prev_receipt_qty: '50.00',
    prev_issue_qty: '80.00',
    prev_closing_qty: '65.00',
    prev_closing_val: '18200.00',
    prev_prd_qty: '60.00',
    sch_qty: '80.00',
    req_qty: '40.00',
    order_qty: '75.00',
    order_value: '21000.00',
    receipt_qty: '0.00',
    receipt_value: '0.00',
    sch_qty_r2: '80.00',
    req_qty_r2: '40.00',
    order_qty_r2: '75.00',
    order_value_r2: '21000.00',
    receipt_qty_r2: '0.00',
    receipt_val_r2: '0.00',
    pur_qty: '0.00',
    pur_value: '0.00',
    bal_pur_qty: '75.00',
    bal_pur_value: '21000.00',
    supplier_id: 'SUP-CAST-03',
    supplier_name: 'Castrol Lubricants India Pvt Ltd',
    part_no_saleable: 'PRD-GEAR-02',
    saleable_part_name: 'Heavy Transmission Gearbox Casing 4WD',
    used_part_no: 'PO-2026-92',
    process_name: 'CNC 5-Axis Milling & Lubrication',
    thickness_gsm: 'VG 220',
    no_of_process_per_part: '1.00',
    plant_allocations: {
      p1: '25.00', p2: '50.00', p3: '0.00', p4: '0.00', p5: '0.00',
      tool_room: '0.00', quality: '0.00', pmd: '0.00', npd: '0.00', hrd: '0.00',
      accounts: '0.00', admin: '0.00', sales: '0.00', req_by_users: '75.00', total_value: '21000.00'
    },
    consumption_analysis: {
      avg_monthly_con: '50.00', avg_daily_con: '1.85', hold_days: 35, lead_time_qty: '18.52',
      reorder_level: '118.52', cost_of_msl: '28000.00', prev_plan_val: '19000.00', prev_actual_val: '21000.00'
    },
    override_reason: null,
    is_modified: false,
    created_at: '2026-10-01T04:00:00Z',
    updated_at: '2026-10-01T04:00:00Z',
  },
  {
    id: 'plan-item-4',
    plan_id: 'plan-2026-10',
    s_no: 4,
    item_id: 'CS-PKG-012',
    description: 'Heavy-Duty Corrugated Carton Box (Box-L)',
    req_type: 'PACKING CONSUMABLES',
    category: 'Packaging Materials',
    type_of_material: 'Carton Box',
    unit: 'BOX',
    purchasing_unit: 'BOX',
    output_per_unit: '1.00',
    rate: '38.00',
    moq: '100.00',
    min_stock_level: '250.00',
    max_stock_level: '600.00',
    lead_time_days: 5,
    prev_opening_qty: '300.00',
    prev_opening_val: '11400.00',
    prev_receipt_qty: '200.00',
    prev_issue_qty: '320.00',
    prev_closing_qty: '180.00',
    prev_closing_val: '6840.00',
    prev_prd_qty: '300.00',
    sch_qty: '400.00',
    req_qty: '400.00',
    order_qty: '470.00',
    order_value: '17860.00',
    receipt_qty: '0.00',
    receipt_value: '0.00',
    sch_qty_r2: '400.00',
    req_qty_r2: '400.00',
    order_qty_r2: '470.00',
    order_value_r2: '17860.00',
    receipt_qty_r2: '0.00',
    receipt_val_r2: '0.00',
    pur_qty: '0.00',
    pur_value: '0.00',
    bal_pur_qty: '470.00',
    bal_pur_value: '17860.00',
    supplier_id: 'SUP-MOD-04',
    supplier_name: 'Modern Pack & Boxes Ltd',
    part_no_saleable: 'PRD-FRAME-01',
    saleable_part_name: 'Sub-Frame Assembly Mark II',
    used_part_no: 'PO-2026-90',
    process_name: 'Finished Goods Packaging',
    thickness_gsm: '5-Ply 180 GSM',
    no_of_process_per_part: '1.00',
    plant_allocations: {
      p1: '250.00', p2: '120.00', p3: '100.00', p4: '0.00', p5: '0.00',
      tool_room: '0.00', quality: '0.00', pmd: '0.00', npd: '0.00', hrd: '0.00',
      accounts: '0.00', admin: '0.00', sales: '0.00', req_by_users: '470.00', total_value: '17860.00'
    },
    consumption_analysis: {
      avg_monthly_con: '350.00', avg_daily_con: '12.96', hold_days: 14, lead_time_qty: '64.81',
      reorder_level: '314.81', cost_of_msl: '9500.00', prev_plan_val: '13300.00', prev_actual_val: '12800.00'
    },
    override_reason: null,
    is_modified: false,
    created_at: '2026-10-01T04:00:00Z',
    updated_at: '2026-10-01T04:00:00Z',
  },
  {
    id: 'plan-item-5',
    plan_id: 'plan-2026-10',
    s_no: 5,
    item_id: 'CS-WELD-007',
    description: 'MIG Welding Wire ER70S-6 1.2mm 15kg Spool',
    req_type: 'WELDING CONSUMABLES',
    category: 'Welding Wire & Electrodes',
    type_of_material: 'Welding Wire',
    unit: 'KG',
    purchasing_unit: 'KG',
    output_per_unit: '0.35',
    rate: '115.00',
    moq: '150.00',
    min_stock_level: '300.00',
    max_stock_level: '750.00',
    lead_time_days: 8,
    prev_opening_qty: '280.00',
    prev_opening_val: '32200.00',
    prev_receipt_qty: '300.00',
    prev_issue_qty: '290.00',
    prev_closing_qty: '290.00',
    prev_closing_val: '33350.00',
    prev_prd_qty: '500.00',
    sch_qty: '500.00',
    req_qty: '175.00',
    order_qty: '185.00',
    order_value: '21275.00',
    receipt_qty: '0.00',
    receipt_value: '0.00',
    sch_qty_r2: '500.00',
    req_qty_r2: '175.00',
    order_qty_r2: '185.00',
    order_value_r2: '21275.00',
    receipt_qty_r2: '0.00',
    receipt_val_r2: '0.00',
    pur_qty: '0.00',
    pur_value: '0.00',
    bal_pur_qty: '185.00',
    bal_pur_value: '21275.00',
    supplier_id: 'SUP-TATA-01',
    supplier_name: 'Tata Steel Special Materials Ltd',
    part_no_saleable: 'PRD-FRAME-01',
    saleable_part_name: 'Sub-Frame Assembly Mark II',
    used_part_no: 'PO-2026-90',
    process_name: 'Robotic MIG Welding Line',
    thickness_gsm: '1.20 mm Dia',
    no_of_process_per_part: '1.00',
    plant_allocations: {
      p1: '120.00', p2: '65.00', p3: '0.00', p4: '0.00', p5: '0.00',
      tool_room: '0.00', quality: '0.00', pmd: '0.00', npd: '0.00', hrd: '0.00',
      accounts: '0.00', admin: '0.00', sales: '0.00', req_by_users: '185.00', total_value: '21275.00'
    },
    consumption_analysis: {
      avg_monthly_con: '280.00', avg_daily_con: '10.37', hold_days: 28, lead_time_qty: '82.96',
      reorder_level: '382.96', cost_of_msl: '34500.00', prev_plan_val: '20000.00', prev_actual_val: '21500.00'
    },
    override_reason: null,
    is_modified: false,
    created_at: '2026-10-01T04:00:00Z',
    updated_at: '2026-10-01T04:00:00Z',
  },
];

const MOCK_PURCHASE_PLAN = {
  id: 'plan-2026-10',
  planning_period: '2026-10',
  planning_version_id: 'pv-2026-10-r1',
  revision_label: 'R1',
  status: 'CALCULATED',
  msl_days_gas: '2.0',
  msl_days_general: '10.0',
  month_days: 31,
  working_days: 27,
  source_filename: 'KNL_Consumables_Plan_Oct26.xlsx',
  created_by: 'usr-admin-01',
  created_by_name: 'admin',
  created_at: '2026-10-01T04:00:00Z',
  modified_by: 'usr-admin-01',
  modified_by_name: 'admin',
  modified_at: '2026-10-01T06:15:00Z',
  total_items: 5,
  total_order_value: '84287.50',
  items: MOCK_PLAN_ITEMS,
};

export function mockApiPlugin(): Plugin {
  return {
    name: 'knl-mock-api',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || '';
        if (!url.startsWith('/api/')) {
          return next();
        }

        const method = req.method || 'GET';
        res.setHeader('Content-Type', 'application/json');

        // Health
        if (url === '/api/v1/health') {
          res.end(JSON.stringify({ status: 'ok', version: '0.1.0' }));
          return;
        }

        // Auth
        if (url === '/api/v1/auth/login' && method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', () => {
            let parsed = { username: 'admin' };
            try { parsed = JSON.parse(body); } catch { /* ignore */ }
            const user = { ...MOCK_USER, username: parsed.username || 'admin' };
            res.end(JSON.stringify({
              access_token: 'mock-knl-jwt-token',
              token_type: 'bearer',
              user,
            }));
          });
          return;
        }

        if (url === '/api/v1/auth/me') {
          res.end(JSON.stringify(MOCK_USER));
          return;
        }

        // Reports Dashboard
        if (url.startsWith('/api/v1/reports/dashboard-summary')) {
          res.end(JSON.stringify({
            total_active_consumables: 142,
            active_critical_alerts: 2,
            active_warning_alerts: 5,
            pending_purchase_approvals: 3,
            open_purchase_orders: 8,
            stock_health_percentage: 92.4,
            mtd_consumption_variance: '+1.8%',
            inventory_valuation: '₹ 42,85,600',
          }));
          return;
        }

        // Alerts
        if (url.startsWith('/api/v1/alerts/evaluate') && method === 'POST') {
          res.end(JSON.stringify({
            total_evaluated: 142,
            alerts_created: 0,
            alerts_updated: 3,
            active_critical_count: 2,
            active_warning_count: 1,
            active_info_count: 0,
          }));
          return;
        }

        if (url.startsWith('/api/v1/alerts')) {
          res.end(JSON.stringify(MOCK_ALERTS));
          return;
        }

        // Masters: Units
        if (url.startsWith('/api/v1/masters/units')) {
          res.end(JSON.stringify({ items: MOCK_UNITS, total: MOCK_UNITS.length, limit: 25, offset: 0 }));
          return;
        }

        // Masters: Consumables
        if (url.startsWith('/api/v1/masters/consumables')) {
          res.end(JSON.stringify({ items: MOCK_CONSUMABLES, total: MOCK_CONSUMABLES.length, limit: 25, offset: 0 }));
          return;
        }

        // Masters: Suppliers
        if (url.startsWith('/api/v1/masters/suppliers')) {
          res.end(JSON.stringify({ items: MOCK_SUPPLIERS, total: MOCK_SUPPLIERS.length, limit: 25, offset: 0 }));
          return;
        }

        // Masters: Products
        if (url.startsWith('/api/v1/masters/products')) {
          res.end(JSON.stringify(MOCK_PRODUCTS));
          return;
        }

        // Mappings: Product-Plants
        if (url.startsWith('/api/v1/mappings/product-plants')) {
          res.end(JSON.stringify([
            { id: 'pp-1', product_id: 'p-1', product_code: 'PRD-FRAME-01', product_name: 'Automotive Sub-Frame Assembly Mark II', plant_id: 'pl-1', plant_name: 'Plant 1 - Chassis Fabrication', route_id: 'rt-1', route_name: 'Primary Stamping & Welding Line', is_primary: true, is_active: true },
            { id: 'pp-2', product_id: 'p-2', product_code: 'PRD-GEAR-02', product_name: 'Heavy Transmission Gearbox Casing 4WD', plant_id: 'pl-2', plant_name: 'Plant 2 - Precision Machining', route_id: 'rt-2', route_name: 'CNC 5-Axis Milling Line', is_primary: true, is_active: true },
          ]));
          return;
        }

        // Mappings: Product-Process-Consumables
        if (url.startsWith('/api/v1/mappings/product-process-consumables')) {
          res.end(JSON.stringify([
            { id: 'ppc-1', product_id: 'p-1', product_code: 'PRD-FRAME-01', product_name: 'Automotive Sub-Frame', process_id: 'pr-1', process_name: 'MIG Welding', consumable_id: 'c-5', consumable_code: 'CS-WELD-007', consumable_name: 'MIG Welding Wire ER70S-6', unit: 'KG', is_active: true },
            { id: 'ppc-2', product_id: 'p-2', product_code: 'PRD-GEAR-02', product_name: 'Gearbox Casing', process_id: 'pr-2', process_name: 'Gear Hobbing & Lubrication', consumable_id: 'c-3', consumable_code: 'CS-LUB-002', consumable_name: 'Industrial Synthetic Gear Oil', unit: 'L', is_active: true },
          ]));
          return;
        }

        // Mappings: Validate
        if (url.startsWith('/api/v1/mappings/validate')) {
          res.end(JSON.stringify({
            is_valid: true,
            total_products_checked: 3,
            unmapped_products_count: 0,
            issues: [],
          }));
          return;
        }

        // Mappings: Resolve
        if (url.startsWith('/api/v1/mappings/resolve/')) {
          res.end(JSON.stringify({
            product_id: 'p-1',
            product_code: 'PRD-FRAME-01',
            product_name: 'Automotive Sub-Frame Assembly Mark II',
            uom: 'PCS',
            plant_mappings: [
              {
                plant_id: 'pl-1',
                plant_name: 'Plant 1 - Chassis Fabrication',
                location: 'Unit A, Industrial Area',
                route_id: 'rt-1',
                route_name: 'Primary Stamping & Welding Line',
                is_primary: true,
                steps: [
                  {
                    process_id: 'pr-1',
                    process_name: 'Robotic MIG Welding & Fixture Jointing',
                    process_description: 'High-amperage robotic seam welding of structural members',
                    sequence_order: 1,
                    consumables: [
                      { id: 'c-5', code: 'CS-WELD-007', name: 'MIG Welding Wire ER70S-6 1.2mm Spool', unit: 'KG' },
                    ],
                  },
                ],
              },
            ],
          }));
          return;
        }

        // Consumption Norms
        if (url.startsWith('/api/v1/consumption-norms/evaluate') && method === 'POST') {
          res.end(JSON.stringify({
            rule_type: 'PRODUCTION_RATE',
            input_rate: '0.045000',
            production_quantity: '1000.00',
            required_quantity: '45.000000',
            scrap_allowance_percent: '3.00',
            scrap_quantity: '1.350000',
            total_calculated_quantity: '46.350000',
            unit_code: 'KG',
            notes: 'Calculated using base production rate with 3% scrap allowance factor.',
          }));
          return;
        }

        if (url.startsWith('/api/v1/consumption-norms')) {
          res.end(JSON.stringify([
            { id: 'norm-1', consumable_id: 'c-1', consumable_code: 'CS-ST-004', consumable_name: 'Cold-Rolled Steel Strip 1.2mm', rule_type: 'PRODUCTION_RATE', rate_per_unit: '0.125', unit_code: 'KG', scrap_factor: '0.02', is_active: true },
            { id: 'norm-2', consumable_id: 'c-2', consumable_code: 'CS-FAST-018', consumable_name: 'Hex Flange Bolt M8x35', rule_type: 'FIXED_QUANTITY', rate_per_unit: '12.0', unit_code: 'PCS', scrap_factor: '0.01', is_active: true },
          ]));
          return;
        }

        // Inventory
        if (url.startsWith('/api/v1/inventory/status')) {
          res.end(JSON.stringify({ source: 'ERP_CENTRAL', mode: 'RECONCILED', is_live: false, import_enabled: true, warehouse_posting: false, msl_alert_policy: 'TBD' }));
          return;
        }

        if (url.startsWith('/api/v1/inventory/balances') || url.startsWith('/api/v1/inventory?')) {
          res.end(JSON.stringify({
            items: [
              { consumable_id: 'c-1', code: 'CS-ST-004', name: 'Cold-Rolled Steel Strip 1.2mm', is_active: true, unit_id: 'u-1', unit_code: 'KG', usable_quantity: '142.50', as_of: new Date().toISOString(), imported_at: new Date().toISOString(), source_export_id: 'EXP-901', availability: 'REPORTED', is_live: false },
              { consumable_id: 'c-2', code: 'CS-FAST-018', name: 'Hex Flange Bolt M8x35 Grade 8.8', is_active: true, unit_id: 'u-3', unit_code: 'PCS', usable_quantity: '420.00', as_of: new Date().toISOString(), imported_at: new Date().toISOString(), source_export_id: 'EXP-901', availability: 'REPORTED', is_live: false },
              { consumable_id: 'c-3', code: 'CS-LUB-002', name: 'Industrial Synthetic Gear Oil ISO VG 220', is_active: true, unit_id: 'u-2', unit_code: 'L', usable_quantity: '65.00', as_of: new Date().toISOString(), imported_at: new Date().toISOString(), source_export_id: 'EXP-901', availability: 'REPORTED', is_live: false },
            ],
            total: 3,
            limit: 25,
            offset: 0,
          }));
          return;
        }

        if (url.startsWith('/api/v1/inventory/history')) {
          res.end(JSON.stringify({ items: [], total: 0, limit: 25, offset: 0 }));
          return;
        }

        // Purchasing Approvals
        if (url.startsWith('/api/v1/purchasing/approvals')) {
          res.end(JSON.stringify(MOCK_APPROVALS));
          return;
        }

        // Monthly Purchase Plan
        if (url.startsWith('/api/v1/purchasing/plan/inspect') && method === 'POST') {
          res.end(JSON.stringify({
            filename: 'KNL_Purchase_Plan_Template.xlsx',
            detected_view: 'NORMAL_VIEW',
            sheet_name: 'Purchase Plan',
            total_rows: 5,
            total_columns: 23,
            headers: [
              'S. No.', 'Req. Type', 'Item Id', 'Description', 'Unit', 'Output / Unit',
              'MOQ.', 'Min. Stock. Level', 'Max. Stock Level', 'Rate',
              'O/s.', 'Receipt', 'Issues', 'C/s.', 'Prd. Qty.',
              'Sch.', 'Req. Qty.', 'Order Qty.', 'Order Value',
              'Pur. Qty.', 'Pur. Value', 'Bal. Pur. Qty', 'Bal. Pur. Value'
            ],
            missing_required_headers: [],
            validation_errors: [],
            sample_rows: MOCK_PLAN_ITEMS,
          }));
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan/import-sheet') && method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', () => {
            res.end(JSON.stringify(MOCK_PURCHASE_PLAN));
          });
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan/recalculate') && method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', () => {
            // Run deterministic formula: Gap = MSL + Req - Avail; Order = max(Gap, MOQ)
            const recalcItems = MOCK_PLAN_ITEMS.map(it => {
              const avail = parseFloat(String(it.prev_closing_qty || 0));
              const msl = parseFloat(String(it.min_stock_level || 0));
              const reqQty = parseFloat(String(it.req_qty || 0));
              const moq = parseFloat(String(it.moq || 0));
              const rate = parseFloat(String(it.rate || 0));
              const gap = msl + reqQty - avail;
              const orderQty = gap > 0 ? Math.max(gap, moq) : 0;
              return {
                ...it,
                order_qty: orderQty.toFixed(2),
                order_value: (orderQty * rate).toFixed(2),
              };
            });
            const updatedPlan = {
              ...MOCK_PURCHASE_PLAN,
              status: 'CALCULATED',
              items: recalcItems,
              total_order_value: recalcItems.reduce((acc, curr) => acc + parseFloat(curr.order_value), 0).toFixed(2),
              modified_at: new Date().toISOString(),
              modified_by_name: 'admin',
            };
            res.end(JSON.stringify(updatedPlan));
          });
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan/save') && method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', () => {
            const updatedPlan = {
              ...MOCK_PURCHASE_PLAN,
              modified_at: new Date().toISOString(),
              modified_by_name: 'admin',
            };
            res.end(JSON.stringify(updatedPlan));
          });
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan/send-to-approval') && method === 'POST') {
          res.end(JSON.stringify({
            status: 'SUCCESS',
            submitted_count: MOCK_PLAN_ITEMS.filter(i => parseFloat(String(i.order_qty || 0)) > 0).length,
            message: 'Successfully submitted purchase recommendations to the Approval Queue.',
          }));
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan/export')) {
          res.setHeader('Content-Type', 'text/csv');
          res.setHeader('Content-Disposition', 'attachment; filename="purchase_plan.csv"');
          res.end('Item Id,Description,Order Qty,Order Value\nCS-ST-004,Cold-Rolled Steel Strip,250.00,11250.00');
          return;
        }

        if (url.startsWith('/api/v1/purchasing/plan')) {
          res.end(JSON.stringify(MOCK_PURCHASE_PLAN));
          return;
        }

        // Purchase Orders
        if (url.startsWith('/api/v1/purchase-orders/eligible')) {
          res.end(JSON.stringify([]));
          return;
        }

        if (url.startsWith('/api/v1/purchase-orders')) {
          res.end(JSON.stringify([
            {
              id: 'po-1',
              po_number: 'PO-2026-0042',
              supplier_name: 'Tata Steel Special Materials Ltd',
              po_date: '2026-04-05',
              status: 'ISSUED',
              total_value: '185000.00',
              currency: 'INR',
              pending_basis: 'STAGED',
              items: [],
              fulfilment_status: 'IN_TRANSIT',
              history: [],
            },
          ]));
          return;
        }

        // GRNs
        if (url.startsWith('/api/v1/grns')) {
          res.end(JSON.stringify([]));
          return;
        }

        // Users
        if (url.startsWith('/api/v1/users')) {
          res.end(JSON.stringify({
            users: [
              { id: 'usr-1', username: 'admin', is_active: true, is_super_admin: true, roles: ['ADMIN'] },
              { id: 'usr-2', username: 'purchase', is_active: true, is_super_admin: false, roles: ['PURCHASE'] },
              { id: 'usr-3', username: 'store', is_active: true, is_super_admin: false, roles: ['STORE'] },
            ],
            total: 3,
          }));
          return;
        }

        // Generic fallback for any other API route
        res.end(JSON.stringify({ status: 'ok', data: [] }));
      });
    },
  };
}
