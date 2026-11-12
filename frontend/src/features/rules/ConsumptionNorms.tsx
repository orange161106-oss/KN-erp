import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import DataTable from '../../components/DataTable';
import type { ColumnDef } from '../../components/DataTable';
import { AuthContext } from '../auth/context';
import NormSetup from './NormSetup';
import NormImportWorkspace from './NormImportWorkspace';
import { downloadNormFile } from './normFiles';
import { NORM_ENDPOINT } from './types';
import type { ConsumptionNorm, NormReferenceData } from './types';

const RULE_TYPES = ['PRODUCTION_RATE', 'AREA_COVERAGE', 'PACKING_RATIO', 'TOOL_LIFE', 'FIXED_QUANTITY', 'PLANT_REQUEST', 'MAINTENANCE', 'MIN_MAX'];
const REFERENCE_FIELDS = ['part_number', 'part_name', 'used_part_number', 'thickness', 'process_count', 'reference_production_qty', 'reference_schedule_qty', 'sch', 'prd_order', 'is_general', 'sch_overridden', 'output_per_unit'] as const;

type NormRow = ConsumptionNorm & Record<typeof REFERENCE_FIELDS[number], any> & {
  s_no: number;
  parameters_json: string;
  flags: string;
};

function gridRow(norm: ConsumptionNorm, index: number, allNorms: ConsumptionNorm[]): NormRow {
  const reference = norm.reference_data || {};
  const params = norm.parameters || {};
  const isGeneral = Boolean(reference.is_general ?? params.is_general ?? (!norm.product_id && !reference.part_number));
  const partNo = reference.part_number || norm.product_part_number || norm.product_code || '';
  const procCount = String(reference.process_count ?? params.process_count ?? '');
  const prdOrder = String(reference.reference_production_qty ?? params.prd_order ?? '1');
  const sch = String(reference.reference_schedule_qty ?? reference.sch ?? params.sch ?? params.rate ?? '');
  const outputPerUnit = String(norm.output_per_unit ?? reference.output_per_unit ?? '');

  const flagList: string[] = [];
  if (isGeneral) flagList.push('General');

  // Check duplicate group: same product, process, consumable
  const sameGroup = allNorms.filter(n =>
    n.id !== norm.id && n.is_active &&
    String(n.product_id || n.reference_data?.part_number) === String(norm.product_id || reference.part_number) &&
    String(n.process_id || n.process_name) === String(norm.process_id || norm.process_name) &&
    String(n.consumable_id || n.consumable_code) === String(norm.consumable_id || norm.consumable_code)
  );
  if (sameGroup.length > 0) flagList.push('Duplicate group');

  // Check sch discrepancy
  const calcSch = Number(prdOrder || 1) * Number(procCount || 0);
  if (sch && !isGeneral && Number(sch) !== calcSch) {
    flagList.push('Sch differs');
  }

  return {
    ...norm,
    s_no: index + 1,
    part_number: partNo,
    part_name: reference.part_name || norm.product_name || '',
    used_part_number: reference.used_part_number || norm.product_part_number || norm.product_code || '',
    thickness: String(reference.thickness ?? ''),
    process_count: procCount,
    reference_production_qty: prdOrder,
    reference_schedule_qty: sch,
    output_per_unit: outputPerUnit,
    sch: sch,
    prd_order: prdOrder,
    parameters_json: JSON.stringify(norm.parameters),
    is_general: isGeneral,
    sch_overridden: Boolean(reference.sch_overridden),
    flags: flagList.join(', ') || 'Normal',
  };
}

