import {useEffect,useRef,useState} from 'react';
import {apiClient} from '../../api/client';
import CentralPurchaseAssessment from '../purchasing/CentralPurchaseAssessment';
import type {BasicTotal} from './CentralRequirements';

interface Review {
  selected_version_id:string|null;
  versions:{id:string;status:string;is_latest:boolean;revision_label:string}[];
  results:{calculations:{id:string}[];errors:{id:string;product_code:string;error_code:string;error_message:string}[];summary:BasicTotal[]}|null;
}

/** Secondary actions load their evidence only when opened, keeping the MRP screen compact. */
export default function RequirementPlanAction({versionId,period,action,onClose,onApproved}:{
  versionId:string;period:string;action:'approve'|'assess';onClose:()=>void;onApproved:()=>void;
}) {
  const [review,setReview]=useState<Review|null>(null);
  const [error,setError]=useState('');const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);const pending=useRef(false);
  const [acknowledged,setAcknowledged]=useState(false);
  const [attempt,setAttempt]=useState(0);const [materialId,setMaterialId]=useState('');
  useEffect(()=>{
    let current=true;setLoading(true);setError('');setReview(null);setAcknowledged(false);
    void apiClient.get<Review>(`/api/v1/requirements/basic/workspace?planning_version_id=${encodeURIComponent(versionId)}`,60000)
      .then(value=>{if(current){
        if(value.selected_version_id!==versionId)throw new Error('The requested plan could not be loaded.');
        setReview(value);
      }})
      .catch(failure=>{if(current)setError(failure instanceof Error?failure.message:'Could not load the plan.');})
      .finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[versionId,attempt]);
  const version=review?.versions.find(row=>row.id===versionId);
  const errors=review?.results?.errors??[];
  const missing=errors.filter(row=>row.error_code==='NO_CONSUMPTION_NORM');
  const hardErrors=errors.some(row=>row.error_code!=='NO_CONSUMPTION_NORM');
  const canApprove=Boolean(review?.results&&version?.is_latest&&['CALCULATED','CALCULATED_WITH_ERRORS'].includes(version.status)&&!hardErrors&&(!missing.length||acknowledged));
  const material=review?.results?.summary.find(row=>row.consumable_id===materialId);
  async function approve() {
    if(pending.current||!canApprove)return;
    pending.current=true;setBusy(true);setError('');
    try {
      await apiClient.post(`/api/v1/requirements/planning-versions/${versionId}/approve`,missing.length?{acknowledge_missing_norms:true}:{});
      onApproved();
    }catch(failure){setError(failure instanceof Error?failure.message:'Approval failed.');}
    finally{pending.current=false;setBusy(false);}
  }
  return <div role="dialog" aria-modal="true" aria-labelledby="requirement-plan-action-title"
    className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4"
    onKeyDown={event=>{if(event.key==='Escape'&&!busy)onClose();}}>
    <div className={`w-full ${action==='assess'?'max-w-5xl':'max-w-xl'} max-h-[85vh] overflow-auto rounded-xl bg-white p-5 shadow-xl space-y-4`}>
      <div className="flex items-center justify-between gap-3"><h2 id="requirement-plan-action-title" className="text-lg font-bold">
        {action==='approve'?'Approve requirement plan':'Stock and purchase assessment'}</h2>
        <button type="button" disabled={busy} onClick={onClose} className="rounded border px-3 py-1">Close</button></div>
      <p className="text-sm">{period}{version?` · ${version.revision_label} · ${version.status}`:''}</p>
      {loading&&<p role="status">Loading plan…</p>}
      {error&&<div role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {!loading&&!review&&<button type="button" className="rounded border px-3 py-2" onClick={()=>setAttempt(value=>value+1)}>Retry load</button>}
      {review&&action==='approve'&&<>
        <p className="text-sm">Review the {review.results?.calculations.length??0} saved requirement lines in the grid before approval. Recalculation does not approve a plan.</p>
        {hardErrors&&<p className="text-sm text-red-700">Resolve calculation errors before approving this plan.</p>}
        {!version?.is_latest&&<p className="text-sm">Historical revisions cannot be approved.</p>}
        {errors.length>0&&<details className="rounded border p-3 text-sm"><summary>{errors.length} configuration issues</summary>
          <div className="max-h-48 overflow-auto">{errors.map(row=><p key={row.id}>{row.product_code}: {row.error_message}</p>)}</div></details>}
        {missing.length>0&&<label className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          <input type="checkbox" checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/>
          <span>I understand that {missing.length} parts have no consumption norms and their consumable requirements are excluded from this approval.</span></label>}
        <button type="button" disabled={loading||busy||!canApprove} onClick={()=>void approve()}
          className="rounded bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{busy?'Approving…':'Confirm approval'}</button>
      </>}
      {review&&action==='assess'&&(version?.status!=='APPROVED'?<p>Approve the requirement plan before assessing stock and purchase quantities.</p>:<>
        <label className="block text-sm">Consumable<select aria-label="Assessment consumable" value={materialId} onChange={event=>setMaterialId(event.target.value)} className="ml-2 rounded border p-2">
          <option value="">Choose a consumable</option>{review.results?.summary.filter(row=>row.is_fully_confirmed).map(row=><option key={row.consumable_id} value={row.consumable_id}>{row.consumable_code} — {row.consumable_name}</option>)}</select></label>
        {material&&<CentralPurchaseAssessment key={material.consumable_id} versionId={versionId} material={material}/>}
      </>)}
    </div>
  </div>;
}
