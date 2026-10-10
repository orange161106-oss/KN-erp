import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import type { ProductResolutionResponse } from '../mappings/types';
import type { ConsumptionNorm } from './types';

const ruleFields = {
  PRODUCTION_RATE: { label: 'Consumption per production unit', fields: { rate: 'Rate per production unit', scrap_factor: 'Approved scrap factor (enter 0 for none)' } },
  AREA_COVERAGE: { label: 'Area and coverage', fields: { area_per_unit: 'Area per production unit', coverage: 'Area covered per consumable unit', loss_factor: 'Approved loss factor (enter 0 for none)' } },
  PACKING_RATIO: { label: 'Packing ratio', fields: { units_per_pack: 'Production units per pack' } },
  TOOL_LIFE: { label: 'Tool life', fields: { operations_per_unit: 'Operations per production unit', tool_life: 'Tool life in operations' } },
  FIXED_QUANTITY: { label: 'Fixed requirement', fields: { quantity: 'Approved fixed quantity' } },
  PLANT_REQUEST: { label: 'Explicit plant request', fields: { default_quantity: 'Approved fallback quantity (enter 0 for none)' } },
  MAINTENANCE: { label: 'Maintenance requirement', fields: { fixed_amount: 'Approved fixed amount', variable_rate: 'Approved rate per production unit' } },
  MIN_MAX: { label: 'Bounded consumption requirement', fields: { base_rate: 'Consumption rate per production unit', min_quantity: 'Requirement lower bound', max_quantity: 'Requirement upper bound' } },
} as const;
type RuleKey = keyof typeof ruleFields;
interface Product { id: string; code: string; name: string; is_active: boolean; }
interface Material { id: string; unit_id: string; is_active: boolean; }

