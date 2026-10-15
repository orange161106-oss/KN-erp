import { useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { apiClient } from '../../api/client';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';
import { NORM_ENDPOINT } from './types';
import type { NormImportPreview, NormImportRow } from './types';

const FIELDS = [
  ['part_number', 'Part No.'], ['part_name', 'Used for – Part Name'], ['used_part_number', 'Used Part No. (PRD Order)'],
  ['consumable_code', 'Consumable Item ID'], ['consumable_name', 'Consumable Name'], ['process_name', 'Process Name'],
  ['thickness', 'Part Thickness (mm)'], ['process_count', 'No. of Process'],
  ['reference_production_qty', 'Reference Prd. Order'], ['reference_schedule_qty', 'Reference Sch'],
] as const;
type DraftRow = NormImportRow & { id: string };
export const normReviewRows = (rows: NormImportRow[]) => rows.map(row => ({ row_number: row.row_number,
  ...Object.fromEntries(FIELDS.map(([key]) => [key, row[key]])),
}));

export default function NormImportWorkspace({ canUpdate, onClose, onImported }: {
  canUpdate: boolean; onClose: () => void; onImported: (message: string) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<NormImportPreview | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [original, setOriginal] = useState(new Map<string, DraftRow>());
  const [selected, setSelected] = useState(new Set<string>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [edited, setEdited] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [formula, setFormula] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [rounding, setRounding] = useState('');
  const [precision, setPrecision] = useState('4');
  const [mode, setMode] = useState<'CREATE' | 'SUPERSEDE'>('CREATE');
  const [reason, setReason] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const columns = useMemo<ColumnDef<DraftRow>[]>(() => [
    { key: 'row_number', label: 'Source Row', width: 95, isEditable: false },
    ...FIELDS.map(([key, label]) => ({ key, label, width: key.includes('name') ? 230 : 175, isEditable: true,
      type: (['thickness', 'process_count', 'reference_production_qty', 'reference_schedule_qty'].includes(key) ? 'number' : 'text') as 'number' | 'text' })),
    { key: 'unit_code', label: 'Stock Unit', width: 100, isEditable: false },
    { key: 'action', label: 'Validation', width: 330, isEditable: false,
      render: (_value, row) => <div className="whitespace-normal text-xs"><strong>{row.action}</strong>{row.errors.map((issue, index) => <p key={index} className="text-red-700">{issue.field}: {issue.message}</p>)}</div> },
  ], []);
  function accept(data: NormImportPreview) {
    const values = data.rows.map(row => ({ ...row, id: `source-${row.row_number}` }));
    setPreview(data); setRows(values); setOriginal(new Map(values.map(row => [row.id, row])));
    setSelected(new Set()); setEdited(false); setEpoch(previous => previous + 1);
  }
  async function inspect(chosen?: File) {
    if (pending.current) return;
    const selectedFile = chosen ?? file;
    if (!selectedFile) return;
    if (!/\.(xlsx|csv)$/i.test(selectedFile.name) || selectedFile.size > 10 * 1024 * 1024) {
      setError('Choose an .xlsx or .csv file of at most 10 MB.'); return;
    }
    pending.current = true; setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('file', selectedFile);
      if (!chosen && preview) body.append('review', JSON.stringify({ source_sha256: preview.source_sha256, rows: normReviewRows(rows) }));
      const data = await apiClient.postFormData<NormImportPreview>(`${NORM_ENDPOINT}/import-preview`, body);
      setFile(selectedFile); accept(data);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not validate the workbook.'); }
    finally { pending.current = false; setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (pending.current || !file || !preview || edited) return;
    if (!formula || !effectiveFrom || !rounding || !reason.trim()) { setError('Choose the approved formula, effective date and rounding, then enter an import reason.'); return; }
    pending.current = true; setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('file', file);
      body.append('review', JSON.stringify({ source_sha256: preview.source_sha256, review_token: preview.review_token, rows: normReviewRows(rows), formula_choice: formula,
        effective_from: effectiveFrom, rounding_policy: rounding, rounding_precision: Number(precision), mode, reason: reason.trim() }));
      const data = await apiClient.postFormData<{ created_count: number; skipped_count: number; superseded_count: number; replayed: boolean; message: string }>(`${NORM_ENDPOINT}/import-confirm`, body);
      await onImported(data.message || `${data.created_count} norms created, ${data.superseded_count} superseded and ${data.skipped_count} existing rows skipped.`);
      onClose();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Import failed. No success was confirmed.'); }
    finally { pending.current = false; setBusy(false); }
  }
  const blocked = !preview || edited || preview.invalid_count > 0 || (preview.conflict_count > 0 && mode !== 'SUPERSEDE');
  const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
  const field = 'block w-full rounded border bg-white px-3 py-2 mt-1 text-sm';
  return <div role="dialog" aria-modal="true" aria-labelledby="norm-import-title" className="fixed inset-0 z-[10000] bg-black/40 p-4 flex items-center justify-center">
    <section className="flex h-[92dvh] w-full max-w-[96vw] min-h-0 flex-col gap-3 rounded-xl bg-white p-5 shadow-xl">
      <header className="flex justify-between gap-3"><div><h2 id="norm-import-title" className="text-xl font-bold">Import Consumption Norms</h2>
        <p className="text-sm text-gray-600">Upload → review and correct → validate → confirm. Preview does not save data. An invalid row blocks the complete import.</p></div>
        <button type="button" aria-label="Close norm import" disabled={busy} onClick={onClose}><X size={22}/></button></header>
      <div className="flex flex-wrap items-center gap-3 rounded border bg-stone-50 p-3">
        <input ref={fileInput} type="file" accept=".xlsx,.csv" aria-label="Consumption norms file" disabled={busy} onChange={event => { const chosen = event.target.files?.[0]; if (chosen) void inspect(chosen); }} />
        {preview && <button type="button" className={button} disabled={busy} onClick={() => void inspect()}>Validate reviewed rows</button>}
        {file && <span className="text-sm">{file.name} · {preview?.sheet_name}</span>}
      </div>
      {error && <p role="alert" className="rounded bg-red-50 p-2 text-red-700">{error}</p>}
      {preview && <>
        <p role="status" className="text-sm">{preview.row_count} rows · {preview.valid_count} valid · {preview.invalid_count} invalid · {preview.duplicate_count} duplicates · {preview.existing_count} existing · {preview.conflict_count} conflicts{edited && <strong className="text-amber-800"> · Changes need validation</strong>}</p>
        <p className="text-xs text-gray-600">Prd. Order and Sch are workbook reference values. Current production quantities come from Production for sale. Stock units come from the consumable master.</p>
        <div className="min-h-[180px] flex-1 overflow-hidden flex flex-col"><DataTable key={epoch} virtualize columns={columns} data={rows} originalData={original}
          selectedIds={selected} onSelectionChange={setSelected} canUpdate={!busy} canCreate={false} canDelete={false} isLoading={busy}
          onCellChange={(id, key, value) => { setRows(previous => previous.map(row => row.id === id ? { ...row, [key]: value } : row)); setEdited(true); }}
          onDiscardChanges={() => { setRows(Array.from(original.values())); setEdited(false); setEpoch(previous => previous + 1); }}
          getRowClassName={row => row.errors.length ? 'bg-red-50' : ''} storageKey="consumption-norm-import" emptyMessage="No norm rows found." /></div>
        <form onSubmit={event => void confirm(event)} className="space-y-3 border-t pt-3"><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <label>Approved formula<select required className={field} value={formula} onChange={event => setFormula(event.target.value)}><option value="">Choose formula</option><option value="PRODUCTION_RATE_FROM_PROCESS_COUNT">Production quantity × No. of Process</option></select></label>
          <label>Effective from<input required type="date" value={effectiveFrom} onChange={event => setEffectiveFrom(event.target.value)} className={field}/></label>
          <label>Rounding<select required className={field} value={rounding} onChange={event => setRounding(event.target.value)}><option value="">Choose rounding</option><option value="NONE">No rounding</option><option value="ROUND_UP">Round up</option><option value="ROUND_HALF_UP">Round half up</option><option value="ROUND_DOWN">Round down</option></select></label>
          <label>Decimal places<select className={field} value={precision} onChange={event => setPrecision(event.target.value)}>{[0, 1, 2, 3, 4].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Existing records<select className={field} value={mode} onChange={event => setMode(event.target.value as 'CREATE' | 'SUPERSEDE')}><option value="CREATE">Create new / skip identical</option>{canUpdate && <option value="SUPERSEDE">Create reviewed new versions</option>}</select></label>
          <label>Import reason<input required maxLength={1000} className={field} value={reason} onChange={event => setReason(event.target.value)}/></label>
        </fieldset><div className="flex justify-between gap-3"><p className="text-xs text-gray-600">Existing records are preserved. Conflicts require explicit new-version approval. Confirmation rechecks master records and database state.</p>
          <button type="submit" disabled={busy || blocked} className={`${button} bg-burnt-orange text-white shrink-0`}>{busy ? 'Processing…' : 'Confirm import'}</button></div></form>
      </>}
      {!preview && <p className="p-8 text-center text-gray-600">{busy ? 'Reading and validating file…' : 'Choose an Excel or CSV file to review consumption norms.'}</p>}
    </section>
  </div>;
}
