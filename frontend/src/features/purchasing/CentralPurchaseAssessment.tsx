import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
export interface BasicTotal {
  consumable_id: string;
  consumable_code: string;
  consumable_name: string;
  uom: string;
  final_required_qty: string;
  is_fully_confirmed: boolean;
}

type State = 'UNKNOWN'|'APPLICABLE'|'NOT_APPLICABLE';
const constraints = [['moq','Minimum order quantity'],['pack_size','Pack size'],['order_multiple','Order multiple'],['max_order_quantity','Maximum order quantity'],['max_stock_quantity','Maximum stock quantity']] as const;
interface Supplier {id:string; code:string; name:string;}
interface Report {status:string; final_requirement:string|null; current_stock:string|null; confirmed_incoming_before_receipt:string|null;
  raw_quantity:string|null; recommended_quantity:string|null; explanation:string; request:Record<string,unknown>;
  limitations:{message:string}[]; projection:{stock_as_of:string|null; limitations:{message:string}[]; current_msl_condition:string; projected_msl_condition:string;}; steps:{code:string; quantity:string; explanation:string}[];}
async function pages<T>(path:string):Promise<T[]> {
  const values:T[]=[];
  for(let offset=0;;){const page=await apiClient.get<{items:T[];total:number}>(`${path}${path.includes('?')?'&':'?'}limit=100&offset=${offset}&is_active=true`);values.push(...page.items);if(!page.items.length||values.length>=page.total)return values;offset+=page.items.length;}
}
const input='block w-full rounded border p-2 text-sm mt-1';
export default function CentralPurchaseAssessment({versionId,material}:{versionId:string;material:BasicTotal}){
  const {user}=useAuth();const canSubmit=Boolean(user?.is_super_admin||user?.purchase_create);
  const [suppliers,setSuppliers]=useState<Supplier[]>([]);const [supplier,setSupplier]=useState('');
  const [sources,setSources]=useState<{source_set_id:string;source_reference:string}[]>([]);const [source,setSource]=useState('');
  const [initiated,setInitiated]=useState('');const [receipt,setReceipt]=useState('');
  const [from,setFrom]=useState('');const [until,setUntil]=useState('');const [reference,setReference]=useState('');
  const [target,setTarget]=useState('');const [days,setDays]=useState('');const [basis,setBasis]=useState('');
  const [policy,setPolicy]=useState<Record<string,{state:State;value:string}>>(Object.fromEntries(constraints.map(([key])=>[key,{state:'UNKNOWN',value:''}])));
  const [other,setOther]=useState('UNKNOWN');const [reason,setReason]=useState('');
  const [report,setReport]=useState<Report|null>(null);const [error,setError]=useState('');const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);const pending=useRef(false);const submission=useRef('');
  useEffect(()=>{let current=true;void Promise.all([
    pages<Supplier>('/api/v1/masters/suppliers'),pages<{supplier_id:string}>(`/api/v1/masters/supplier-consumables?consumable_id=${material.consumable_id}`),
    apiClient.get<{source_set_id:string;source_reference:string}[]>(`/api/v1/requirements/basic/${versionId}/sources?consumable_id=${material.consumable_id}`),
  ]).then(([all,mappings,sets])=>{if(current){setSuppliers(all.filter(row=>mappings.some(mapping=>mapping.supplier_id===row.id)));setSources(sets);}})
    .catch(failure=>{if(current)setError(failure.message);}).finally(()=>{if(current)setLoading(false);});return()=>{current=false;};},[versionId,material.consumable_id]);
  function reset(){setReport(null);setMessage('');}
  async function assess(event:React.FormEvent){
    event.preventDefault();if(pending.current)return;pending.current=true;setBusy(true);setError('');setMessage('');setReport(null);
    try{
      const utc=(value:string)=>new Date(value).toISOString();
      const evidence={effective_from:utc(from),effective_until:utc(until)};
      const values=Object.fromEntries(constraints.map(([key])=>[key,{state:policy[key].state,
        ...(policy[key].state==='APPLICABLE'?{value:policy[key].value}:{}),...(policy[key].state!=='UNKNOWN'?{approval_reference:reference}:{}),}]));
      const value=await apiClient.post<Report>('/api/v1/purchasing/recommendations/assess',{
        consumable_id:material.consumable_id,planning_version_id:versionId,supplier_id:supplier,
        unit_id:await apiClient.get<{unit_id:string}>(`/api/v1/masters/consumables/${material.consumable_id}`).then(row=>row.unit_id),
        source_set_id:source||null,initiated_at:utc(initiated),receipt_at:utc(receipt),evidence_from:utc(from),evidence_until:utc(until),
        target:target!==''?{quantity:target,approval_reference:reference}:null,
        constraints:{...values,other_constraints:other,...(other==='CONFIRMED_NONE'?{other_constraints_reference:reference}:{})},
        lead_time:days!==''&&basis?{supplier_id:supplier,approval_reference:reference,start_event:'ORDER_INITIATED',end_event:'MATERIAL_USABLE',days:Number(days),basis,...evidence}:null,
      });setReport(value);submission.current=crypto.randomUUID();
    }catch(failure){setError(failure instanceof Error?failure.message:'Purchase assessment failed.');}
    finally{pending.current=false;setBusy(false);}
  }
  async function submit(){
    if(!report||report.status!=='RECOMMENDED'||!report.recommended_quantity||pending.current||!reason.trim())return;
    pending.current=true;setBusy(true);setError('');
    try{const value=await apiClient.post<{approval_id:string;replayed:boolean}>('/api/v1/purchase-orders/demand',{submission_key:submission.current,reason:reason.trim(),recommendation:report.request});setMessage(`Purchase demand ${value.replayed?'already submitted':'submitted'} for approval. No purchase order was created.`);}
    catch(failure){setError(failure instanceof Error?failure.message:'Demand submission failed. Retry keeps the same submission reference.');}
    finally{pending.current=false;setBusy(false);}
  }
  function exportReport(){
    if(!report)return;const data=[['Consumable','Basic requirement','Usable stock','Confirmed incoming','Stock-adjusted raw need','Final purchase quantity','Unit','Status'],[material.consumable_code,report.final_requirement,report.current_stock,report.confirmed_incoming_before_receipt,report.raw_quantity,report.recommended_quantity,material.uom,report.status],[],['Limitations'],...[...report.limitations,...report.projection.limitations].map(row=>[row.message]),[],['Step','Quantity','Explanation'],...report.steps.map(row=>[row.code,row.quantity,row.explanation])];
    const csv=data.map(row=>row.map(value=>{const text=String(value??'');return '"'+(text.match(/^[=+\-@]/)?"'"+text:text).replaceAll('"','""')+'"';}).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`Purchase_Assessment_${material.consumable_code}.csv`;link.click();URL.revokeObjectURL(url);
  }
  return <section className="space-y-4 rounded-xl border bg-white p-5"><h3 className="text-lg font-semibold">Inventory and purchase assessment — {material.consumable_code}</h3>
    <p className="text-sm">Approved basic requirement: <strong>{material.final_required_qty} {material.uom}</strong>. Select verified inventory evidence and approved supplier policies. Missing evidence produces an incomplete assessment.</p>
    {loading&&<p role="status">Loading suppliers and inventory sources…</p>}
    {error&&<p role="alert" className="text-red-700">{error}</p>}{message&&<p role="status" className="text-green-800">{message}</p>}
    <form onSubmit={event=>void assess(event)} onChange={reset} className="space-y-3"><fieldset disabled={busy||loading} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label>Mapped supplier<select required className={input} value={supplier} onChange={event=>setSupplier(event.target.value)}><option value="">Choose supplier</option>{suppliers.map(row=><option key={row.id} value={row.id}>{row.code} — {row.name}</option>)}</select></label>
      <label>Reconciled inventory source<select className={input} value={source} onChange={event=>setSource(event.target.value)}><option value="">No verified source selected</option>{sources.map(row=><option key={row.source_set_id} value={row.source_set_id}>{row.source_reference||row.source_set_id}</option>)}</select></label>
      <label>Order initiated at<input required type="datetime-local" className={input} value={initiated} onChange={event=>setInitiated(event.target.value)}/></label>
      <label>Material usable at<input required type="datetime-local" className={input} value={receipt} onChange={event=>setReceipt(event.target.value)}/></label>
      <label>Policy valid from<input required type="datetime-local" className={input} value={from} onChange={event=>setFrom(event.target.value)}/></label>
      <label>Policy valid until<input required type="datetime-local" className={input} value={until} onChange={event=>setUntil(event.target.value)}/></label>
      <label>Policy approval reference<input className={input} value={reference} onChange={event=>setReference(event.target.value)}/></label>
      <label>Approved target stock ({material.uom})<input type="number" min="0" step="any" className={input} value={target} onChange={event=>setTarget(event.target.value)}/></label>
      <label>Lead-time basis<select className={input} value={basis} onChange={event=>setBasis(event.target.value)}><option value="">Unconfirmed</option><option value="ELAPSED_24_HOUR_DAYS">Elapsed 24-hour days</option></select></label>
      <label>Approved lead time (days)<input type="number" min="0" max="3660" step="1" className={input} value={days} onChange={event=>setDays(event.target.value)}/></label>
      {constraints.map(([key,label])=><label key={key}>{label}<select className={input} value={policy[key].state} onChange={event=>setPolicy({...policy,[key]:{...policy[key],state:event.target.value as State}})}><option value="UNKNOWN">Unconfirmed</option><option value="NOT_APPLICABLE">Approved as not applicable</option><option value="APPLICABLE">Applicable — enter quantity</option></select>{policy[key].state==='APPLICABLE'&&<input aria-label={`${label} quantity`} required type="number" min="0" step="any" className={input} value={policy[key].value} onChange={event=>setPolicy({...policy,[key]:{...policy[key],value:event.target.value}})}/>}</label>)}
      <label>Additional supplier constraints<select className={input} value={other} onChange={event=>setOther(event.target.value)}><option value="UNKNOWN">Unconfirmed</option><option value="CONFIRMED_NONE">Approved: no additional constraints</option></select></label>
      <button className="self-end rounded bg-burnt-orange px-4 py-2 text-white disabled:opacity-40" type="submit">Assess stock and purchase need</button>
    </fieldset></form>
    {!sources.length&&!loading&&<p className="text-amber-800">No reconciled inventory source is available for this material and revision. Supply a verified usable stock snapshot, dated demand, incoming PO coverage and reconciliation through the existing inventory import before a complete purchase recommendation can be released.</p>}
    {report&&<div className="space-y-3 rounded border p-4"><h4 className="font-semibold">{report.status}</h4><p>{report.explanation}</p>
      <dl className="grid gap-3 sm:grid-cols-3">{[['Basic requirement',report.final_requirement],['Usable stock',report.current_stock],['Confirmed incoming',report.confirmed_incoming_before_receipt],['Stock-adjusted raw need',report.raw_quantity],['Final purchase quantity',report.recommended_quantity]].map(([label,value])=><div key={label}><dt className="text-sm">{label}</dt><dd className="font-semibold">{value??'Unavailable'} {value!==null&&material.uom}</dd></div>)}</dl>
      <p className="text-sm">Stock as of: {report.projection.stock_as_of||'Unavailable'} · Current stock condition: {report.projection.current_msl_condition} · Projected condition: {report.projection.projected_msl_condition}</p>
      {[...report.limitations,...report.projection.limitations].map((row,index)=><p className="text-amber-800" key={index}>{row.message}</p>)}
      <ol>{report.steps.map((row,index)=><li key={index}>{row.explanation}: {row.quantity}</li>)}</ol><button className="rounded border px-3 py-2" onClick={exportReport}>Export assessment CSV</button>
      {canSubmit&&report.status==='RECOMMENDED'&&Number(report.recommended_quantity)>0&&<div className="flex flex-wrap gap-3"><input aria-label="Purchase demand reason" placeholder="Reason for purchase approval" className="rounded border p-2" value={reason} onChange={event=>setReason(event.target.value)}/><button disabled={busy||!reason.trim()} className="rounded border px-3 py-2" onClick={()=>void submit()}>Submit traced demand for approval</button></div>}
    </div>}
  </section>;
}