export default function NormSetup({ onCreated }: { onCreated: (id: string) => Promise<void> }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState('');
  const [resolution, setResolution] = useState<ProductResolutionResponse | null>(null);
  const [plant, setPlant] = useState('');
  const [process, setProcess] = useState('');
  const [consumable, setConsumable] = useState('');
  const [material, setMaterial] = useState<Material | null>(null);
  const [unitCode, setUnitCode] = useState('');
  const [rule, setRule] = useState<RuleKey | ''>('');
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [rounding, setRounding] = useState('');
  const [precision, setPrecision] = useState('4');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    let current = true;
    apiClient.get<Product[]>('/api/v1/masters/products').then(rows => { if (current) setProducts(rows.filter(p => p.is_active)); })
      .catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, []);
  useEffect(() => {
    let current = true;
    setResolution(null); setPlant(''); setProcess(''); setConsumable('');
    if (product) apiClient.get<ProductResolutionResponse>(`/api/v1/mappings/resolve/${product}`)
      .then(value => { if (current) setResolution(value); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [product]);
  useEffect(() => {
    let current = true;
    setMaterial(null); setUnitCode('');
    if (consumable) void (async () => {
      try {
        const value = await apiClient.get<Material>(`/api/v1/masters/consumables/${consumable}`);
        const unit = await apiClient.get<{ code: string; is_active: boolean }>(`/api/v1/masters/units/${value.unit_id}`);
        if (current) {
          if (!value.is_active || !unit.is_active) throw new Error('The consumable and its unit must be active.');
          setMaterial(value); setUnitCode(unit.code);
        }
      } catch (e) { if (current) setError(e instanceof Error ? e.message : 'Cannot load the consumable unit.'); }
    })();
    return () => { current = false; };
  }, [consumable]);
  const plants = resolution?.plant_mappings || [];
  const steps = plants.find(p => p.plant_id === plant)?.steps || [];
  const materials = steps.find(p => p.process_id === process)?.consumables.filter(c => c.is_active) || [];
  async function save(event: React.FormEvent) {
    event.preventDefault(); setError(''); setMessage('');
    if (!product || !plant || !process || !consumable || material?.id !== consumable || !rule || !rounding || !from) {
      setError('Select a mapped product, plant, process, consumable, formula, rounding policy and effective date.'); return;
    }
    if (to && to < from) { setError('Effective until must be on or after effective from.'); return; }
    setBusy(true);
    try {
      const saved = await apiClient.post<ConsumptionNorm>('/api/v1/consumption-norms', {
        product_id: product, plant_id: plant, process_id: process, consumable_id: consumable,
        unit_id: material.unit_id, rule_type: rule, parameters, rounding_policy: rounding,
        rounding_precision: Number(precision), effective_from: from, effective_to: to || null,
      });
      setMessage(`Norm version ${saved.version} saved. Select it below and run a calculation using a date within its effective period.`);
      await onCreated(saved.id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save the norm.'); }
    finally { setBusy(false); }
  }
  const inputClass = 'block w-full rounded border border-gray-300 px-3 py-2';
  return <section className="rounded-lg border bg-white p-6 space-y-4">
    <h3 className="text-lg font-semibold">Create consumption norm</h3>
    <p>Choose an existing mapping and enter KNL-approved parameters. No rates or allowances are filled automatically. Saving another norm for the same scope creates a new version and supersedes the previous one.</p>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-red-800">{error}</p>}
    {message && <p role="status" className="rounded bg-green-50 p-3 text-green-800">{message}</p>}
    <form onSubmit={save} className="space-y-4"><fieldset disabled={busy} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <label>Product<select required className={inputClass} value={product} onChange={e => setProduct(e.target.value)}><option value="">Choose product</option>{products.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></label>
      <label>Mapped plant<select required className={inputClass} value={plant} onChange={e => { setPlant(e.target.value); setProcess(''); setConsumable(''); }}><option value="">Choose plant</option>{plants.map(p => <option key={p.plant_id} value={p.plant_id}>{p.plant_name}</option>)}</select></label>
      <label>Mapped process<select required className={inputClass} value={process} onChange={e => { setProcess(e.target.value); setConsumable(''); }}><option value="">Choose process</option>{steps.map(p => <option key={p.process_id} value={p.process_id}>{p.process_name}</option>)}</select></label>
      <label>Mapped consumable<select required className={inputClass} value={consumable} onChange={e => setConsumable(e.target.value)}><option value="">Choose consumable</option>{materials.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}</select></label>
      <label>Output unit<input readOnly className={inputClass} value={unitCode} placeholder="From the consumable master" /></label>
      <label>Formula type<select required className={inputClass} value={rule} onChange={e => { setRule(e.target.value as RuleKey); setParameters({}); }}><option value="">Choose approved formula</option>{Object.entries(ruleFields).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></label>
      {rule && Object.entries(ruleFields[rule].fields).map(([key, label]) => <label key={key}>{label}<input required type="number" step="any" min="0" className={inputClass} value={parameters[key] || ''} onChange={e => setParameters({ ...parameters, [key]: e.target.value })} /></label>)}
      <label>Rounding policy<select required className={inputClass} value={rounding} onChange={e => setRounding(e.target.value)}><option value="">Choose rounding</option><option value="NONE">No rounding</option><option value="ROUND_UP">Round up</option><option value="ROUND_HALF_UP">Round half up</option><option value="ROUND_DOWN">Round down</option></select></label>
      <label>Decimal places<select className={inputClass} value={precision} onChange={e => setPrecision(e.target.value)}>{[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      <label>Effective from<input required type="date" className={inputClass} value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label>Effective until (optional)<input type="date" min={from} className={inputClass} value={to} onChange={e => setTo(e.target.value)} /></label>
      <button disabled={!material || !rule} className="rounded bg-burnt-orange hover:bg-burnt-orange-dark px-4 py-2 font-semibold text-white disabled:opacity-50 shadow-xs transition-colors" type="submit">{busy ? 'Saving norm…' : 'Save norm'}</button>
    </fieldset></form>
    {product && resolution && !plants.length && <p>No active plant route exists for this product. Complete Production Mappings first.</p>}
    {process && !materials.length && <p>No active consumable is assigned to this process. Complete Product–Process–Consumable mapping first.</p>}
  </section>;
}
