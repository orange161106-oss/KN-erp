import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import { useAuth } from '../auth/context';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';
import CentralPurchaseAssessment from '../purchasing/CentralPurchaseAssessment';

export interface CentralVersion { id: string; planning_period: string; revision_label: string; status: string; is_latest: boolean; source_filename: string; }
export interface BasicTotal { consumable_id: string; consumable_code: string; consumable_name: string; uom: string; final_required_qty: string; is_fully_confirmed: boolean; }
interface Calculation { id: string; product_code: string; product_name?: string; product_part_number?: string; product_item_id?: string;
  consumable_id?: string; process_name: string; consumable_code: string; consumable_name: string; source_production_qty: string;
  raw_requirement: string; calculated_qty: string; uom: string; rule_version: number; parameters: Record<string, unknown>;
  calculation_steps: {step_number: number; description: string; formula: string; result: string}[]; }
interface Results { calculations: Calculation[]; errors: {id:string; product_code:string; error_code:string; error_message:string;
  context_data?: {part_number?:string; item_id?:string; part_description?:string; planned_quantity?:string}}[]; summary: BasicTotal[]; }
interface Workspace { versions: CentralVersion[]; selected_version_id: string | null; results: Results | null; }
interface MissingPartItem { part_no?: string; part_number?: string; product_code?: string; item_id?: string; part_name?: string; part_description?: string; planned_quantity?: number | string; production_quantity?: number | string; error_message?: string; }
interface Preview {
  complete: boolean;
  sources: {id:string; source_row_number:number; product_code:string; production_quantity:string; unit:string; norm_count:number; matched:boolean}[];
  errors: {product_code:string; source_row_number:number; message:string}[];
  has_missing_norms?: boolean;
  missing_parts_count?: number;
  missing_parts_qty?: string | number;
  no_consumption_norms?: MissingPartItem[];
  duplicate_norm_groups_count?: number;
  duplicate_groups_warning?: string | null;
}
interface CalculationRunResponse {
  planning_version_id: string;
  status: string;
  has_missing_norms?: boolean;
  missing_parts_count?: number;
  missing_parts_qty?: string | number;
  no_consumption_norms?: MissingPartItem[];
  duplicate_norm_groups_count?: number;
  duplicate_groups_warning?: string | null;
}

const endpoint = '/api/v1/requirements/basic';
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';

