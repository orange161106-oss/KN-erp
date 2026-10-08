import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';

interface Product { id?: string; code: string; name: string; uom: string; item_id?: string | null; part_number?: string | null; }
interface Candidate { code: string; item_id: string; part_number: string; name: string; uom: string; source_rows: number[]; description_options?: string[]; unit_options?: string[]; }
interface Preview { filename: string; sheet: string; sha256: string; products: Candidate[]; message: string; }

export default function Products() {
  const { user } = useAuth();
  const canWrite = Boolean(user?.is_super_admin || user?.permissions.includes('masters.write'));
  const [products, setProducts] = useState<Product[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [candidates, setCandidates] = useState<Product[]>([]);
  const [sheet, setSheet] = useState('Prd. Order');
  const [key, setKey] = useState('');
  const [unit, setUnit] = useState('');
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [manual, setManual] = useState<Product>({ code: '', name: '', uom: '', item_id: '', part_number: '' });
  const sourceChoices = [
    { field: 'item_id', label: 'Item ID' },
    { field: 'part_number', label: 'Part No.' },
    { field: 'code', label: 'Product Code' },
  ] as const;
  const missing = {
    codes: candidates.filter(p => !p.code.trim()).length,
    descriptions: candidates.filter(p => !p.name.trim()).length,
    units: candidates.filter(p => !p.uom.trim()).length,
  };
  const load = async () => {
    setLoading(true);
    try { setProducts(await apiClient.get<Product[]>('/api/v1/masters/products')); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    let cancelled = false;
    void apiClient.get<Product[]>('/api/v1/masters/products')
      .then(data => { if (!cancelled) setProducts(data); })
      .catch(error => { if (!cancelled) { setFailed(true); setMessage(error.message); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  const act = async (operation: () => Promise<void>) => {
    setBusy(true); setMessage(''); setFailed(false);
    try { await operation(); } catch (e) { setFailed(true); setMessage(e instanceof Error ? e.message : 'Operation failed.'); }
    finally { setBusy(false); }
  };
  const inspect = (file: File) => act(async () => {
    setUploadName(file.name); setPreview(null); setCandidates([]);
    if (!file.name.toLowerCase().endsWith('.xlsx') || !file.size || file.size > 10 * 1024 * 1024) {
      throw new Error('Choose a nonempty .xlsx workbook of at most 10 MB.');
    }
    const data = new FormData(); data.append('file', file); data.append('sheet_name', sheet);
    const result = await apiClient.postFormData<Preview>('/api/v1/masters/products/preview', data, 30000);
    if (!Array.isArray(result.products) || !result.products.length) throw new Error('No products were found. Check the sheet name and product identifier headers.');
    setPreview(result); setKey('');
    setCandidates(result.products.map(p => ({ code: p.code, item_id: p.item_id || null, part_number: p.part_number || null, name: p.name, uom: p.uom })));
    setMessage(result.message);
  });
  const approve = () => act(async () => {
    if (!preview || !key) {
      throw new Error('Choose a product code source available in your workbook: Item ID, Part No. or Product Code.');
    }
    const source = sourceChoices.find(choice => choice.field === key);
    if (!source || !preview.products.some(p => p[source.field]?.trim())) {
      throw new Error('The selected identifier is not present in this workbook. Choose Item ID or Part No. to populate the product codes.');
    }
    if (missing.codes || missing.descriptions || missing.units) {
      throw new Error(`Please review every product before saving. Missing values: ${missing.codes} product codes, ${missing.descriptions} descriptions, ${missing.units} production units.`);
    }
    const uniqueCodes = new Set(candidates.map(p => p.code.trim()));
    if (uniqueCodes.size !== candidates.length) {
      throw new Error('The selected identifiers contain duplicate product codes. Choose a verified unique identifier or review the duplicate rows before saving.');
    }
    setSaving(true);
    try {
      await apiClient.post('/api/v1/masters/products/reviewed', { products: candidates,
        source_reference: `${preview.filename}; sheet=${preview.sheet}; sha256=${preview.sha256}` });
      setPreview(null); setCandidates([]); await load(); setMessage('Reviewed products saved. Continue to Product–Plant Routes.');
    } finally { setSaving(false); }
  });
  return <section className="space-y-4">
    <h2 className="text-xl font-semibold">Products</h2>
    <p>Products are the parts KNL plans to manufacture. Create or review them before assigning plants, routes and consumption rules.</p>
    {!canWrite && <p role="note">You have read-only access. A Super Admin or an employee with Edit master data permission can upload and save products.</p>}
    {!canWrite && message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    {canWrite && <>
      <form className="flex flex-wrap gap-3 border p-3" onSubmit={e => { e.preventDefault(); void act(async () => {
        await apiClient.post('/api/v1/masters/products', manual); await load(); setMessage('Product created. Continue to Product–Plant Routes.');
      }); }}>
        {(['code', 'item_id', 'part_number', 'name', 'uom'] as const).map(field => <label key={field}>
          {({ code: 'Product code', item_id: 'External Item ID', part_number: 'Part No.', name: 'Description', uom: 'Production unit' })[field]}
          <input className="block border p-1" value={manual[field] || ''} required={['code', 'name', 'uom'].includes(field)}
            onChange={e => setManual({ ...manual, [field]: e.target.value })} />
        </label>)}
        <button disabled={busy}>Create product</button>
      </form>
      <div className="border p-3 space-y-2">
        <h3 className="font-semibold">Review products from the production-order workbook</h3>
        {busy && <p role="status" aria-live="polite">{saving ? 'Saving reviewed products… Keep this page open.' : `Processing ${uploadName || 'products'}… Please wait.`}</p>}
        {message && <p role={failed ? 'alert' : 'status'} className={`rounded border p-3 ${failed ? 'border-red-300 bg-red-50 text-red-800' : 'border-blue-300 bg-blue-50 text-blue-900'}`}>{message}</p>}
        <label>Sheet name <input className="border p-1" value={sheet} onChange={e => setSheet(e.target.value)} /></label>
        <input aria-label="Preview product workbook" type="file" accept=".xlsx" disabled={busy}
          onChange={e => { const file = e.target.files?.[0]; if (file) void inspect(file); e.target.value = ''; }} />
        {preview && <>
          <label>Product code source <select value={key} onChange={e => {
            const field = e.target.value as 'item_id' | 'part_number' | 'code'; setKey(field);
            setCandidates(candidates.map((p, i) => ({ ...p, code: field ? preview.products[i][field] : '' })));
          }}><option value="">Choose the verified identifier</option>{sourceChoices.map(choice => {
            const available = preview.products.some(p => p[choice.field]?.trim());
            return <option key={choice.field} value={choice.field} disabled={!available}>{choice.label}{available ? '' : ' (not present in this workbook)'}</option>;
          })}</select></label>
          <label>Reviewed unit for blank rows <input value={unit} onChange={e => setUnit(e.target.value)} /></label>
          <button disabled={!unit.trim() || busy} onClick={() => setCandidates(candidates.map(p => ({ ...p, uom: p.uom || unit.trim() })))}>Apply unit to blank rows</button>
          <p>Review all rows below. Uploading alone does not create master data or approve demand.</p>
          <p>{candidates.length} products found. Resolve blank descriptions and units, then choose Save reviewed products.</p>
          {(missing.codes || missing.descriptions || missing.units) > 0 && <p className="rounded border border-amber-300 bg-amber-50 p-2 text-amber-900" aria-live="polite">
            Still to review: {missing.codes} product codes, {missing.descriptions} descriptions, {missing.units} production units.
          </p>}
          <div className="sticky top-0 z-10 flex items-center gap-3 border bg-white p-3 shadow-sm">
            <button className="rounded bg-brand-navy px-5 py-2 font-semibold text-white disabled:opacity-50" disabled={busy || !candidates.length} onClick={() => void approve()}>{saving ? 'Saving products…' : 'Save reviewed products'}</button>
            <span className="text-sm">Save after reviewing product codes, descriptions and production units.</span>
          </div>
          <div className="max-h-[50vh] overflow-auto rounded border" aria-label="Product preview table">
          <table className="w-full"><thead className="sticky top-0 bg-gray-100"><tr><th>Item ID</th><th>Part No.</th><th>Product code</th><th>Description</th><th>Unit</th></tr></thead><tbody>
            {candidates.map((p, i) => <tr key={i}><td>{p.item_id}</td><td>{p.part_number}</td>
              {(['code', 'name', 'uom'] as const).map(field => <td key={field} className="border-b p-2"><input className={`rounded border p-1 ${field === 'name' ? 'w-72' : field === 'uom' ? 'w-20' : 'w-44'}`} aria-label={`Product ${i + 1} ${field}`} value={p[field]}
                onChange={e => setCandidates(candidates.map((row, j) => j === i ? { ...row, [field]: e.target.value } : row))} />
                {field === 'name' && (preview.products[i].description_options?.length || 0) > 1 && <div className="text-sm text-amber-800">
                  Conflicting descriptions in source rows {preview.products[i].source_rows.join(', ')}. Choose the correct description:
                  <select aria-label={`Product ${i + 1} description choice`} value={p.name} onChange={e => setCandidates(candidates.map((row, j) => j === i ? { ...row, name: e.target.value } : row))}>
                    <option value="">Review source descriptions</option>{preview.products[i].description_options?.map(name => <option key={name} value={name}>{name}</option>)}
                  </select></div>}
                {field === 'uom' && (preview.products[i].unit_options?.length || 0) > 1 && <p className="text-sm text-amber-800">Conflicting source units: {preview.products[i].unit_options?.join(', ')}. Enter the verified unit.</p>}
              </td>)}
            </tr>)}
          </tbody></table>
          </div>
        </>}
      </div>
    </>}
    {loading && <p role="status">Loading products…</p>}
    <table className="w-full"><thead><tr><th>Code</th><th>Item ID</th><th>Part No.</th><th>Description</th><th>Unit</th></tr></thead>
      <tbody>{products.map(p => <tr key={p.id}><td>{p.code}</td><td>{p.item_id}</td><td>{p.part_number}</td><td>{p.name}</td><td>{p.uom}</td></tr>)}</tbody></table>
    {!loading && !failed && !products.length && <p>No products yet. An authorised master-data editor can create one or review a workbook.</p>}
  </section>;
}
