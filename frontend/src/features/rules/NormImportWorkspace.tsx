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
  const [selectedErrorFilter, setSelectedErrorFilter] = useState<string | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const pending = useRef(false);

  const columns = useMemo<ColumnDef<DraftRow>[]>(() => [
    { key: 'row_number', label: 'Source Row', width: 95, isEditable: false },
    ...FIELDS.map(([key, label]) => ({ key, label, width: key.includes('name') ? 230 : 175, isEditable: true,
      type: (['process_count', 'reference_production_qty', 'reference_schedule_qty'].includes(key) ? 'number' : 'text') as 'number' | 'text' })),
    { key: 'unit_code', label: 'Stock Unit', width: 100, isEditable: false },
    { key: 'action', label: 'Validation / Flags', width: 330, isEditable: false,
      render: (_value, row) => (
        <div className="whitespace-normal text-xs space-y-1">
          <div className="flex flex-wrap items-center gap-1">
            <strong>{row.action}</strong>
            {row.is_general && <span className="rounded bg-blue-100 text-blue-800 px-1.5 py-0.5 text-[10px] font-medium">General</span>}
            {row.is_possible_duplicate && <span className="rounded bg-amber-100 text-amber-800 px-1.5 py-0.5 text-[10px] font-medium">Duplicate Group</span>}
            {row.sch_differs && <span className="rounded bg-orange-100 text-orange-800 px-1.5 py-0.5 text-[10px] font-medium">Sch differs</span>}
          </div>
          {row.warnings?.map((w, index) => <p key={index} className="text-amber-700">⚠️ {w}</p>)}
          {row.errors.map((issue, index) => <p key={index} className="text-red-700">{issue.field}: {issue.message}</p>)}
        </div>
      ) },
  ], []);

  function getErrorCategory(err: { field: string; code: string; message: string }): { key: string; label: string } {
    const msg = err.message.toLowerCase();
    if (err.field === 'consumable_code') {
      if (err.code === 'CONSUMABLE_CODE_REQUIRED' || msg.includes('blank') || msg.includes('required')) {
        return { key: 'BLANK_CONSUMABLE_ID', label: 'Blank Cons. Item ID' };
      }
      return { key: 'CONSUMABLE_NOT_IN_MASTER', label: 'Consumable not in master' };
    }
    if (err.field === 'part_number' || err.field === 'used_part_number') {
      if (err.code === 'BLANK_PART_NUMBER' || msg.includes('blank part no')) {
        return { key: 'BLANK_PART_NO', label: 'Blank Part No' };
      }
      if (err.code === 'DUPLICATE_NORM_ROW') {
        return { key: 'DUPLICATE_ROW', label: 'Duplicate row' };
      }
      return { key: 'PART_NOT_IN_MASTER', label: 'Part not in master' };
    }
    if (err.field === 'process_name') {
      return { key: 'PROCESS_NOT_IN_MASTER', label: 'Process not in master' };
    }
    if (err.field === 'reference_schedule_qty' && err.code === 'EXISTING_NORM_CONFLICT') {
      return { key: 'CONFLICT', label: 'Existing conflict' };
    }
    return { key: 'INVALID_NUMBER', label: 'Invalid number / quantity' };
  }

  const errorReasonCounts = useMemo(() => {
    const map = new Map<string, { label: string; count: number }>();
    rows.forEach(row => {
      const seenInRow = new Set<string>();
      (row.errors || []).forEach(err => {
        const { key, label } = getErrorCategory(err);
        if (!seenInRow.has(key)) {
          seenInRow.add(key);
          const current = map.get(key) || { label, count: 0 };
          current.count += 1;
          map.set(key, current);
        }
      });
    });
    return Array.from(map.entries()).map(([key, { label, count }]) => ({ key, label, count }));
  }, [rows]);

  const visibleRows = useMemo(() => {
    if (!selectedErrorFilter) return rows;
    return rows.filter(row =>
      (row.errors || []).some(err => getErrorCategory(err).key === selectedErrorFilter)
    );
  }, [rows, selectedErrorFilter]);

  const invalidRows = useMemo(() => rows.filter(r => r.errors.length > 0 || r.action === 'INVALID'), [rows]);

  function downloadErrorListCsv() {
    if (!invalidRows.length) return;
    const headers = ['Row Number', 'Part No', 'Used Part No', 'Cons. Item ID', 'Consumable Name', 'Process Name', 'Errors'];
    const dataRows = invalidRows.map(r => [
      r.row_number,
      r.part_number || '',
      r.used_part_number || '',
      r.consumable_code || '',
      r.consumable_name || '',
      r.process_name || '',
      r.errors.map(e => e.message).join('; '),
    ]);
    const csvContent = [headers.join(','), ...dataRows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Consumption_Norms_Error_List_${file?.name || 'import'}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function accept(data: NormImportPreview) {
    const values = data.rows.map(row => ({ ...row, id: `source-${row.row_number}` }));
    setPreview(data); setRows(values); setOriginal(new Map(values.map(row => [row.id, row])));
    setSelected(new Set()); setEdited(false); setSelectedErrorFilter(null); setEpoch(previous => previous + 1);
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

  async function executeConfirm(skipInvalid: boolean) {
    if (pending.current || !file || !preview || edited) return;
    if (!formula || !effectiveFrom || !rounding || !reason.trim()) { setError('Choose the approved formula, effective date and rounding, then enter an import reason.'); return; }
    pending.current = true; setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('file', file);
      body.append('review', JSON.stringify({
        source_sha256: preview.source_sha256,
        review_token: preview.review_token,
        rows: normReviewRows(rows),
        formula_choice: formula,
        effective_from: effectiveFrom,
        rounding_policy: rounding,
        rounding_precision: Number(precision),
        mode,
        reason: reason.trim(),
        skip_invalid: skipInvalid,
      }));
      const data = await apiClient.postFormData<{ created_count: number; skipped_count: number; superseded_count: number; replayed: boolean; message: string }>(`${NORM_ENDPOINT}/import-confirm`, body);
      await onImported(data.message || `${data.created_count} norms created, ${data.superseded_count} superseded and ${data.skipped_count} existing rows skipped.`);
      onClose();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Import failed. No success was confirmed.'); }
    finally { pending.current = false; setBusy(false); }
  }

  function handleFormSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (blocked) return;
    if (preview && preview.invalid_count > 0) {
      setShowConfirmModal(true);
    } else {
      void executeConfirm(false);
    }
  }

  const blocked = !preview || edited || preview.valid_count === 0 || (preview.conflict_count > 0 && mode !== 'SUPERSEDE');
  const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
  const field = 'block w-full rounded border bg-white px-3 py-2 mt-1 text-sm';

  return <div role="dialog" aria-modal="true" aria-labelledby="norm-import-title" className="fixed inset-0 z-[10000] bg-black/40 p-4 flex items-center justify-center">
    <section className="flex h-[92dvh] w-full max-w-[96vw] min-h-0 flex-col gap-3 rounded-xl bg-white p-5 shadow-xl">
      <header className="flex justify-between gap-3"><div><h2 id="norm-import-title" className="text-xl font-bold">Import Consumption Norms</h2>
        <p className="text-sm text-gray-600">Upload → review and correct → validate → confirm. Preview does not save data. Valid rows can be imported while skipping invalid rows.</p></div>
        <button type="button" aria-label="Close norm import" disabled={busy} onClick={onClose}><X size={22}/></button></header>
      <div className="flex flex-wrap items-center gap-3 rounded border bg-stone-50 p-3">
        <input ref={fileInput} type="file" accept=".xlsx,.csv" aria-label="Consumption norms file" disabled={busy} onChange={event => { const chosen = event.target.files?.[0]; if (chosen) void inspect(chosen); }} />
        {preview && <button type="button" className={button} disabled={busy} onClick={() => void inspect()}>Validate reviewed rows</button>}
        {file && <span className="text-sm">{file.name} · {preview?.sheet_name}</span>}
      </div>
      {error && <p role="alert" className="rounded bg-red-50 p-2 text-red-700">{error}</p>}
      {preview && <>
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium" role="status">
              {preview.row_count} rows · {preview.valid_count} valid · {preview.invalid_count} invalid
            </span>
            {Boolean(preview.general_count) && <span className="rounded bg-blue-100 text-blue-800 px-2 py-0.5 text-xs font-semibold">{preview.general_count} General (no part)</span>}
            {Boolean(preview.duplicate_groups_count) && <span className="rounded bg-amber-100 text-amber-800 px-2 py-0.5 text-xs font-semibold">{preview.duplicate_groups_count} Duplicate groups</span>}
            {Boolean(preview.skipped_total_count) && <span className="rounded bg-gray-100 text-gray-700 px-2 py-0.5 text-xs font-semibold">{preview.skipped_total_count} Subtotal rows skipped</span>}
            {preview.duplicate_count > 0 && <span className="text-gray-500 text-xs">· {preview.duplicate_count} duplicates</span>}
            {preview.existing_count > 0 && <span className="text-gray-500 text-xs">· {preview.existing_count} existing</span>}
            {preview.conflict_count > 0 && <span className="text-gray-500 text-xs">· {preview.conflict_count} conflicts</span>}
            {edited && <strong className="text-amber-800 text-xs"> · Changes need validation</strong>}
          </div>

          {errorReasonCounts.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
              <span className="text-gray-600 font-medium">Filter by error reason:</span>
              {selectedErrorFilter && (
                <button
                  type="button"
                  className="rounded bg-gray-200 px-2 py-0.5 text-gray-800 hover:bg-gray-300 font-semibold cursor-pointer"
                  onClick={() => setSelectedErrorFilter(null)}
                >
                  Show all ({rows.length}) ✕
                </button>
              )}
              {errorReasonCounts.map(({ key, label, count }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSelectedErrorFilter(prev => prev === key ? null : key)}
                  className={`rounded px-2 py-0.5 font-medium border transition-colors cursor-pointer ${
                    selectedErrorFilter === key
                      ? 'bg-red-700 text-white border-red-700 shadow-xs'
                      : 'bg-red-50 text-red-800 border-red-200 hover:bg-red-100'
                  }`}
                >
                  {label} ({count})
                </button>
              ))}
            </div>
          )}
        </div>

        {invalidRows.length > 0 && (
          <section className="rounded-lg border border-red-200 bg-red-50/60 p-3 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 className="font-semibold text-red-900 text-sm">
                  {invalidRows.length} invalid rows found
                </h4>
                <p className="text-xs text-red-700">
                  You can import the {preview.valid_count} valid rows and skip these invalid rows. Skipped rows are not saved.
                </p>
              </div>
              <button
                type="button"
                className="rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-800 hover:bg-red-50 shadow-xs cursor-pointer"
                onClick={downloadErrorListCsv}
              >
                Download error list (CSV)
              </button>
            </div>
            <div className="max-h-36 overflow-y-auto rounded border border-red-200 bg-white">
              <table className="w-full text-xs text-left">
                <thead className="bg-red-100/70 border-b border-red-200 text-gray-700 sticky top-0">
                  <tr>
                    <th className="p-1.5 font-medium w-16">Row #</th>
                    <th className="p-1.5 font-medium">Part No.</th>
                    <th className="p-1.5 font-medium">Cons. Item ID</th>
                    <th className="p-1.5 font-medium">Process</th>
                    <th className="p-1.5 font-medium">Reason / Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {invalidRows.map(row => (
                    <tr key={row.id} className="border-b last:border-b-0 hover:bg-red-50/40">
                      <td className="p-1.5 font-mono font-bold text-red-900">{row.row_number}</td>
                      <td className="p-1.5 font-mono">{row.part_number || '—'}</td>
                      <td className="p-1.5 font-mono">{row.consumable_code || '—'}</td>
                      <td className="p-1.5">{row.process_name || '—'}</td>
                      <td className="p-1.5 text-red-700">
                        {row.errors.map((e, idx) => (
                          <span key={idx} className="block">• {e.message}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <p className="text-xs text-gray-600">Prd. Order, Sch and Part Thickness are workbook reference values. Current production quantities come from Production for sale. Stock units come from the consumable master.</p>
        <div className="min-h-[180px] flex-1 overflow-hidden flex flex-col"><DataTable key={epoch} virtualize columns={columns} data={visibleRows} originalData={original}
          selectedIds={selected} onSelectionChange={setSelected} canUpdate={!busy} canCreate={false} canDelete={false} isLoading={busy}
          onCellChange={(id, key, value) => { setRows(previous => previous.map(row => row.id === id ? { ...row, [key]: value } : row)); setEdited(true); }}
          onDiscardChanges={() => { setRows(Array.from(original.values())); setEdited(false); setEpoch(previous => previous + 1); }}
          getRowClassName={row => row.errors.length ? 'bg-red-50' : ''} storageKey="consumption-norm-import" emptyMessage="No norm rows found." /></div>
        <form onSubmit={handleFormSubmit} className="space-y-3 border-t pt-3"><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <label>Approved formula<select required className={field} value={formula} onChange={event => setFormula(event.target.value)}><option value="">Choose formula</option><option value="PRODUCTION_RATE_FROM_PROCESS_COUNT">Production quantity × No. of Process</option></select></label>
          <label>Effective from<input required type="date" value={effectiveFrom} onChange={event => setEffectiveFrom(event.target.value)} className={field}/></label>
          <label>Rounding<select required className={field} value={rounding} onChange={event => setRounding(event.target.value)}><option value="">Choose rounding</option><option value="NONE">No rounding</option><option value="ROUND_UP">Round up</option><option value="ROUND_HALF_UP">Round half up</option><option value="ROUND_DOWN">Round down</option></select></label>
          <label>Decimal places<select className={field} value={precision} onChange={event => setPrecision(event.target.value)}>{[0, 1, 2, 3, 4].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Existing records<select className={field} value={mode} onChange={event => setMode(event.target.value as 'CREATE' | 'SUPERSEDE')}><option value="CREATE">Create new / skip identical</option>{canUpdate && <option value="SUPERSEDE">Create reviewed new versions</option>}</select></label>
          <label>Import reason<input required maxLength={1000} className={field} value={reason} onChange={event => setReason(event.target.value)}/></label>
        </fieldset><div className="flex justify-between gap-3 items-center">
          <p className="text-xs text-gray-600">Existing records are preserved. Conflicts require explicit new-version approval. Confirmation rechecks master records and database state.</p>
          <button type="submit" disabled={busy || blocked} className={`${button} bg-burnt-orange text-white shrink-0 font-medium`}>
            {busy ? 'Processing…' : 'Confirm import'}
          </button>
        </div></form>
      </>}
      {!preview && <p className="p-8 text-center text-gray-600">{busy ? 'Reading and validating file…' : 'Choose an Excel or CSV file to review consumption norms.'}</p>}
    </section>

    {showConfirmModal && preview && (
      <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10001] bg-black/50 p-4 flex items-center justify-center">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl space-y-4">
          <h3 className="text-lg font-bold text-gray-900">Confirm Norm Import</h3>
          <div className="text-sm bg-amber-50 border border-amber-200 text-amber-900 p-3 rounded-lg space-y-1">
            <p className="font-semibold">Import {preview.valid_count} valid rows, skip {preview.invalid_count} invalid rows?</p>
            <p className="text-xs text-amber-800">
              {preview.invalid_count} rows have validation errors and will NOT be saved into consumption norms.
            </p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className={button}
              disabled={busy}
              onClick={() => setShowConfirmModal(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`${button} bg-burnt-orange text-white font-medium`}
              disabled={busy}
              onClick={() => {
                setShowConfirmModal(false);
                void executeConfirm(true);
              }}
            >
              {busy ? 'Processing…' : `Import ${preview.valid_count} valid rows, skip ${preview.invalid_count} invalid rows`}
            </button>
          </div>
        </div>
      </div>
    )}
  </div>;
}