export default function CentralRequirements({ purchaseOnly = false, initialVersionId = '' }: {purchaseOnly?: boolean; initialVersionId?: string}) {
  const {user} = useAuth(); const superAdmin = Boolean(user?.is_super_admin);
  const canCalculate = superAdmin || Boolean(user?.requirements_update);
  const [versions,setVersions] = useState<CentralVersion[]>([]); const [identity,setIdentity] = useState('');
  const [results,setResults] = useState<Results|null>(null); const [preview,setPreview] = useState<Preview|null>(null);
  const [asOf,setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy,setBusy] = useState(false); const [loading,setLoading] = useState(false);
  const [error,setError] = useState(''); const [message,setMessage] = useState('');
  const [selected,setSelected] = useState(new Set<string>()); const [detail,setDetail] = useState<Calculation|null>(null);
  const [material,setMaterial] = useState('');
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [missingParts, setMissingParts] = useState<MissingPartItem[]>([]);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [acknowledgeMissingNorms, setAcknowledgeMissingNorms] = useState(false);
  const [expandedConsumables, setExpandedConsumables] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');

  const pending = useRef(false); const generation = useRef(0);
  const preloadedIdentity = useRef('');
  const version = versions.find(row=>row.id===identity);
  const calculationOriginals = useMemo(()=>new Map((results?.calculations||[]).map(row=>[row.id,row])),[results]);
  const sourceOriginals = useMemo(()=>new Map((preview?.sources||[]).map(row=>[row.id,row])),[preview]);
  
  const acceptResults = useCallback((value: Results) => {
    setResults(value);
    setMissingParts((value.errors || []).filter(row => row.error_code === 'NO_CONSUMPTION_NORM').map(row => ({
      part_no: row.context_data?.part_number || row.product_code,
      item_id: row.context_data?.item_id,
      part_name: row.context_data?.part_description,
      planned_quantity: row.context_data?.planned_quantity,
    })));
  }, []);

  const acceptWorkspace = useCallback((value: Workspace) => {
    setVersions(value.versions);
    preloadedIdentity.current=value.selected_version_id||'';
    setIdentity(value.selected_version_id||'');
    if(value.results)acceptResults(value.results);
    else {setResults(null);setMissingParts([]);}
  },[acceptResults]);

  const readWorkspace = useCallback((versionId='')=>apiClient.get<Workspace>(
    `${endpoint}/workspace${versionId?`?planning_version_id=${encodeURIComponent(versionId)}`:''}`,60000),[]);

  useEffect(()=>{
    let current=true;setLoading(true);
    void readWorkspace(initialVersionId).then(value=>{if(current)acceptWorkspace(value);})
      .catch(failure=>{if(current)setError(failure.message);})
      .finally(()=>{if(current)setLoading(false);});
    return ()=>{current=false;};
  },[readWorkspace,acceptWorkspace,initialVersionId]);

  useEffect(()=>{
    const current = ++generation.current;
    if(identity&&preloadedIdentity.current===identity){preloadedIdentity.current='';return;}
    preloadedIdentity.current='';
    setResults(null);setPreview(null);setDetail(null);setMaterial('');setError('');setMessage('');
    setDuplicateWarning(null); setMissingParts([]); setShowApprovalModal(false); setAcknowledgeMissingNorms(false);
    if(!identity) return;
    setLoading(true);
    void apiClient.get<Results>(`${endpoint}/${identity}/results`,60000).then(value=>{
      if(current===generation.current) {
        acceptResults(value);
      }
    })
      .catch(failure=>{if(current===generation.current)setError(failure.message);})
      .finally(()=>{if(current===generation.current)setLoading(false);});
    return ()=>{++generation.current;};
  },[identity,acceptResults]);

  async function reloadResults() {
    if(pending.current)return;
    pending.current=true;setLoading(true);setError('');
    try {
      acceptWorkspace(await readWorkspace(identity || initialVersionId));
    } catch(failure) {
      setError(failure instanceof Error?failure.message:'The saved results could not be loaded.');
    } finally {pending.current=false;setLoading(false);}
  }

  async function run(action:'preview'|'calculate'|'approve', ackMissing = false) {
    if(pending.current||!identity) return;
    const targetDate = asOf || new Date().toISOString().slice(0, 10);
    pending.current=true;setBusy(true);setError('');setMessage('');
    let saved = false;
    try{
      if(action==='preview') {
        const prev = await apiClient.post<Preview>(`${endpoint}/preview`,{planning_version_id:identity,as_of_date:targetDate});
        setPreview(prev);
        setDuplicateWarning(prev.duplicate_groups_warning || null);
        setMissingParts(prev.no_consumption_norms || []);
      }
      else {
        if(action==='calculate') {
          const calcRes = await apiClient.post<CalculationRunResponse>(`${endpoint}/calculate`,{planning_version_id:identity,as_of_date:targetDate});
          setDuplicateWarning(calcRes.duplicate_groups_warning || null);
          setMissingParts(calcRes.no_consumption_norms || []);
        }
        else {
          await apiClient.post(`/api/v1/requirements/planning-versions/${identity}/approve`, ackMissing ? { acknowledge_missing_norms: true } : {});
          setShowApprovalModal(false);
          setAcknowledgeMissingNorms(false);
        }
        saved = true;
        // The write has committed. A later read failure must not display the old
        // zero-row calculation or tell the operator to repeat the write.
        setResults(null);setPreview(null);
        setMessage(action==='approve'?'Central plan approved by Super Admin. Consolidated demand is available to inventory and purchase assessment.':'Product-wise requirements saved. The Consumable Planning Module shows the same saved results. Review any remaining configuration issues below.');
        acceptWorkspace(await readWorkspace(identity));
      }
    }catch(failure){setError(saved?'The changes were saved, but the latest results could not be loaded. Use Reload results to view them.':failure instanceof Error?failure.message:'The operation failed.');}
    finally{pending.current=false;setBusy(false);}
  }

  function downloadMissingNormsCsv() {
    if (!missingParts.length) return;
    const headers = ['Part No', 'Item ID', 'Part Description', 'Planned Qty'];
    const dataRows = missingParts.map(p => [
      p.part_no || p.part_number || p.product_code || '',
      p.item_id || '',
      p.part_name || p.part_description || p.error_message || '',
      String(p.planned_quantity ?? p.production_quantity ?? '0'),
    ]);
    const csvString = [headers.join(','), ...dataRows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))].join('\r\n');
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Missing_Consumption_Norms_${version?.planning_period || 'Period'}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function toggleConsumableBreakdown(id: string) {
    setExpandedConsumables(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function download(format:'xlsx'|'csv'){
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    try{
      const token=getAccessToken();const response=await fetch(`${getApiBaseUrl()}${endpoint}/${identity}/export?format=${format}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});
      if(!response.ok){const value=await response.json().catch(()=>null);throw new Error(value?.message||'Export failed.');}
      const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=`Basic_Requirements_${version?.planning_period}_${version?.revision_label}.${format}`;link.click();URL.revokeObjectURL(url);
    }catch(failure){setError(failure instanceof Error?failure.message:'Export failed.');}finally{pending.current=false;setBusy(false);}
  }

  const hasHardErrors = Boolean(results?.errors?.some(e => e.error_code !== 'NO_CONSUMPTION_NORM'));
  const hasMissingNorms = missingParts.length > 0 || Boolean(results?.errors?.some(e => e.error_code === 'NO_CONSUMPTION_NORM'));

  const visibleCalculations = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (results?.calculations || []).filter(row => !term || [row.product_code, row.product_part_number, row.product_item_id,
      row.product_name, row.consumable_code, row.consumable_name].some(value => value?.toLowerCase().includes(term)));
  }, [results, search]);
  const columns:ColumnDef<Calculation>[]=[{key:'product_code',label:'Product',width:190},
    {key:'product_part_number',label:'Part No.',width:160},{key:'product_item_id',label:'Product Item ID',width:160},
    {key:'product_name',label:'Product Description',width:240},{key:'process_name',label:'Process',width:160},
    {key:'consumable_code',label:'Consumable Item ID',width:180},{key:'consumable_name',label:'Consumable',width:260},
    {key:'source_production_qty',label:'Production Quantity',width:170},{key:'raw_requirement',label:'Raw Basic Requirement',width:170},
    {key:'calculated_qty',label:'Required Consumable Quantity',width:210},{key:'uom',label:'Stock Unit',width:100},{key:'rule_version',label:'Norm Version',width:110},
    {key:'id',label:'Calculation Details',width:140,render:(_value,row)=><button className="underline" onClick={()=>setDetail(row)}>View formula</button>}];

  return <div className="space-y-4 min-w-0">
    <section className="rounded-xl border bg-white p-5 space-y-3"><h2 className="text-xl font-bold">{purchaseOnly?'Central purchase assessment':'Central basic requirement plan'}</h2>
      <p className="text-sm">Production quantities × approved consumption norms → Super Admin review → consolidated inventory and purchase assessment.</p>
      <div className="flex flex-wrap items-end gap-3"><label>Production revision<select aria-label="Central production revision" disabled={loading||busy} value={identity} onChange={event=>setIdentity(event.target.value)} className="block rounded border p-2"><option value="">Choose imported production</option>{versions.map(row=><option key={row.id} value={row.id}>{row.planning_period} · {row.revision_label} · {row.status}{row.is_latest?' · Latest':' · History'}</option>)}</select></label>
        {!purchaseOnly&&<><label>Norm effective date<input type="date" value={asOf} onChange={event=>{setAsOf(event.target.value);setPreview(null);}} className="block rounded border p-2"/></label>
          <button className={button} disabled={busy||loading||!identity} onClick={()=>void run('preview')}>Preview matching</button>
          {canCalculate&&<button className={`${button} bg-burnt-orange text-white`} disabled={busy||loading||!version?.is_latest||version.status==='APPROVED'} onClick={()=>void run('calculate')}>Calculate and save</button>}
          {superAdmin&&<button className={`${button} bg-emerald-700 text-white`} disabled={busy||loading||!results||!version?.is_latest||!['CALCULATED','CALCULATED_WITH_ERRORS'].includes(version.status)||hasHardErrors} onClick={()=>{
            if (hasMissingNorms) setShowApprovalModal(true);
            else void run('approve', false);
          }}>Approve central plan</button>}</>}
        <button className={button} disabled={busy||!results} onClick={()=>void download('xlsx')}>Export Excel</button><button className={button} disabled={busy||!results} onClick={()=>void download('csv')}>Export CSV</button>
        <button className={button} disabled={busy||loading} onClick={()=>void reloadResults()}>Reload results</button>
      </div>
      {version&&<p className="text-sm">Source: {version.source_filename} · Status: <strong>{version.status}</strong>{!version.is_latest&&' · Historical revision; calculation and approval are protected.'}</p>}
      {!identity&&!loading&&!error&&<p>Upload a production workbook in Production for sale to start central planning.</p>}
      {loading&&<p role="status">Loading central plan…</p>}{busy&&<p role="status">Processing…</p>}
      {error&&<p role="alert" className="rounded bg-red-50 p-3 text-red-700">{error}</p>}{message&&<p role="status" className="rounded bg-green-50 p-3 text-green-800">{message}</p>}
    </section>

    {!purchaseOnly&&results&&<section className="min-w-0 rounded-xl border bg-white">
      <div className="flex flex-wrap items-center gap-3 p-4">
        <div><h3 className="font-semibold">Consumables required per product</h3>
          <p className="text-sm">{results.calculations.length} saved requirement lines. Quantities use the selected production revision and saved consumption formulas.</p></div>
        <input aria-label="Search product requirements" placeholder="Search part number, item ID or consumable" className="ml-auto rounded border p-2 text-sm min-w-64" value={search} onChange={event=>setSearch(event.target.value)}/>
      </div>
      <div className="h-[420px] min-h-0 flex flex-col overflow-hidden"><DataTable virtualize columns={columns} data={visibleCalculations} originalData={calculationOriginals} selectedIds={selected} onSelectionChange={setSelected} canUpdate={false} canCreate={false} canDelete={false} storageKey="central-basic-results" emptyMessage={search?'No product requirements match this search.':'No saved calculation yet. Preview matching, then calculate and save.'}/></div>
    </section>}

    {duplicateWarning && (
      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 flex items-start gap-2 shadow-sm">
        <span className="font-bold text-base">⚠️</span>
        <div>
          <strong className="font-semibold">Multiple Norms Active:</strong> {duplicateWarning}
        </div>
      </div>
    )}

    {missingParts.length > 0 && (
      <section className="rounded-xl border border-amber-300 bg-amber-50/60 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-semibold text-amber-950 text-base">
              {missingParts.length} parts have no consumption norms defined
            </h3>
            <p className="text-xs text-amber-800">
              Consumable requirements for these production parts are excluded from calculations until norms are configured.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={`${button} bg-white text-gray-800 shadow-sm hover:bg-gray-50`}
              onClick={downloadMissingNormsCsv}
            >
              Download Missing Norms List (CSV)
            </button>
            <a
              href="/rules"
              className={`${button} bg-burnt-orange text-white`}
              target="_blank"
              rel="noreferrer"
            >
              Open Consumption Norms →
            </a>
          </div>
        </div>
        <div className="max-h-60 overflow-y-auto rounded border border-amber-200 bg-white">
          <table className="w-full text-xs text-left">
            <thead className="bg-amber-100/60 border-b border-amber-200 text-gray-700">
              <tr>
                <th className="p-2 font-medium">Part No</th>
                <th className="p-2 font-medium">Item ID</th>
                <th className="p-2 font-medium">Part Description</th>
                <th className="p-2 font-medium text-right">Planned Qty</th>
              </tr>
            </thead>
            <tbody>
              {missingParts.map((p, idx) => (
                <tr key={idx} className="border-b last:border-b-0 hover:bg-amber-50/30">
                  <td className="p-2 font-mono font-medium">{p.part_no || p.part_number || p.product_code || '—'}</td>
                  <td className="p-2 font-mono text-gray-600">{p.item_id || '—'}</td>
                  <td className="p-2">{p.part_name || p.part_description || p.error_message || '—'}</td>
                  <td className="p-2 text-right font-mono font-medium">{String(p.planned_quantity ?? p.production_quantity ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )}

    {preview&&<section className="rounded-xl border bg-white p-4 space-y-2"><h3 className="font-semibold">Product and norm matching</h3><p>{preview.sources.length} source rows · {preview.complete?'All rows matched':'Corrections required'}. Preview does not save or approve demand.</p>
      <div className="h-72 flex flex-col"><DataTable columns={[{key:'source_row_number',label:'Source Row'},{key:'product_code',label:'Product'},{key:'production_quantity',label:'Production Quantity'},{key:'norm_count',label:'Matched Norms'},{key:'matched',label:'Ready',render:value=>value?'Yes':'Review'}]}
        data={preview.sources} originalData={sourceOriginals} selectedIds={selected} onSelectionChange={setSelected} canUpdate={false} canCreate={false} canDelete={false}/></div>
      {preview.errors.map((row,index)=><p key={index} className="text-red-700">Row {row.source_row_number} · {row.product_code}: {row.message}</p>)}
    </section>}

    {results?.errors.length ? (
      <details className={`rounded border p-4 space-y-1 ${hasHardErrors ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50'}`}>
        <summary className="font-semibold cursor-pointer">{results.errors.length} configuration issues — {hasHardErrors ? 'resolve before approval' : 'parts without consumption norms'}</summary>
        <p className="text-sm">Review the listed products in Consumption Norms, then Calculate and save again. Valid requirement lines remain visible above.</p>
        <a href="/rules" className="text-sm underline">Open Consumption Norms</a>
        <div className="max-h-64 overflow-auto">{results.errors.map(row=><p key={row.id} className={`text-sm ${hasHardErrors ? 'text-red-700' : 'text-amber-800'}`}>{row.product_code}: {row.error_message}</p>)}</div>
      </details>
    ) : null}

    {detail&&!purchaseOnly&&<section className="rounded-xl border bg-white p-4"><button className="float-right underline" onClick={()=>setDetail(null)}>Close details</button><h3 className="font-semibold">{detail.product_code} → {detail.consumable_code}, norm v{detail.rule_version}</h3><p className="text-sm">Approved parameters: {JSON.stringify(detail.parameters)}</p><ol>{detail.calculation_steps.map(step=><li key={step.step_number} className="mt-2"><strong>{step.description}</strong><p>{step.formula} = {step.result}</p></li>)}</ol></section>}
    
    {results&&<section className="rounded-xl border bg-white p-4 space-y-3"><h3 className="font-semibold">Consolidated consumable requirements</h3><p className="text-sm">Each material is consolidated across products before usable stock or incoming supply is applied. Basic demand remains separate from purchase quantity.</p>
      <div className="overflow-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr>
              <th className="py-2">Consumable</th>
              <th className="py-2">Basic requirement</th>
              <th className="py-2">Unit</th>
              <th className="py-2">Review</th>
              <th className="py-2">Breakdown</th>
              <th className="py-2">Inventory / purchase</th>
            </tr>
          </thead>
          <tbody>
            {results.summary.map(row => {
              const breakdown = (results.calculations || []).filter(c => c.consumable_id ? c.consumable_id === row.consumable_id : c.consumable_code === row.consumable_code);
              const isExpanded = expandedConsumables.has(row.consumable_id);
              return (
                <tr key={row.consumable_id} className="border-t">
                  <td colSpan={6} className="p-0">
                    <div className="flex items-center justify-between py-2.5 px-1 hover:bg-gray-50">
                      <div className="w-[30%] font-medium">{row.consumable_code} — {row.consumable_name}</div>
                      <div className="w-[15%] font-mono font-semibold">{row.final_required_qty}</div>
                      <div className="w-[10%] text-gray-600">{row.uom}</div>
                      <div className="w-[15%]">{row.is_fully_confirmed?'Approved':'Awaiting Super Admin'}</div>
                      <div className="w-[15%]">
                        {breakdown.length > 0 ? (
                          <button
                            type="button"
                            className="text-xs text-burnt-orange font-medium underline"
                            onClick={() => toggleConsumableBreakdown(row.consumable_id)}
                          >
                            {isExpanded ? 'Hide parts breakdown' : `View parts breakdown (${breakdown.length})`}
                          </button>
                        ) : <span className="text-xs text-gray-400">—</span>}
                      </div>
                      <div className="w-[15%] text-right pr-2">
                        <button disabled={!row.is_fully_confirmed||!version?.is_latest} className="underline disabled:opacity-40" onClick={()=>setMaterial(row.consumable_id)}>Assess purchase</button>
                      </div>
                    </div>
                    {isExpanded && breakdown.length > 0 && (
                      <div className="bg-gray-50 border-y px-4 py-2 my-1 text-xs">
                        <p className="font-semibold text-gray-700 mb-1.5">Contributing production parts:</p>
                        <table className="w-full bg-white border rounded">
                          <thead className="bg-gray-100 text-gray-600">
                            <tr>
                              <th className="p-1.5">Product / Part No</th>
                              <th className="p-1.5">Process</th>
                              <th className="p-1.5 text-right">Production Qty</th>
                              <th className="p-1.5 text-right">Basic Requirement</th>
                              <th className="p-1.5">Stock Unit</th>
                            </tr>
                          </thead>
                          <tbody>
                            {breakdown.map((item, bIdx) => (
                              <tr key={bIdx} className="border-t font-mono">
                                <td className="p-1.5 font-sans font-medium">{item.product_code}</td>
                                <td className="p-1.5 font-sans text-gray-600">{item.process_name || '—'}</td>
                                <td className="p-1.5 text-right">{item.source_production_qty}</td>
                                <td className="p-1.5 text-right font-semibold text-burnt-orange">{item.calculated_qty}</td>
                                <td className="p-1.5 text-gray-600">{item.uom}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>}

    {showApprovalModal && (
      <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
        <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl space-y-4">
          <h3 className="text-lg font-bold text-gray-900">Approve Plan with Missing Norms</h3>
          <div className="text-sm text-amber-900 bg-amber-50 p-3 rounded-lg border border-amber-200 space-y-1">
            <p className="font-semibold">⚠️ Attention: {missingParts.length} parts have no consumption norms defined.</p>
            <p>Approving now means consumables for these parts will <strong>NOT</strong> be calculated or ordered for this month.</p>
          </div>
          <label className="flex items-start gap-2.5 text-sm text-gray-700 cursor-pointer p-2 rounded hover:bg-gray-50 border">
            <input
              type="checkbox"
              className="mt-0.5 rounded border-gray-300"
              checked={acknowledgeMissingNorms}
              onChange={e => setAcknowledgeMissingNorms(e.target.checked)}
            />
            <span>
              I understand that {missingParts.length} parts have no consumption norms and their consumable requirements are excluded from this approval.
            </span>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className={button}
              onClick={() => { setShowApprovalModal(false); setAcknowledgeMissingNorms(false); }}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!acknowledgeMissingNorms || busy}
              className={`${button} bg-emerald-700 text-white font-medium`}
              onClick={() => void run('approve', true)}
            >
              {busy ? 'Approving…' : 'Confirm & Approve'}
            </button>
          </div>
        </div>
      </div>
    )}

    {identity&&material&&results&&<CentralPurchaseAssessment key={`${identity}/${material}`} versionId={identity} material={results.summary.find(row=>row.consumable_id===material)!}/>}
  </div>;
}
