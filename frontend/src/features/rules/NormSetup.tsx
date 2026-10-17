import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import type { ConsumptionNorm } from './types';

const ruleFields = {
  PRODUCTION_RATE: { label: 'Consumption per production unit', fields: { rate: 'Rate per production unit', scrap_factor: 'Approved scrap factor (enter 0 for none)' } },
  AREA_COVERAGE: { label: 'Area and coverage', fields: { area_per_unit: 'Area per production unit', coverage: 'Area covered per consumable unit', loss_factor: 'Approved loss factor (enter 0 for none)' } },
  PACKING_RATIO: { label: 'Packing ratio', fields: { units_per_pack: 'Production units per pack', material_per_pack: 'Consumable quantity per pack' } },
  TOOL_LIFE: { label: 'Tool life', fields: { operations_per_unit: 'Operations per production unit', tool_life: 'Tool life in operations' } },
  FIXED_QUANTITY: { label: 'Fixed requirement', fields: { quantity: 'Approved fixed quantity' } },
  PLANT_REQUEST: { label: 'Explicit plant request', fields: { default_quantity: 'Approved fallback quantity (enter 0 for none)' } },
  MAINTENANCE: { label: 'Maintenance requirement', fields: { fixed_amount: 'Approved fixed amount', variable_rate: 'Approved rate per production unit' } },
  MIN_MAX: { label: 'Bounded consumption requirement', fields: { base_rate: 'Consumption rate per production unit', min_quantity: 'Requirement lower bound', max_quantity: 'Requirement upper bound' } },
} as const;
type RuleKey = keyof typeof ruleFields;
interface Product { id: string; code: string; name: string; part_number?: string | null; is_active: boolean; }
interface Material { id: string; code: string; name: string; unit_id: string; is_active: boolean; }
interface Process { id: string; name: string; is_active: boolean; }
interface Unit { id: string; code: string; is_active: boolean; }

async function allPages<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let offset = 0;
  while (true) {
    const page = await apiClient.get<{ items: T[]; total: number }>(`${path}?limit=100&offset=${offset}&is_active=true`);
    rows.push(...page.items);
    if (!page.items.length || rows.length >= page.total) return rows;
    offset += page.items.length;
  }
}

export default function NormSetup({ onCreated, onCancel }: { onCreated: (id: string) => Promise<void>; onCancel?: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState('');
  const [processes, setProcesses] = useState<Process[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [process, setProcess] = useState('');
  const [consumable, setConsumable] = useState('');
  const [rule, setRule] = useState<RuleKey | ''>('');
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [rounding, setRounding] = useState('');
  const [precision, setPrecision] = useState('4');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const pending = useRef(false);
  useEffect(() => {
    let current = true;
    void Promise.all([
      apiClient.get<Product[]>('/api/v1/masters/products'),
      (async () => {
        const rows: Process[] = [];
        for (let skip = 0; ; skip += 100) {
          const page = await apiClient.get<Process[]>(`/api/v1/processes?limit=100&skip=${skip}`);
          rows.push(...page);
          if (page.length < 100) return rows;
        }
      })(),
      allPages<Material>('/api/v1/masters/consumables'),
      allPages<Unit>('/api/v1/masters/units'),
    ]).then(([productRows, processRows, materialRows, unitRows]) => {
      if (current) {
        setProducts(productRows.filter(row => row.is_active)); setProcesses(processRows.filter(row => row.is_active));
        setMaterials(materialRows.filter(row => row.is_active)); setUnits(unitRows.filter(row => row.is_active));
      }
    }).catch(failure => { if (current) setError(failure.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, []);
  const material = materials.find(row => row.id === consumable);
  const unit = units.find(row => row.id === material?.unit_id);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    setError(''); setMessage('');
    if (!product || !process || !material || !unit || !rule || !rounding || !from) {
      setError('Select an active product, process, consumable, formula, rounding policy and effective date.'); return;
    }
    if (to && to < from) { setError('Effective until must be on or after effective from.'); return; }
    pending.current = true; setBusy(true);
    try {
      const saved = await apiClient.post<ConsumptionNorm>('/api/v1/consumption-norms', {
        product_id: product, plant_id: null, process_id: process, consumable_id: consumable,
        unit_id: material.unit_id, rule_type: rule, parameters, rounding_policy: rounding,
        rounding_precision: Number(precision), effective_from: from, effective_to: to || null,
      });
      setMessage(`Norm version ${saved.version} saved. Select it below and run a calculation using a date within its effective period.`);
      await onCreated(saved.id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save the norm.'); }
    finally { pending.current = false; setBusy(false); }
  }
  const inputClass = 'block w-full rounded border border-gray-300 px-3 py-2';
  return <section className="rounded-lg border bg-white p-6 space-y-4">
    <h3 className="text-lg font-semibold">Create consumption norm</h3>
    <p className="text-sm text-gray-600">Choose existing master records and enter approved parameters. Product–plant mapping is not required for basic planning. No rates or master records are created automatically.</p>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-red-800">{error}</p>}
    {message && <p role="status" className="rounded bg-green-50 p-3 text-green-800">{message}</p>}
    {loading && <p role="status">Loading master records…</p>}
    <form onSubmit={save} className="space-y-4"><fieldset disabled={busy || loading} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <label>Product<select required className={inputClass} value={product} onChange={e => setProduct(e.target.value)}><option value="">Choose product</option>{products.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></label>
      <label>Process<select required className={inputClass} value={process} onChange={e => setProcess(e.target.value)}><option value="">Choose process</option>{processes.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Consumable<select required className={inputClass} value={consumable} onChange={e => setConsumable(e.target.value)}><option value="">Choose consumable</option>{materials.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}</select></label>
      <label>Output unit<input readOnly className={inputClass} value={unit?.code || ''} placeholder="From the consumable master" /></label>
      <label>Formula type<select required className={inputClass} value={rule} onChange={e => { setRule(e.target.value as RuleKey); setParameters({}); }}><option value="">Choose approved formula</option>{Object.entries(ruleFields).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></label>
      {rule && Object.entries(ruleFields[rule].fields).map(([key, label]) => <label key={key}>{label}<input required type="number" step="any" min="0" className={inputClass} value={parameters[key] || ''} onChange={e => setParameters({ ...parameters, [key]: e.target.value })} /></label>)}
      <label>Rounding policy<select required className={inputClass} value={rounding} onChange={e => setRounding(e.target.value)}><option value="">Choose rounding</option><option value="NONE">No rounding</option><option value="ROUND_UP">Round up</option><option value="ROUND_HALF_UP">Round half up</option><option value="ROUND_DOWN">Round down</option></select></label>
      <label>Decimal places<select className={inputClass} value={precision} onChange={e => setPrecision(e.target.value)}>{[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      <label>Effective from<input required type="date" className={inputClass} value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label>Effective until (optional)<input type="date" min={from} className={inputClass} value={to} onChange={e => setTo(e.target.value)} /></label>
      <div className="flex gap-2"><button disabled={!unit || !rule} className="rounded bg-burnt-orange hover:bg-burnt-orange-dark px-4 py-2 font-semibold text-white disabled:opacity-50 shadow-xs transition-colors" type="submit">{busy ? 'Saving norm…' : 'Save norm'}</button>{onCancel && <button disabled={busy} type="button" className="rounded border px-4 py-2" onClick={onCancel}>Cancel</button>}</div>
    </fieldset></form>
    {material && !unit && <p className="text-red-700">The consumable needs an active stock unit in master data before this norm can be saved.</p>}
  </section>;
}