export default function ConsumptionNorms() {
  const auth = useContext(AuthContext);
  const user = auth?.user;
  const superAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const modern = Boolean(user && ['consumption_norms_read', 'consumption_norms_create', 'consumption_norms_update'].some(flag => flag in user));
  const canRead = superAdmin || Boolean(modern ? user?.consumption_norms_read : user?.permissions?.some(code => ['norms.read', 'masters.read', 'masters.write'].includes(code)));
  const canCreate = superAdmin || Boolean(modern ? user?.consumption_norms_create : user?.permissions?.some(code => ['norms.write', 'masters.write'].includes(code)));
  const canUpdate = superAdmin || Boolean(modern ? user?.consumption_norms_update : user?.permissions?.some(code => ['norms.write', 'masters.write'].includes(code)));
  const [norms, setNorms] = useState<ConsumptionNorm[]>([]);
  const [rows, setRows] = useState<NormRow[]>([]);
  const [original, setOriginal] = useState(new Map<string, NormRow>());
  const [selected, setSelected] = useState(new Set<string>());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [search, setSearch] = useState('');
  const [processFilter, setProcessFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<'ALL' | 'PRODUCT_LINKED' | 'GENERAL'>('ALL');
  const [warningFilter, setWarningFilter] = useState(false);
  const [ruleFilter, setRuleFilter] = useState('');
  const [history, setHistory] = useState(false);
  const [reason, setReason] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const pending = useRef(false);
  const requestId = useRef(0);
  const loadNorms = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true); setError('');
    try {
      const data = await apiClient.get<ConsumptionNorm[]>(NORM_ENDPOINT);
      if (id !== requestId.current) return;
      const records = data.map((norm, idx) => gridRow(norm, idx, data));
      setNorms(data); setRows(records); setOriginal(new Map(records.map(row => [row.id, row])));
      setSelected(new Set()); setEpoch(value => value + 1);
    } catch (failure) { if (id === requestId.current) setError(failure instanceof Error ? failure.message : 'Could not load consumption norms.'); }
    finally { if (id === requestId.current) setLoading(false); }
  }, []);
  useEffect(() => {
    if (canRead) void loadNorms();
    return () => { ++requestId.current; };
  }, [canRead, loadNorms]);
  const changedRows = useMemo(() => rows.filter(row => {
    const before = original.get(row.id);
    return row.is_active && before && ([...REFERENCE_FIELDS, 'parameters_json', 'rounding_policy', 'rounding_precision', 'effective_from', 'effective_to'] as const)
      .some(key => String(row[key] ?? '') !== String(before[key] ?? ''));
  }), [rows, original]);
  const dirty = changedRows.length > 0;
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter(row => {
      if (!history && !row.is_active) return false;
      if (processFilter && row.process_name !== processFilter) return false;
      if (ruleFilter && row.rule_type !== ruleFilter) return false;
      if (categoryFilter === 'PRODUCT_LINKED' && row.is_general) return false;
      if (categoryFilter === 'GENERAL' && !row.is_general) return false;
      if (warningFilter && (!row.flags || row.flags === 'Normal')) return false;
      if (term && ![row.part_number, row.used_part_number, row.part_name, row.product_code, row.product_item_id, row.consumable_code, row.consumable_name, row.flags]
        .some(value => String(value || '').toLowerCase().includes(term))) return false;
      return true;
    });
  }, [rows, search, processFilter, ruleFilter, categoryFilter, warningFilter, history]);
  const processes = useMemo(() => [...new Set(rows.map(row => row.process_name).filter((value): value is string => Boolean(value)))].sort(), [rows]);
  function discard() { setRows(Array.from(original.values())); setReason(''); setError(''); setEpoch(value => value + 1); }
  async function save() {
    if (pending.current || !canUpdate || !dirty) return;
    setError(''); setMessage('');
    if (!reason.trim()) { setError('Enter a change reason before saving.'); return; }
    const updates = [];
    for (const row of changedRows) {
      let parameters: Record<string, unknown>;
      try { parameters = JSON.parse(row.parameters_json); }
      catch { setError(`Invalid formula parameters for ${row.consumable_code || row.id}. Enter a JSON object.`); return; }
      if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) {
        setError('Formula parameters must be a JSON object containing approved values.'); return;
      }
      const precision = Number(row.rounding_precision);
      if (!Number.isInteger(precision) || precision < 0 || precision > 4) { setError('Decimal places must be an integer from 0 to 4.'); return; }
      const before = original.get(row.id)!;
      const reference: NormReferenceData = { ...before.reference_data };
      REFERENCE_FIELDS.forEach(key => { (reference as any)[key] = row[key] ?? null; });
      const update: Record<string, unknown> = { norm_id: row.id, expected_version: before.version };
      if (row.parameters_json !== before.parameters_json) update.parameters = parameters;
      if (REFERENCE_FIELDS.some(key => row[key] !== before[key])) update.reference_data = reference;
      if (row.rounding_policy !== before.rounding_policy) update.rounding_policy = row.rounding_policy;
      if (String(row.rounding_precision) !== String(before.rounding_precision)) update.rounding_precision = precision;
      if (row.effective_from !== before.effective_from) update.effective_from = row.effective_from;
      if (String(row.effective_to ?? '') !== String(before.effective_to ?? '')) update.effective_to = row.effective_to || null;
      updates.push(update);
    }
    pending.current = true; setBusy(true);
    try {
      const result = await apiClient.post<{ updated_count: number }>(`${NORM_ENDPOINT}/bulk-update`, { updates, reason: reason.trim() });
      setReason(''); await loadNorms(); setMessage(`${result.updated_count} norms saved as reviewed versions. Earlier versions remain in history.`);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Changes could not be saved.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function download(kind: 'template' | 'export', format: 'xlsx' | 'csv') {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try { await downloadNormFile(kind, format); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Download failed.'); }
    finally { pending.current = false; setBusy(false); }
  }

  function toggleSchLock(id: string) {
    if (!canUpdate || busy) return;
    setRows(previous => previous.map(row => {
      if (row.id !== id) return row;
      const nextOverridden = !row.sch_overridden;
      const updated = { ...row, sch_overridden: nextOverridden };
      if (!nextOverridden) {
        const prd = Number(updated.reference_production_qty || updated.prd_order || 1);
        const proc = Number(updated.process_count || 0);
        const newSch = String(prd * proc);
        updated.reference_schedule_qty = newSch;
        updated.sch = newSch;
        try {
          const parsed = JSON.parse(updated.parameters_json || '{}');
          parsed.rate = Number(newSch);
          parsed.sch = Number(newSch);
          parsed.sch_overridden = false;
          updated.parameters_json = JSON.stringify(parsed);
        } catch (_) {}
      } else {
        try {
          const parsed = JSON.parse(updated.parameters_json || '{}');
          parsed.sch_overridden = true;
          updated.parameters_json = JSON.stringify(parsed);
        } catch (_) {}
      }
      return updated;
    }));
  }
  const columns: ColumnDef<NormRow>[] = [
    { key: 's_no', label: 'S. No.', width: 75, isEditable: false },
    { key: 'part_number', label: 'Part No.', width: 160, isEditable: true },
    { key: 'part_name', label: 'Used for- Part Name', width: 220, isEditable: true },
    { key: 'used_part_number', label: 'Used Part no (prd order)', width: 200, isEditable: true },
    { key: 'consumable_code', label: 'Cons. Item ID', width: 150, isEditable: false },
    { key: 'consumable_name', label: 'Consumable Name', width: 220, isEditable: false },
    { key: 'process_name', label: 'Process Name', width: 140, isEditable: false },
    { key: 'thickness', label: 'Part Thickness in mm', width: 150, type: 'number', isEditable: true },
    { key: 'process_count', label: 'No. of Process', width: 130, type: 'number', isEditable: true },
    { key: 'reference_production_qty', label: 'Prd. Order', width: 130, type: 'number', isEditable: true },
    {
      key: 'reference_schedule_qty',
      label: 'Sch',
      width: 140,
      type: 'number',
      isEditable: true,
      render: (value, row) => (
        <span className="inline-flex items-center gap-1 font-mono font-medium">
          <button
            type="button"
            className="hover:opacity-75 focus:outline-none"
            title={row.sch_overridden ? "Override unlocked: Sch won't auto-calculate. Click to lock & recalculate." : "Auto-calculated: Sch = Prd. Order x No.of Process. Click to unlock."}
            onClick={(e) => {
              e.stopPropagation();
              toggleSchLock(row.id);
            }}
          >
            {row.sch_overridden ? '🔓' : '🔒'}
          </button>
          {value}
        </span>
      ),
    },
    { key: 'output_per_unit', label: 'Output / Unit', width: 130, type: 'number', isEditable: true },
    { key: 'rule_type', label: 'Rule Type', width: 150, isEditable: false },
    { key: 'is_active', label: 'Status', width: 100, isEditable: false, render: value => value ? 'Active' : 'Historical' },
    {
      key: 'flags',
      label: 'Flags',
      width: 180,
      isEditable: false,
      render: value => {
        if (!value || value === 'Normal') return <span className="text-gray-400">Normal</span>;
        const badges = String(value).split(', ');
        return (
          <div className="flex flex-wrap gap-1 text-xs">
            {badges.map((b, i) => (
              <span key={i} className={`rounded px-1.5 py-0.5 font-medium ${
                b === 'General' ? 'bg-blue-100 text-blue-800' :
                b.includes('Duplicate') ? 'bg-amber-100 text-amber-800' :
                b.includes('differs') ? 'bg-orange-100 text-orange-800' : 'bg-gray-100 text-gray-700'
              }`}>
                {b}
              </span>
            ))}
          </div>
        );
      },
    },
  ];
  const button = 'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40';
  const field = 'rounded border border-gray-300 bg-white px-3 py-2 text-sm';
  if (!canRead) return <p role="alert">You do not have permission to view consumption norms.</p>;
  return <div className="space-y-5">
    <header className="rounded-xl border bg-white p-5">
      <h2 className="text-2xl font-bold">Consumption Norms</h2>
      <p className="mt-1 text-sm text-gray-600">Maintain approved product, process and consumable rules for basic requirements. New products use master data; plant routes are not required for this workflow.</p>
    </header>
    <section className="space-y-3 rounded-xl border bg-white p-4">
      <div className="flex flex-wrap gap-2">
        {canCreate && <><button className={`${button} bg-burnt-orange text-white`} type="button" disabled={busy || dirty || loading} onClick={() => setShowImport(true)}>Upload Excel / CSV</button>
          <button className={button} type="button" disabled={busy || dirty || loading} onClick={() => setShowCreate(value => !value)}>Add new norm</button></>}
        <button type="button" className={button} disabled={busy} onClick={() => void download('template', 'xlsx')}>Download Excel template</button>
        <button type="button" className={button} disabled={busy} onClick={() => void download('template', 'csv')}>Download CSV template</button>
        <button type="button" className={button} disabled={busy || dirty || loading || !norms.length} onClick={() => void download('export', 'xlsx')}>Export Excel</button>
        <button type="button" className={button} disabled={busy || dirty || loading || !norms.length} onClick={() => void download('export', 'csv')}>Export CSV</button>
        <span className="ml-auto self-center text-sm">{dirty ? `${changedRows.length} unsaved norms` : 'Saved'}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <input aria-label="Search consumption norms" className={`${field} min-w-64 flex-1`} placeholder="Search Part No., Used Part No., Item ID or consumable name" value={search} onChange={event => setSearch(event.target.value)}/>
        <select aria-label="Filter process" className={field} value={processFilter} onChange={event => setProcessFilter(event.target.value)}><option value="">All processes</option>{processes.map(value => <option key={value}>{value}</option>)}</select>
        <select aria-label="Filter category" className={field} value={categoryFilter} onChange={event => setCategoryFilter(event.target.value as any)}>
          <option value="ALL">All Categories</option>
          <option value="PRODUCT_LINKED">Product-linked only</option>
          <option value="GENERAL">General consumables only</option>
        </select>
        <label className="text-sm flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={warningFilter} onChange={event => setWarningFilter(event.target.checked)}/>
          Show warnings / duplicates only
        </label>
        <select aria-label="Filter formula" className={field} value={ruleFilter} onChange={event => setRuleFilter(event.target.value)}><option value="">All formulas</option>{RULE_TYPES.map(value => <option key={value}>{value}</option>)}</select>
        <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={history} onChange={event => setHistory(event.target.checked)}/>Show history</label>
      </div>
      {canUpdate && <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Change reason" className={`${field} flex-1`} placeholder="Reason for the reviewed changes" value={reason} maxLength={1000} disabled={busy} onChange={event => setReason(event.target.value)}/>
        <button type="button" className={`${button} bg-emerald-600 text-white`} disabled={busy || loading || !dirty} onClick={() => void save()}>Save changes</button>
        <button type="button" className={button} disabled={busy || !dirty} onClick={discard}>Cancel edits</button>
      </div>}
      <p className="text-xs text-gray-600">Prd. Order / Sch are reference values. Current production quantities are supplied in Production for sale. Master links are protected; use Add new norm to select different master records. Historical rows are read-only.</p>
      {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-700">{error}</p>}
      {message && <p role="status" className="rounded bg-green-50 p-3 text-green-800">{message}</p>}
    </section>
    {showCreate && canCreate && <NormSetup onCancel={() => setShowCreate(false)} onCreated={async () => { await loadNorms(); setShowCreate(false); setMessage('Consumption norm saved.'); }}/>}
    <section className="h-[520px] min-h-0 flex flex-col overflow-hidden rounded-xl border bg-white">
      <DataTable key={epoch} virtualize columns={columns} data={visible} originalData={original} selectedIds={selected} onSelectionChange={setSelected}
        canUpdate={canUpdate && !busy && !loading} canCreate={false} canDelete={false} isLoading={loading || busy}
        onCellChange={(id, key, value) => {
          if (!canUpdate || busy) return;
          if (!original.get(id)?.is_active) { setError('Historical versions are read-only. Edit the active version.'); return; }
          setRows(previous => previous.map(row => {
            if (row.id !== id) return row;
            const updated = { ...row, [key]: value };
            if (key === 'reference_schedule_qty' || key === 'sch') {
              updated.sch_overridden = true;
              updated.reference_schedule_qty = value;
              updated.sch = value;
              try {
                const parsed = JSON.parse(updated.parameters_json || '{}');
                parsed.rate = Number(value);
                parsed.sch = Number(value);
                parsed.sch_overridden = true;
                updated.parameters_json = JSON.stringify(parsed);
              } catch (_) {}
            }
            if (key === 'process_count' || key === 'reference_production_qty' || key === 'prd_order') {
              if (key === 'process_count') updated.process_count = value;
              if (key === 'reference_production_qty' || key === 'prd_order') {
                updated.reference_production_qty = value;
                updated.prd_order = value;
              }
              if (!updated.sch_overridden) {
                const prd = Number(updated.reference_production_qty || 1);
                const proc = Number(updated.process_count || 0);
                const newSch = String(prd * proc);
                updated.reference_schedule_qty = newSch;
                updated.sch = newSch;
              }
            }
            return updated;
          }));
        }}
        onSave={save} onDiscardChanges={discard} storageKey="consumption-norms-grid" saveStatus={busy ? 'saving' : 'idle'}
        getRowClassName={row => row.is_active ? '' : 'text-gray-500 bg-gray-50'}
        emptyMessage="No consumption norms match. Upload a workbook or add an approved norm to start."/>
    </section>
    {showImport && canCreate && <NormImportWorkspace canUpdate={canUpdate} onClose={() => setShowImport(false)} onImported={async value => { await loadNorms(); setMessage(value); }}/>}
  </div>;
}
