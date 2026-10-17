import type { PurchaseWorkspaceRecord } from './PurchaseWorkspace';

export interface PurchaseViewColumn {
  label: string;
  value: (record: PurchaseWorkspaceRecord, source?: PurchaseWorkspaceRecord['md_sources'][number], index?: number) => string;
}

const show = (value: unknown): string => value == null || value === '' ? '—' : String(value);
const field = (key: keyof PurchaseWorkspaceRecord): PurchaseViewColumn['value'] => record => show(record[key]);
const missing: PurchaseViewColumn['value'] = () => '—';
const column = (label: string, value: PurchaseViewColumn['value']): PurchaseViewColumn => ({ label, value });
const sourceField = (key: keyof PurchaseWorkspaceRecord['md_sources'][number]): PurchaseViewColumn['value'] => (_record, source) => show(source?.[key]);

export const normalViewColumns = (month: number, year: number): PurchaseViewColumn[] => {
  const current = new Date(year, month - 1).toLocaleString('en', { month: 'short' });
  const previous = new Date(year, month - 2).toLocaleString('en', { month: 'short' });
  const prevYear = month === 1 ? year - 1 : year;
  return [
    column('S. No.', (_row, _source, index) => String((index ?? 0) + 1)),
    column('Req. Type', field('category')),
    column('Item Id', field('consumable_code')),
    column('Description', field('consumable_name')),
    column('Unit', field('unit')),
    column('Output / Unit', field('output_unit')),
    column('MOQ.', field('minimum_order_qty')),
    column('Min. Stock. Level', field('minimum_stock_level')),
    column('Max. Stock Level', field('max_stock_level')),
    column('Rate', field('unit_rate')),
    column(`O/s. ${previous}-${String(prevYear).slice(-2)}`, field('opening_qty')),
    column(`Receipt ${previous}-${String(prevYear).slice(-2)}`, field('receipt_qty')),
    column(`Issues ${previous}-${String(prevYear).slice(-2)}`, field('issue_qty')),
    column(`C/s. ${previous}-${String(prevYear).slice(-2)}`, field('stock_qty')),
    column(`Prd. Qty. ${previous}-${String(prevYear).slice(-2)}`, missing),
    column(`Sch. ${current}-${String(year).slice(-2)}`, missing),
    column(`Req. Qty. ${current}-${String(year).slice(-2)}`, field('required_qty')),
    column('Order Qty.', field('system_recommended_qty')),
    column('Order Value', field('purchase_value')),
    column('Pur. Qty.', missing),
    column('Pur. Value', missing),
    column('Bal. Pur. Qty', missing),
    column('Bal. Pur. Value', missing),
  ];
};

export const mdViewColumns = (month: number, year: number): PurchaseViewColumn[] => {
  const current = new Date(year, month - 1).toLocaleString('en', { month: 'short' });
  const previous = new Date(year, month - 2).toLocaleString('en', { month: 'short' });
  const prevYear = month === 1 ? year - 1 : year;
  const list: PurchaseViewColumn[] = [
    column('Supplier ID', field('supplier_code')),
    column('Supplier name', field('supplier_name')),
    column('Item Id', field('consumable_code')),
    column('Category', field('category')),
    column('Type of material', field('type_of_material')),
    column('S. No.', (_row, _source, index) => String((index ?? 0) + 1)),
    column('Description', field('consumable_name')),
    column('Part No. of saleable item', sourceField('part_number')),
    column('Used for- Name of Saleable part', sourceField('part_name')),
    column('Used Part no (prd order)', sourceField('production_order_part')),
    column('Process name', sourceField('process_name')),
    column('Material thickness in mm / Gsm', sourceField('part_thickness')),
    column('No of process per part', sourceField('process_count')),
    column('Output/ Unit', field('output_unit')),
    column('Rate', field('unit_rate')),
    column(`Opening Qty ${previous}'${String(prevYear).slice(-2)}`, field('opening_qty')),
    column(`Opening Value ${previous}'${String(prevYear).slice(-2)}`, field('opening_value')),
    column(`Receipt. Qty. ${previous}'${String(prevYear).slice(-2)}`, field('receipt_qty')),
    column(`Issue Qty. ${previous}'${String(prevYear).slice(-2)}`, field('issue_qty')),
    column(`Closing Qty ${previous}'${String(prevYear).slice(-2)}`, field('stock_qty')),
    column(`Closing Value ${previous}'${String(prevYear).slice(-2)}`, field('closing_value')),
    column('Rate', field('unit_rate')),
    column('Min stock level', field('minimum_stock_level')),
    column('Max stock level', field('max_stock_level')),
    column('Minimum order qty.', field('minimum_order_qty')),
    column('Lead time to supply in days', field('lead_time_days')),
    column('Sch. Qty. as per assy R1', sourceField('production_qty')),
    column('Purchasing Unit', field('unit')),
    column('Sch. Qty. Cons. Itemwise R1', sourceField('required_qty')),
    column(`Opening stock ${current}'${String(year).slice(-2)}`, field('stock_qty')),
    column('Req. Qty.', field('required_qty')),
    column('Order Qty R1', field('system_recommended_qty')),
    column('Order Value R1', field('purchase_value')),
  ];
  const remaining = [
    'Receipt qty. R1', 'Receipt value R1', 'Sch. Qty. as per assy R2',
    'Sch. Qty. Cons. Itemwise R2', 'Req. R2', 'closing stock',
    'Req.qty lessed by issue qty', 'Issue Qty. till', 'Order Qty. R2',
    'Order Value R2', 'Receipt qty. R2', 'Receipt value R2',
    'Total Receipt Qty.', 'Total receipt value', 'P1', 'P2', 'P3', 'P4', 'P5',
    'tool room', 'Quality', 'PMD', 'NPD', 'HRD', 'Accounts',
    'Purchase ,Stores&admin', 'Sales', 'Req. given by users', 'Total Value.',
    'Avg.Monthly Consumption', 'Avg.Daily Consumption', 'Minimum order Quantity.',
    'Lead time to supply in days', 'Mini number of days to hold in production',
    'Min stock level', 'Max stock level', 'Lead time qty', 'Re-Order Level',
    'Cost of MSL', 'REORDER LEVEL(MSL+(Avg.reqd.con per dayxLead timr to supply in days))',
    'Avg. consumption per day', 'Previous month Plan value', 'Previous month Actual value',
  ];
  const known: Record<number, PurchaseViewColumn['value']> = {
    65: field('minimum_order_qty'), 66: field('lead_time_days'),
    68: field('minimum_stock_level'), 69: field('max_stock_level'),
  };
  remaining.forEach((label, index) => list.push(column(label, known[index + 34] ?? missing)));
  return list;
};
