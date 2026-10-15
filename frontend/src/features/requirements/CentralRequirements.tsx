import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import { useAuth } from '../auth/context';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';
import CentralPurchaseAssessment from '../purchasing/CentralPurchaseAssessment';

export interface CentralVersion { id: string; planning_period: string; revision_label: string; status: string; is_latest: boolean; source_filename: string; }
export interface BasicTotal { consumable_id: string; consumable_code: string; consumable_name: string; uom: string; final_required_qty: string; is_fully_confirmed: boolean; }
interface Calculation { id: string; product_code: string; process_name: string; consumable_code: string; consumable_name: string; source_production_qty: string;
  raw_requirement: string; calculated_qty: string; uom: string; rule_version: number; parameters: Record<string, unknown>;
  calculation_steps: {step_number: number; description: string; formula: string; result: string}[]; }
interface Results { calculations: Calculation[]; errors: {id:string; product_code:string; error_code:string; error_message:string}[]; summary: BasicTotal[]; }
interface Preview { complete: boolean; sources: {id:string; source_row_number:number; product_code:string; production_quantity:string; unit:string; norm_count:number; matched:boolean}[];
  errors: {product_code:string; source_row_number:number; message:string}[]; }
const endpoint = '/api/v1/requirements/basic';
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';

export default function CentralRequirements({ purchaseOnly = false }: {purchaseOnly?: boolean}) {
  const {user} = useAuth(); const superAdmin = Boolean(user?.is_super_admin);
  const canCalculate = superAdmin || Boolean(user?.requirements_update);
  const [versions,setVersions] = useState<CentralVersion[]>([]); const [identity,setIdentity] = useState('');
  const [results,setResults] = useState<Results|null>(null); const [preview,setPreview] = useState<Preview|null>(null);
  const [asOf,setAsOf] = useState(''); const [busy,setBusy] = useState(false); const [loading,setLoading] = useState(false);
  const [error,setError] = useState(''); const [message,setMessage] = useState('');
  const [selected,setSelected] = useState(new Set<string>()); const [detail,setDetail] = useState<Calculation|null>(null);
  const [material,setMaterial] = useState(''); const pending = useRef(false); const generation = useRef(0);
  const version = versions.find(row=>row.id===identity);
  const calculationOriginals = useMemo(()=>new Map((results?.calculations||[]).map(row=>[row.id,row])),[results]);
  const sourceOriginals = useMemo(()=>new Map((preview?.sources||[]).map(row=>[row.id,row])),[preview]);
  const refresh = useCallback(async()=>{
    const values = await apiClient.get<CentralVersion[]>(`${endpoint}/versions`); setVersions(values);
    setIdentity(previous=>values.some(row=>row.id===previous)?previous:values.find(row=>row.is_latest)?.id||values[0]?.id||'');
  },[]);
  useEffect(()=>{setLoading(true);void refresh().catch(failure=>setError(failure.message)).finally(()=>setLoading(false));},[refresh]);
  useEffect(()=>{
    const current = ++generation.current; setResults(null);setPreview(null);setDetail(null);setMaterial('');setError('');setMessage('');
    if(!identity) return;
    setLoading(true);
    void apiClient.get<Results>(`${endpoint}/${identity}/results`).then(value=>{if(current===generation.current) setResults(value);})
      .catch(failure=>{if(current===generation.current)setError(failure.message);})
      .finally(()=>{if(current===generation.current)setLoading(false);});
    return ()=>{++generation.current;};
  },[identity]);
  async function run(action:'preview'|'calculate'|'approve') {
    if(pending.current||!identity) return;
    if(action!=='approve'&&!asOf){setError('Choose the norm effective date before calculating.');return;}
    pending.current=true;setBusy(true);setError('');setMessage('');
    try{
      if(action==='preview') setPreview(await apiClient.post<Preview>(`${endpoint}/preview`,{planning_version_id:identity,as_of_date:asOf}));
      else {
        if(action==='calculate') await apiClient.post(`${endpoint}/calculate`,{planning_version_id:identity,as_of_date:asOf});
        else await apiClient.post(`/api/v1/requirements/planning-versions/${identity}/approve`,{});
        setResults(await apiClient.get<Results>(`${endpoint}/${identity}/results`));await refresh();setPreview(null);
        setMessage(action==='approve'?'Central plan approved by Super Admin. Consolidated demand is available to inventory and purchase assessment.':'Basic requirements saved. Resolve every calculation error before approval.');
      }
    }catch(failure){setError(failure instanceof Error?failure.message:'The operation failed.');}
    finally{pending.current=false;setBusy(false);}
  }
  async function download(format:'xlsx'|'csv'){
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    try{
      const token=getAccessToken();const response=await fetch(`${getApiBaseUrl()}${endpoint}/${identity}/export?format=${format}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});
      if(!response.ok){const value=await response.json().catch(()=>null);throw new Error(value?.message||'Export failed.');}
      const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=`Basic_Requirements_${version?.planning_period}_${version?.revision_label}.${format}`;link.click();URL.revokeObjectURL(url);
    }catch(failure){setError(failure instanceof Error?failure.message:'Export failed.');}finally{pending.current=false;setBusy(false);}
  }
  const columns:ColumnDef<Calculation>[]=[{key:'product_code',label:'Product',width:190},{key:'process_name',label:'Process',width:160},
    {key:'consumable_code',label:'Consumable Item ID',width:180},{key:'consumable_name',label:'Consumable',width:260},
    {key:'source_production_qty',label:'Production Quantity',width:170},{key:'raw_requirement',label:'Raw Basic Requirement',width:170},
    {key:'calculated_qty',label:'Basic Requirement',width:160},{key:'uom',label:'Stock Unit',width:100},{key:'rule_version',label:'Norm Version',width:110},
    {key:'id',label:'Calculation Details',width:140,render:(_value,row)=><button className="underline" onClick={()=>setDetail(row)}>View formula</button>}];
  return <div className="space-y-4 min-w-0">
    <section className="rounded-xl border bg-white p-5 space-y-3"><h2 className="text-xl font-bold">{purchaseOnly?'Central purchase assessment':'Central basic requirement plan'}</h2>
      <p className="text-sm">Production quantities × approved consumption norms → Super Admin review → consolidated inventory and purchase assessment.</p>
      <div className="flex flex-wrap items-end gap-3"><label>Production revision<select aria-label="Central production revision" disabled={loading||busy} value={identity} onChange={event=>setIdentity(event.target.value)} className="block rounded border p-2"><option value="">Choose imported production</option>{versions.map(row=><option key={row.id} value={row.id}>{row.planning_period} · {row.revision_label} · {row.status}{row.is_latest?' · Latest':' · History'}</option>)}</select></label>
        {!purchaseOnly&&<><label>Norm effective date<input type="date" value={asOf} onChange={event=>{setAsOf(event.target.value);setPreview(null);}} className="block rounded border p-2"/></label>
          <button className={button} disabled={busy||loading||!identity} onClick={()=>void run('preview')}>Preview matching</button>
          {canCalculate&&<button className={`${button} bg-burnt-orange text-white`} disabled={busy||loading||!version?.is_latest||version.status==='APPROVED'} onClick={()=>void run('calculate')}>Calculate and save</button>}
          {superAdmin&&<button className={`${button} bg-emerald-700 text-white`} disabled={busy||loading||!version?.is_latest||version.status!=='CALCULATED'||Boolean(results?.errors.length)} onClick={()=>void run('approve')}>Approve central plan</button>}</>}
        <button className={button} disabled={busy||!results} onClick={()=>void download('xlsx')}>Export Excel</button><button className={button} disabled={busy||!results} onClick={()=>void download('csv')}>Export CSV</button>
      </div>
      {version&&<p className="text-sm">Source: {version.source_filename} · Status: <strong>{version.status}</strong>{!version.is_latest&&' · Historical revision; calculation and approval are protected.'}</p>}
      {!identity&&!loading&&<p>Upload a production workbook in Production for sale to start central planning.</p>}
      {loading&&<p role="status">Loading central plan…</p>}{busy&&<p role="status">Processing…</p>}
      {error&&<p role="alert" className="rounded bg-red-50 p-3 text-red-700">{error}</p>}{message&&<p role="status" className="rounded bg-green-50 p-3 text-green-800">{message}</p>}
    </section>
    {preview&&<section className="rounded-xl border bg-white p-4 space-y-2"><h3 className="font-semibold">Product and norm matching</h3><p>{preview.sources.length} source rows · {preview.complete?'All rows matched':'Corrections required'}. Preview does not save or approve demand.</p>
      <div className="h-72 flex flex-col"><DataTable columns={[{key:'source_row_number',label:'Source Row'},{key:'product_code',label:'Product'},{key:'production_quantity',label:'Production Quantity'},{key:'norm_count',label:'Matched Norms'},{key:'matched',label:'Ready',render:value=>value?'Yes':'Review'}]}
        data={preview.sources} originalData={sourceOriginals} selectedIds={selected} onSelectionChange={setSelected} canUpdate={false} canCreate={false} canDelete={false}/></div>
      {preview.errors.map((row,index)=><p key={index} className="text-red-700">Row {row.source_row_number} · {row.product_code}: {row.message}</p>)}
    </section>}
    {results?.errors.length? <section className="rounded border border-red-200 bg-red-50 p-4"><h3 className="font-semibold">Approval blocked — resolve calculation errors</h3>{results.errors.map(row=><p key={row.id}>{row.product_code}: {row.error_message}</p>)}</section>:null}
    {!purchaseOnly&&results&&<section className="h-[420px] min-h-0 flex flex-col overflow-hidden rounded-xl border bg-white"><DataTable virtualize columns={columns} data={results.calculations} originalData={calculationOriginals} selectedIds={selected} onSelectionChange={setSelected} canUpdate={false} canCreate={false} canDelete={false} storageKey="central-basic-results" emptyMessage="No saved calculation yet. Preview matching, then calculate and save."/></section>}
    {detail&&!purchaseOnly&&<section className="rounded-xl border bg-white p-4"><button className="float-right underline" onClick={()=>setDetail(null)}>Close details</button><h3 className="font-semibold">{detail.product_code} → {detail.consumable_code}, norm v{detail.rule_version}</h3><p className="text-sm">Approved parameters: {JSON.stringify(detail.parameters)}</p><ol>{detail.calculation_steps.map(step=><li key={step.step_number} className="mt-2"><strong>{step.description}</strong><p>{step.formula} = {step.result}</p></li>)}</ol></section>}
    {results&&<section className="rounded-xl border bg-white p-4 space-y-3"><h3 className="font-semibold">Consolidated consumable requirements</h3><p className="text-sm">Each material is consolidated across products before usable stock or incoming supply is applied. Basic demand remains separate from purchase quantity.</p>
      <div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr><th>Consumable</th><th>Basic requirement</th><th>Unit</th><th>Review</th><th>Inventory / purchase</th></tr></thead><tbody>{results.summary.map(row=><tr key={row.consumable_id} className="border-t"><td className="py-2">{row.consumable_code} — {row.consumable_name}</td><td>{row.final_required_qty}</td><td>{row.uom}</td><td>{row.is_fully_confirmed?'Approved':'Awaiting Super Admin'}</td><td><button disabled={!row.is_fully_confirmed||!version?.is_latest} className="underline disabled:opacity-40" onClick={()=>setMaterial(row.consumable_id)}>Assess purchase</button></td></tr>)}</tbody></table></div>
    </section>}
    {identity&&material&&results&&<CentralPurchaseAssessment key={`${identity}/${material}`} versionId={identity} material={results.summary.find(row=>row.consumable_id===material)!}/>}
  </div>;
}
