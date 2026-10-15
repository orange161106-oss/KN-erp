import { useMemo, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';

interface SourceRow { source_row_number: number; product_code: string; product_name: string; part_number: string; item_id: string;
  quantity: string; unit: string; customer?: string; norm_count: number; errors: {message: string}[]; norm_errors: {message: string}[]; }
interface Preview { sheet_name: string; planning_period: string; revision_label: string; as_of_date: string; review_token: string;
  rows: SourceRow[]; errors: string[]; can_confirm: boolean; norm_ready: boolean; }
export default function CentralProductionImport({ isOpen, onClose, onImportSuccess }: {
  isOpen: boolean; onClose: () => void; onImportSuccess: (count: number, sheet: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState('Prd. Order');
  const [month, setMonth] = useState(''); const [revision, setRevision] = useState('');
  const [asOf, setAsOf] = useState(''); const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [selected, setSelected] = useState(new Set<string>()); const pending = useRef(false);
  const previewRows = useMemo(()=>preview?.rows.map(row=>({...row,id:String(row.source_row_number)}))||[],[preview]);
  const originalRows = useMemo(()=>new Map(previewRows.map(row=>[row.id,row])),[previewRows]);
  if (!isOpen) return null;
  const reset = () => { setPreview(null); setError(''); };
  function body() {
    const data = new FormData(); if (file) data.append('file', file);
    data.append('sheet_name', preview?.sheet_name || sheet); data.append('target_period', preview?.planning_period || month);
    data.append('as_of_date', asOf); if (preview?.revision_label || revision.trim()) data.append('revision_label', preview?.revision_label || revision.trim());
    return data;
  }
  async function inspect(event: React.FormEvent) {
    event.preventDefault(); if (!file || pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try { setPreview(await apiClient.postFormData<Preview>('/api/v1/requirements/basic/production-preview', body())); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not preview production data.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function confirm() {
    if (!preview || !preview.can_confirm || pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try {
      const data = body(); data.append('review_token', preview.review_token);
      const result = await apiClient.postFormData<{imported_count: number}>('/api/v1/requirements/basic/production-confirm', data);
      onImportSuccess(result.imported_count, preview.sheet_name); setPreview(null); setFile(null); onClose();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Import failed. No success was confirmed.'); }
    finally { pending.current = false; setBusy(false); }
  }
  const columns: ColumnDef<SourceRow & {id: string}>[] = [
    {key:'source_row_number', label:'Source Row', width:95}, {key:'part_number',label:'Part No.',width:180},
    {key:'item_id',label:'Item ID',width:170}, {key:'product_code',label:'Matched Product',width:190},
    {key:'product_name',label:'Description',width:260}, {key:'customer',label:'Customer',width:180},
    {key:'quantity',label:'Production Quantity',width:155}, {key:'unit',label:'Unit',width:80},
    {key:'norm_count',label:'Matched Norms',width:120}, {key:'errors',label:'Review',width:360,
      render:(_value,row)=><div className="whitespace-normal text-xs">{[...row.errors,...row.norm_errors].map((item,i)=><p key={i} className={row.errors.length?'text-red-700':'text-amber-800'}>{item.message}</p>)}{!row.errors.length && !row.norm_errors.length && 'Ready'}</div>},
  ];
  return <div role="dialog" aria-modal="true" aria-labelledby="central-import-title" className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4">
    <section className="flex h-[90dvh] w-[96vw] min-h-0 flex-col gap-3 rounded-xl bg-white p-5">
      <header className="flex justify-between"><div><h2 id="central-import-title" className="text-xl font-bold">Import production for central planning</h2><p className="text-sm">Review exact product matches and norms. Super Admin reviews the calculated central plan.</p></div><button disabled={busy} onClick={onClose} aria-label="Close production import">✕</button></header>
      <form onSubmit={event=>void inspect(event)} className="flex flex-wrap items-end gap-3 rounded border p-3"><fieldset disabled={busy} className="contents">
        <label>Production file<input required type="file" accept=".xlsx,.csv" className="block text-sm" onChange={event=>{setFile(event.target.files?.[0]||null);reset();}}/></label>
        <label>Sheet<input className="block rounded border p-2" value={sheet} onChange={event=>{setSheet(event.target.value);reset();}}/></label>
        <label>Planning month<input required type="month" className="block rounded border p-2" value={month} onChange={event=>{setMonth(event.target.value);reset();}}/></label>
        <label>Revision<input placeholder="Blank selects latest" className="block w-44 rounded border p-2" value={revision} onChange={event=>{setRevision(event.target.value);reset();}}/></label>
        <label>Norm effective date<input required type="date" className="block rounded border p-2" value={asOf} onChange={event=>{setAsOf(event.target.value);reset();}}/></label>
        <button disabled={!file} className="rounded border px-4 py-2" type="submit">{busy?'Processing…':'Preview and validate'}</button>
      </fieldset></form>
      {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-700">{error}</p>}
      {preview && <><p role="status">{preview.rows.length} production rows · {preview.planning_period} · {preview.revision_label}. Preview does not save data.</p>
        {preview.errors.map((item,i)=><p role="alert" key={i} className="text-red-700">{item}</p>)}
        {!preview.norm_ready && <p className="text-amber-800">Some norms need correction. Production can be saved when source errors are resolved; approval and purchase release remain blocked until every calculation error is resolved.</p>}
        <div className="min-h-0 flex flex-1 flex-col"><DataTable virtualize columns={columns} data={previewRows} originalData={originalRows}
          selectedIds={selected} onSelectionChange={setSelected} canUpdate={false} canCreate={false} canDelete={false} storageKey="central-production-preview"/></div>
        <footer className="flex items-center justify-between"><p className="text-sm">No products, plants or norms are created automatically. Existing revisions are preserved.</p><button disabled={busy||!preview.can_confirm} onClick={()=>void confirm()} className="rounded bg-burnt-orange px-4 py-2 text-white disabled:opacity-40">Confirm production import</button></footer>
      </>}
    </section>
  </div>;
}
