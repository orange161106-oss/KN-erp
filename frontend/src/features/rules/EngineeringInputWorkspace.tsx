import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { apiClient } from '../../api/client';

const ENDPOINT = '/api/v1/consumption-norms/engineering-inputs';
const SHEET_NAMES = ['Process Verification', 'Tool Life Details', 'Product Consumable BOM'];

type SourceRow = {
  source_row: number;
  reference: string | number | null;
  status: 'PENDING' | 'READY_FOR_REVIEW' | 'NOT_APPROVED' | string;
  missing_fields: string[];
  validation_issues?: string[];
  warnings?: string[];
  source_values: Record<string, string | number | boolean | null>;
};
type WorkbookData = {
  workflow: string;
  filename: string;
  source_sha256: string;
  total_rows: number;
  ready_rows: number;
  pending_rows: number;
  not_approved_rows: number;
  sheets: Record<string, { row_count: number; rows: SourceRow[] }>;
};
type SavedWorkbook = { batch_id: string; filename: string; uploaded_at: string; status: string; batch: WorkbookData };

function display(value: unknown) {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

export default function EngineeringInputWorkspace({ onClose, onSaved }: { onClose: () => void; onSaved: (message: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [workbook, setWorkbook] = useState<WorkbookData | null>(null);
  const [saved, setSaved] = useState<SavedWorkbook | null>(null);
  const [sheet, setSheet] = useState(SHEET_NAMES[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const activeWorkbook = workbook ?? (!file ? saved?.batch : null) ?? null;
  const rows = activeWorkbook?.sheets[sheet]?.rows ?? [];
  const fields = useMemo(() => {
    const keys = new Set<string>();
    rows.forEach(row => Object.keys(row.source_values).forEach(key => keys.add(key)));
    return [...keys];
  }, [rows]);

  useEffect(() => {
    let active = true;
    void apiClient.get<SavedWorkbook | null>(`${ENDPOINT}/latest`).then(value => {
      if (active) setSaved(value);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'Could not load the saved engineering workbook.');
    });
    return () => { active = false; };
  }, []);

  async function inspect(chosen: File) {
    setError(''); setFile(chosen); setWorkbook(null);
    if (!chosen.name.toLowerCase().endsWith('.xlsx') || chosen.size > 10 * 1024 * 1024) {
      setError('Choose an .xlsx workbook no larger than 10 MB.'); return;
    }
    setBusy(true);
    try {
      const body = new FormData(); body.append('file', chosen);
      const result = await apiClient.postFormData<WorkbookData>(`${ENDPOINT}/preview`, body);
      setWorkbook(result); setSheet(SHEET_NAMES[0]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The workbook could not be previewed.'); }
    finally { setBusy(false); if (input.current) input.current.value = ''; }
  }

  async function save() {
    if (!file || !workbook || busy) return;
    setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('file', file);
      const result = await apiClient.postFormData<{ batch_id: string; filename: string; uploaded_at: string; status: string; replayed: boolean; batch: WorkbookData; message: string }>(ENDPOINT, body);
      const latest: SavedWorkbook = { batch_id: result.batch_id, filename: result.filename, uploaded_at: result.uploaded_at, status: result.status, batch: result.batch };
      setSaved(latest); setWorkbook(null); setFile(null);
      onSaved(result.message);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The engineering workbook could not be saved.'); }
    finally { setBusy(false); }
  }

  const summary = activeWorkbook?.sheets[sheet];
  const button = 'rounded border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50';
  return <div role="dialog" aria-modal="true" aria-labelledby="engineering-input-title" className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-3 md:p-6">
    <section className="flex h-[94dvh] w-full max-w-[98vw] min-h-0 flex-col gap-3 rounded-xl bg-white p-4 shadow-xl md:p-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id="engineering-input-title" className="text-xl font-bold">Engineering Input Workbook</h2>
          <p className="mt-1 text-sm text-gray-600">Preview and retain all populated source rows. Blank or unapproved engineering inputs stay pending and are not used in calculations.</p>
        </div>
        <button type="button" aria-label="Close engineering input workbook" onClick={onClose} disabled={busy}><X size={22}/></button>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded border bg-stone-50 p-3">
        <input ref={input} type="file" accept=".xlsx" aria-label="Engineering input workbook file" disabled={busy} onChange={event => {
          const chosen = event.target.files?.[0]; if (chosen) void inspect(chosen);
        }}/>
        {workbook && <button type="button" className={`${button} bg-burnt-orange text-white`} disabled={busy} onClick={() => void save()}>Save all rows to ERP</button>}
        {workbook && <span className="text-sm">Previewing {file?.name}</span>}
        {!workbook && !file && saved && <span className="text-sm text-emerald-800">Saved workbook: {saved.filename} · {new Date(saved.uploaded_at).toLocaleString()}</span>}
      </div>

      {error && <p role="alert" className="rounded bg-red-50 p-2 text-red-700">{error}</p>}
      {activeWorkbook && <>
        <div className="flex flex-wrap items-center gap-2 rounded border p-2 text-sm" role="status">
          <strong>{activeWorkbook.total_rows} source rows retained</strong>
          <span className="rounded bg-amber-100 px-2 py-1 text-amber-900">{activeWorkbook.pending_rows} pending</span>
          <span className="rounded bg-red-100 px-2 py-1 text-red-900">{activeWorkbook.not_approved_rows} not approved</span>
          <span className="rounded bg-blue-100 px-2 py-1 text-blue-900">{activeWorkbook.ready_rows} ready for review</span>
          <span className="text-gray-600">Ready rows still require review before they can affect live master data.</span>
        </div>
        <nav className="flex flex-wrap gap-2" aria-label="Engineering workbook sheets">
          {SHEET_NAMES.map(name => <button key={name} type="button" className={`${button} ${sheet === name ? 'bg-slate-800 text-white' : 'bg-white'}`} onClick={() => setSheet(name)}>
            {name} ({activeWorkbook.sheets[name]?.row_count ?? 0})
          </button>)}
        </nav>
        <div className="min-h-0 flex-1 overflow-auto rounded border">
          <table className="min-w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-amber-50">
              <tr>
                <th className="whitespace-nowrap border p-2 text-left">Excel row</th>
                <th className="whitespace-nowrap border p-2 text-left">Reference</th>
                <th className="whitespace-nowrap border p-2 text-left">Review status</th>
                <th className="min-w-80 border p-2 text-left">Missing fields / review findings</th>
                {fields.map(field => <th key={field} className="min-w-44 border p-2 text-left">{field}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => <tr key={`${sheet}-${row.source_row}`} className="odd:bg-white even:bg-stone-50 align-top">
                <td className="border p-2">{row.source_row}</td>
                <td className="border p-2">{display(row.reference)}</td>
                <td className="whitespace-nowrap border p-2 font-medium">{row.status.replace(/_/g, ' ')}</td>
                <td className="max-w-96 border p-2">
                  {row.missing_fields.length > 0 && <div className="text-amber-900"><strong>Missing:</strong> {row.missing_fields.join(', ')}</div>}
                  {row.validation_issues?.map((issue, index) => <div key={index} className="text-red-700">{issue}</div>)}
                  {row.warnings?.map((warning, index) => <div key={`warning-${index}`} className="text-amber-800">{warning}</div>)}
                  {!row.missing_fields.length && !row.validation_issues?.length && !row.warnings?.length && '—'}
                </td>
                {fields.map(field => <td key={field} className="max-w-72 whitespace-pre-wrap border p-2">{display(row.source_values[field])}</td>)}
              </tr>)}
              {!rows.length && <tr><td colSpan={fields.length + 4} className="p-6 text-center text-gray-500">No populated source rows on this sheet.</td></tr>}
            </tbody>
          </table>
        </div>
        {summary && <footer className="text-xs text-gray-500">Showing {rows.length} of {summary.row_count} populated rows on {sheet}. Source rows are kept intact; nothing is applied to Consumption Norms or the October planning baseline.</footer>}
      </>}
      {!activeWorkbook && !error && <p className="rounded border bg-stone-50 p-4 text-sm text-gray-600">Choose the engineering input workbook to preview it. Saving retains its rows as pending source data; it does not modify approved norms.</p>}
      <footer className="flex justify-end border-t pt-3"><button type="button" className={button} onClick={onClose} disabled={busy}>Close</button></footer>
    </section>
  </div>;
}
