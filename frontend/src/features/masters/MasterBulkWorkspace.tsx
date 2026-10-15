import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Save, Trash2, Upload, X } from 'lucide-react';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';
import ConfirmDialog from '../../components/ConfirmDialog';
import { useAuth } from '../auth/context';

type Category = 'consumables' | 'sales_parts' | 'assemble';
type Row = { id: string; [field: string]: string | null };
interface Report {
  data_rows?: number; identified_rows?: number; unique_rows?: number;
  missing_identifier_rows?: number[];
  duplicate_rows?: Array<{ identifier: string; first_row: number; last_row: number }>;
}
interface Catalog {
  category: Category; review_token: string; row_count: number; records: Row[];
  filename: string | null; report: Report;
}
const FIELDS: Record<Category, Array<[string, string, boolean]>> = {
  consumables: [['supplier_id', 'Supplier ID', false], ['supplier_name', 'Supplier Name', true], ['item_id', 'Item ID', false],
    ['description', 'Description', true], ['category', 'Category', true], ['type_of_material', 'Type of Material', true],
    ['output_unit', 'Stock Unit', false], ['rate', 'Rate', true]],
  sales_parts: [['part_no', 'Part No.', false], ['item_id', 'Item ID', false], ['part_description', 'Part Description', true], ['uom', 'Stock Unit', false]],
  assemble: [['consumable_item', 'Consumable Item', false], ['part_no_saleable_item', 'Saleable Part No.', false],
    ['used_for_name_of_saleable_part', 'Saleable Part Name', true], ['used_part_no_prd_order', 'PRD Part No.', true],
    ['process_name', 'Process', false], ['material_thickness_in_mm_gsm', 'Thickness / GSM', true],
    ['no_of_process_per_part', 'Process Count', true], ['output_unit', 'Stock Unit', false], ['rate', 'Rate', true]],
};
const validUnit = (value: string | null) => Boolean(value && value.length <= 16 && /[a-z]/i.test(value) &&
  !/^(?:[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?|nan|[+-]?infinity)$/i.test(value.replace(/,/g, '')));

export default function MasterBulkWorkspace({ category, label, onClose, onChanged }: {
  category: Category; label: string; onClose: () => void; onChanged: () => void;
}) {
  const { user } = useAuth();
  const superAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canUpload = superAdmin || Boolean(user?.masters_create);
  const canEdit = superAdmin || Boolean(user?.masters_update);
  const canDelete = superAdmin || Boolean(user?.masters_delete);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [draft, setDraft] = useState<Catalog | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [records, setRecords] = useState<Row[]>([]);
  const [original, setOriginal] = useState(new Map<string, Row>());
  const [selected, setSelected] = useState(new Set<string>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [epoch, setEpoch] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [bulkUnit, setBulkUnit] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const requestId = useRef(0);
  const endpoint = `/api/v1/masters/product-master/${category}/workspace`;
  const staged = Boolean(file);
  const unitField = category === 'sales_parts' ? 'uom' : 'output_unit';
  const columns = useMemo<ColumnDef<Row>[]>(() => FIELDS[category].map(([key, title, editable]) => ({
    key, label: title, isEditable: editable || (staged && key === unitField),
    width: key.includes('description') || key.includes('name') ? 260 : 160,
    type: key === 'rate' || key === 'no_of_process_per_part' ? 'number' : 'text',
  })), [category, staged, unitField]);
  const changes = useMemo(() => records.flatMap(row => {
    const before = original.get(row.id);
    const changed = Object.fromEntries(FIELDS[category].filter(([key, , editable]) => (editable || (staged && key === unitField)) &&
      String(row[key] ?? '') !== String(before?.[key] ?? '')).map(([key]) => [key, row[key]]));
    return Object.keys(changed).length ? [{ id: row.id, changes: changed }] : [];
  }), [records, original, category, staged, unitField]);
  const dirty = staged || changes.length > 0;
  const invalidUnits = useMemo(() => staged ? records.filter(row => !validUnit(row[unitField])) : [], [records, staged, unitField]);
  const report = draft?.report ?? catalog?.report;
  const mayEdit = staged ? canUpload : canEdit;
  const accept = useCallback((data: Catalog) => {
    setCatalog(data); setDraft(null); setFile(null); setRecords(data.records);
    setOriginal(new Map(data.records.map(row => [row.id, row]))); setSelected(new Set()); setEpoch(previous => previous + 1);
  }, []);
  useEffect(() => {
    const id = ++requestId.current;
    setBusy(true); setError(''); setMessage(''); setCatalog(null);
    void apiClient.get<Catalog>(endpoint).then(data => { if (requestId.current === id) accept(data); })
      .catch(failure => { if (requestId.current === id) { setError(failure.message); setRecords([]); } })
      .finally(() => { if (requestId.current === id) setBusy(false); });
    return () => { ++requestId.current; };
  }, [endpoint, accept]);

  async function upload(selectedFile: File) {
    if (pending.current || dirty || !canUpload || !catalog || catalog.row_count > 0) return;
    if (!selectedFile.name.toLowerCase().endsWith('.xlsx') || selectedFile.size > 15 * 1024 * 1024) {
      setError('Choose an .xlsx workbook of at most 15 MB.'); return;
    }
    pending.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const body = new FormData(); body.append('file', selectedFile);
      const data = await apiClient.postFormData<Catalog>(`${endpoint}/preview`, body);
      setDraft(data); setFile(selectedFile); setRecords(data.records);
      setOriginal(new Map(data.records.map(row => [row.id, row]))); setSelected(new Set()); setEpoch(previous => previous + 1);
      setMessage(`${data.row_count} unique items ready for review. Click Save changes to save this upload.`);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Upload failed.'); }
    finally { pending.current = false; setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  async function save() {
    if (pending.current || !dirty || !mayEdit || !catalog) return;
    if (invalidUnits.length) { setError(`${invalidUnits.length} rows need a valid stock unit. Edit Stock Unit or apply the correct unit below before saving.`); return; }
    pending.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const review = { review_token: draft?.review_token ?? catalog.review_token, updates: changes };
      let data: Catalog;
      if (file) {
        const body = new FormData(); body.append('file', file); body.append('review', JSON.stringify(review));
        data = await apiClient.postFormData<Catalog>(endpoint, body);
      } else data = await apiClient.patch<Catalog>(endpoint, review);
      accept(data); onChanged(); setMessage(`${data.row_count} items saved successfully.`);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Save failed.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function remove() {
    if (pending.current || !catalog?.row_count || !reason.trim() || !canDelete) return;
    pending.current = true; setBusy(true); setError('');
    try {
      accept(await apiClient.delete<Catalog>(endpoint, { review_token: catalog.review_token, reason: reason.trim() }));
      setDeleteOpen(false); setReason(''); setMessage('Existing data removed from this tab. Upload and review the replacement workbook, then save.'); onChanged();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Delete failed.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function exportExcel() {
    if (busy || !catalog?.row_count || dirty) return;
    pending.current = true; setBusy(true); setError('');
    try {
      const response = await fetch(`${getApiBaseUrl()}${endpoint}/export`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
      if (!response.ok) throw new Error('Unable to export the catalog. Refresh your session and try again.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `Product_Master_${category}.xlsx`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Export failed.'); }
    finally { pending.current = false; setBusy(false); }
  }
  const close = () => { if (!busy && (!dirty || window.confirm('Discard the unsaved upload or changes?'))) onClose(); };
  const button = 'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40';

  return <div role="dialog" aria-modal="true" aria-labelledby="bulk-upload-modal-title" className="fixed inset-0 z-50 bg-black/40 p-4 flex items-center justify-center">
    <div className="w-full max-w-[96vw] h-[92dvh] bg-white rounded-xl shadow-xl p-5 flex flex-col min-h-0 gap-3">
      <header className="flex justify-between items-start gap-3">
        <div><h2 id="bulk-upload-modal-title" className="text-xl font-bold">Bulk Excel Intake</h2>
          <p className="text-sm">{label}</p><p className="text-xs text-stone-600 mt-1">Upload, review, then Save changes. Delete existing data before uploading a replacement. History and reference IDs are retained.</p></div>
        <button type="button" aria-label="Close bulk import" onClick={close} disabled={busy}><X size={22}/></button>
      </header>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-stone-50 p-3">
        <input aria-label="Master Excel file" ref={fileInput} type="file" accept=".xlsx" hidden
          onChange={event => { const selectedFile = event.target.files?.[0]; if (selectedFile) void upload(selectedFile); }}/>
        <button type="button" className={`${button} bg-erp-orange text-white`} disabled={busy || dirty || !canUpload || !catalog || catalog.row_count > 0} onClick={() => fileInput.current?.click()}><Upload size={16}/>Upload data</button>
        <button type="button" className={`${button} text-red-700`} disabled={busy || dirty || !canDelete || !catalog?.row_count}
          onClick={() => { setReason(''); setDeleteOpen(true); }}><Trash2 size={16}/>Delete data</button>
        <button type="button" className={`${button} bg-emerald-600 text-white`} disabled={busy || !dirty || !mayEdit} onClick={() => void save()}><Save size={16}/>Save changes</button>
        <button type="button" className={button} disabled={busy || dirty || !catalog?.row_count} onClick={() => void exportExcel()}><Download size={16}/>Export Excel</button>
        {staged && <button type="button" className={button} disabled={busy} onClick={() => { if (catalog) accept(catalog); setError(''); setMessage('Upload discarded.'); }}>Discard upload</button>}
        {!busy && <span role="status" className={`ml-auto text-sm ${dirty ? 'text-amber-700' : 'text-emerald-800'}`}>{dirty ? 'Not saved yet' : `Saved · ${records.length} items`}</span>}
      </div>
      {report?.identified_rows !== undefined && <details className="rounded border bg-stone-50 p-2 text-sm">
        <summary>Workbook checks: {report.identified_rows} rows with IDs · {report.unique_rows} unique items · {report.duplicate_rows?.length ?? 0} duplicates · {report.missing_identifier_rows?.length ?? 0} rows without IDs</summary>
        {Boolean(report.missing_identifier_rows?.length) && <p>Skipped worksheet rows without required IDs: {report.missing_identifier_rows?.join(', ')}.</p>}
        {report.duplicate_rows?.map((row, index) => <p key={index}>{row.identifier}: worksheet rows {row.first_row} and {row.last_row}. The last row is used; review its values.</p>)}
      </details>}
      {invalidUnits.length > 0 && <div className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
        <p>{invalidUnits.length} rows need valid stock unit labels. Review numeric Output/Unit values and blank Unit cells before saving. A separate Unit column can contain PCS, KG, LTR or the actual stock unit.</p>
        <label>Correct unit for these rows <input aria-label="Reviewed stock unit" value={bulkUnit} maxLength={16} onChange={event => setBulkUnit(event.target.value)} className="border rounded p-1 ml-2 w-28"/></label>
        <button type="button" className={`${button} ml-2`} disabled={busy || !canUpload} onClick={() => {
          const value = bulkUnit.trim().toUpperCase();
          if (!validUnit(value)) { setError('Enter the actual stock unit, such as PCS or KG.'); return; }
          setRecords(previous => previous.map(row => validUnit(row[unitField]) ? row : { ...row, [unitField]: value })); setError('');
        }}>Apply to unresolved units</button>
      </div>}
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {message && <p className="text-emerald-800">{message}</p>}
      <p className="text-xs text-stone-600">{draft?.filename || catalog?.filename ? `File: ${draft?.filename ?? catalog?.filename} · ${records.length} unique items` : 'Current master catalog. No month or year is required.'}</p>
      <div className="flex-1 min-h-0 flex flex-col">
        <DataTable key={`${endpoint}:${epoch}`} virtualize columns={columns} data={records} originalData={original}
          selectedIds={selected} onSelectionChange={setSelected} isLoading={busy} canCreate={false} canDelete={false} canUpdate={mayEdit && !busy}
          onCellChange={(id, key, value) => setRecords(previous => previous.map(row => row.id === id ? { ...row, [key]: value } : row))}
          onSave={save} onDiscardChanges={() => { setRecords(Array.from(original.values())); setEpoch(previous => previous + 1); }}
          saveStatus={busy ? 'saving' : 'idle'} storageKey={`master-catalog-${category}`} emptyMessage="No master data. Upload an Excel workbook to review it."/>
      </div>
      <ConfirmDialog isOpen={deleteOpen} title={`Delete ${label} data?`} isDestructive isLoading={busy}
        message={`Remove all ${catalog?.row_count ?? 0} active rows in this tab. Other tabs are unchanged. History and mapping IDs are retained; matching imports restore the same IDs.`}
        confirmLabel="Delete data" isConfirmDisabled={!reason.trim()} onConfirm={() => void remove()} onCancel={() => !busy && setDeleteOpen(false)}
        details={<label>Reason<input aria-label="Deletion reason" maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} className="w-full rounded border p-2 mt-1"/></label>}/>
    </div>
  </div>;
}
