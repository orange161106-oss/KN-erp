import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';

const BASE = '/api/v1/reports';
const control = 'border rounded p-2 bg-white';
const button = 'rounded bg-brand-navy text-white px-4 py-2 disabled:opacity-50';
type Option = { id: string; label: string; detail: string | null };
type Page<T> = { items: T[]; total: number; limit: number; offset: number };
type Stock = { consumable_id: string; code: string; name: string; is_active: boolean; unit_code: string;
  usable_quantity: string | null; as_of: string | null; imported_at: string | null; source_export_id: string | null; availability: string };
type Projection = { status: string; is_live: false; cutoff: string; consumable_id: string; unit_id: string;
  planning_version_id: string; planning_period: string; stock_snapshot_id: string | null; stock_as_of: string | null;
  source_set_id: string | null; opening_stock: string | null; projected_stock: string | null; current_msl: string | null;
  current_msl_condition: string; projected_msl: string | null; projected_msl_condition: string;
  first_future_breach_at: string | null; future_breach: boolean | null;
  timeline: { at: string; balance_before: string; receipts: string; requirements: string; balance_after: string;
    msl: string | null; msl_condition: string; sources: string[] }[];
  limitations: { code: string; message: string; blocks_projection: boolean }[] };
type Reorder = { status: string; is_live: false; reorder_required: boolean | null; already_breached: boolean | null;
  expected_msl_crossing_at: string | null; latest_safe_order_at: string | null; explanation: string;
  limitations: { code: string; message: string }[] };
type Flow = { approval_id: string; evidence_id: string | null; submitted_at: string | null; supplier_id: string;
  supplier_code: string; supplier_name: string; consumable_id: string; consumable_code: string; consumable_name: string;
  unit_code: string; planning_version_id: string | null; recommendation_status: string; recommended_quantity: string | null;
  approval_status: string; reviewed_at: string | null; approved_quantity: string | null;
  draft_allocated_quantity: string; issued_ordered_quantity: string; received_quantity: string;
  cancelled_order_quantity: string;
  accepted_quantity: string; rejected_quantity: string; pending_quantity: string; pending_basis: string; is_live: false };
type FlowPage = Page<Flow> & { pending_only: boolean; submitted_from: string | null; submitted_until: string | null;
  po_status: string | null; po_date_from: string | null; po_date_until: string | null;
  receipt_coverage: string; is_live: false };
type GRN = { grn_id: string; source_grn_id: string; purchase_order_id: string; po_number: string;
  supplier_id: string; supplier_code: string; supplier_name: string; consumable_id: string;
  consumable_code: string; consumable_name: string; unit_id: string; unit_code: string;
  source_line_id: string; event_at: string; imported_at: string; received_quantity: string;
  accepted_quantity: string; rejected_quantity: string; stock_transaction_id: string | null;
  stock_snapshot_id: string; is_live: false };
type GRNPage = Page<GRN> & { event_from: string | null; event_until: string | null; source: string; is_live: false };
type Tab = 'stock' | 'projection' | 'supplier-plan' | 'pending' | 'grns' | 'trace';
const tabs: { id: Tab; label: string; permission: 'inventory' | 'purchase' }[] = [
  { id: 'stock', label: 'Material stock', permission: 'inventory' },
  { id: 'projection', label: 'Projected shortage / MSL', permission: 'inventory' },
  { id: 'supplier-plan', label: 'Supplier purchase plan', permission: 'purchase' },
  { id: 'pending', label: 'Pending POs', permission: 'purchase' },
  { id: 'grns', label: 'GRNs', permission: 'purchase' },
  { id: 'trace', label: 'Recommendation fulfilment', permission: 'purchase' },
];
const formatDate = (value: string | null) => value ? new Date(value).toLocaleString() : 'Not available';
const errorText = (failure: unknown) => failure instanceof Error ? failure.message : 'The report could not be loaded.';
const asUtc = (value: string) => value ? new Date(value).toISOString() : '';

function Pager({ page, total, setPage }: { page: number; total: number; setPage: (value: number) => void }) {
  return <div className="flex items-center gap-3 text-sm"><span>Page {page + 1}</span>
    <button className={control} disabled={page === 0} onClick={() => setPage(Math.max(0, page - 1))}>Previous</button>
    <button className={control} disabled={(page + 1) * 25 >= total} onClick={() => setPage(page + 1)}>Next</button></div>;
}

function SelectOption({ label, value, setValue, options, empty }: { label: string; value: string;
  setValue: (value: string) => void; options: Option[]; empty: string }) {
  return <label className="text-sm">{label}<select className={`${control} block mt-1 min-w-56`} value={value}
    onChange={event => setValue(event.target.value)}><option value="">{empty}</option>
    {options.map(option => <option key={option.id} value={option.id}>{option.label}{option.detail ? ` · ${option.detail}` : ''}</option>)}</select></label>;
}

function Table({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto border rounded bg-white"><table className="w-full text-left text-sm">{children}</table></div>;
}

export default function InventoryPurchaseReports() {
  const { user } = useAuth();
  const canInventory = !!user?.permissions.includes('reports.inventory.read');
  const canPurchase = !!user?.permissions.includes('reports.purchase.read');
  const visible = tabs.filter(tab => tab.permission === 'inventory' ? canInventory : canPurchase);
  const [tab, setTab] = useState<Tab>(visible[0]?.id ?? 'stock');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [materials, setMaterials] = useState<Option[]>([]);
  const [suppliers, setSuppliers] = useState<Option[]>([]);
  const [versions, setVersions] = useState<Option[]>([]);
  const [stock, setStock] = useState<Page<Stock> | null>(null);
  const [stockPage, setStockPage] = useState(0);
  const [search, setSearch] = useState('');
  const [active, setActive] = useState('true');
  const [projection, setProjection] = useState<Projection | null>(null);
  const [reorder, setReorder] = useState<Reorder | null>(null);
  const [flow, setFlow] = useState<FlowPage | null>(null);
  const [grns, setGrns] = useState<GRNPage | null>(null);
  const [page, setPage] = useState(0);
  const [materialId, setMaterialId] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [sourceSetId, setSourceSetId] = useState('');
  const [cutoff, setCutoff] = useState('');
  const [evaluatedAt, setEvaluatedAt] = useState('');
  const [policyEvidence, setPolicyEvidence] = useState('');
  const [leadEvidence, setLeadEvidence] = useState('');
  const [approvalStatus, setApprovalStatus] = useState('');
  const [poStatus, setPoStatus] = useState('');
  const [poDateFrom, setPoDateFrom] = useState('');
  const [poDateUntil, setPoDateUntil] = useState('');
  const [submittedFrom, setSubmittedFrom] = useState('');
  const [submittedUntil, setSubmittedUntil] = useState('');
  const [eventFrom, setEventFrom] = useState('');
  const [eventUntil, setEventUntil] = useState('');

  const loadOptions = useCallback(async () => {
    const requests: Promise<void>[] = [];
    if (canInventory || canPurchase) requests.push(apiClient.get<Option[]>(`${BASE}/options/materials?limit=100`).then(setMaterials));
    if (canInventory || canPurchase) requests.push(apiClient.get<Option[]>(`${BASE}/options/planning-versions?limit=100`).then(setVersions));
    if (canPurchase) requests.push(apiClient.get<Option[]>(`${BASE}/options/suppliers?limit=100`).then(setSuppliers));
    try { await Promise.all(requests); } catch (failure) { setError(errorText(failure)); }
  }, [canInventory, canPurchase]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadOptions(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadOptions]);

  const loadStock = useCallback(async () => {
    if (!canInventory || tab !== 'stock') return;
    setBusy(true); setError('');
    const params = new URLSearchParams({ limit: '25', offset: String(stockPage * 25) });
    if (search.trim()) params.set('q', search.trim());
    if (active) params.set('is_active', active);
    try { setStock(await apiClient.get<Page<Stock>>(`${BASE}/material-stock?${params}`)); }
    catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }, [active, canInventory, search, stockPage, tab]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadStock(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadStock]);

  const runProjection = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setProjection(null); setReorder(null);
    try {
      const params = new URLSearchParams({ consumable_id: materialId, planning_version_id: versionId, cutoff: asUtc(cutoff) });
      if (sourceSetId.trim()) params.set('source_set_id', sourceSetId.trim());
      setProjection(await apiClient.get<Projection>(`${BASE}/projected-shortage?${params}`));
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  };
  const runReorder = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setReorder(null);
    try {
      const body: Record<string, unknown> = { consumable_id: materialId, planning_version_id: versionId,
        source_set_id: sourceSetId || null, evaluated_at: asUtc(evaluatedAt), cutoff: asUtc(cutoff) };
      if (policyEvidence.trim()) body.policy = JSON.parse(policyEvidence);
      if (leadEvidence.trim()) body.lead_time = JSON.parse(leadEvidence);
      setReorder(await apiClient.post<Reorder>(`${BASE}/msl-reorder-assessment`, body));
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  };

  const loadFlow = useCallback(async () => {
    if (!canPurchase || !['supplier-plan', 'pending', 'trace'].includes(tab)) return;
    setBusy(true); setError('');
    const params = new URLSearchParams({ limit: '25', offset: String(page * 25) });
    if (tab === 'pending') {
      params.set('pending_only', 'true');
      if (supplierId) params.set('supplier_id', supplierId);
      if (materialId) params.set('consumable_id', materialId);
    } else {
      if (supplierId) params.set('supplier_id', supplierId);
      if (materialId) params.set('consumable_id', materialId);
      if (versionId) params.set('planning_version_id', versionId);
      if (approvalStatus) params.set('approval_status', approvalStatus);
    }
    if (tab !== 'pending' && poStatus) params.set('po_status', poStatus);
    if (poDateFrom) params.set('po_date_from', poDateFrom);
    if (poDateUntil) params.set('po_date_until', poDateUntil);
    if (submittedFrom) params.set('submitted_from', asUtc(submittedFrom));
    if (submittedUntil) params.set('submitted_until', asUtc(submittedUntil));
    const path = tab === 'pending' ? 'pending-purchase-orders' : tab === 'supplier-plan' ? 'supplier-purchase-plan' : 'recommendation-fulfilment';
    try { setFlow(await apiClient.get<FlowPage>(`${BASE}/${path}?${params}`)); }
    catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }, [approvalStatus, canPurchase, materialId, page, poDateFrom, poDateUntil, poStatus, submittedFrom, submittedUntil, supplierId, tab, versionId]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadFlow(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadFlow]);

  const loadGrns = useCallback(async () => {
    if (!canPurchase || tab !== 'grns') return;
    setBusy(true); setError('');
    const params = new URLSearchParams({ limit: '25', offset: String(page * 25) });
    if (supplierId) params.set('supplier_id', supplierId);
    if (materialId) params.set('consumable_id', materialId);
    if (eventFrom) params.set('event_from', asUtc(eventFrom));
    if (eventUntil) params.set('event_until', asUtc(eventUntil));
    try { setGrns(await apiClient.get<GRNPage>(`${BASE}/grns?${params}`)); }
    catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }, [canPurchase, eventFrom, eventUntil, materialId, page, supplierId, tab]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadGrns(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadGrns]);

  if (!visible.length) return <p role="alert">You do not have permission to view inventory or purchase reports.</p>;
  const queryAgain = () => { setPage(0); if (tab === 'stock') setStockPage(0); };
  const projectionForm = <form onSubmit={runProjection} className="bg-white border rounded p-4 space-y-3">
    <h3 className="font-semibold">Projected stock, MSL and shortage timeline</h3>
    <p>The result is M4.2’s dated domain report. It keeps incomplete timing or coverage visible and does not spread monthly demand.</p>
    <div className="flex flex-wrap gap-3 items-end"><SelectOption label="Material" value={materialId} setValue={setMaterialId} options={materials} empty="Select material" />
      <SelectOption label="Planning version" value={versionId} setValue={setVersionId} options={versions} empty="Select version" />
      <label className="text-sm">Exclusive report cutoff<input className={`${control} block mt-1`} type="datetime-local" required value={cutoff} onChange={event => setCutoff(event.target.value)} /></label>
      <label className="text-sm">Reconciled source set ID (optional)<input className={`${control} block mt-1`} value={sourceSetId} onChange={event => setSourceSetId(event.target.value)} /></label>
      <button className={button} disabled={busy || !materialId || !versionId || !cutoff}>Show projection</button></div>
  </form>;
  const flowFilters = <div className="bg-white border rounded p-4 flex flex-wrap gap-3 items-end">
    <SelectOption label="Supplier" value={supplierId} setValue={value => { setSupplierId(value); setPage(0); }} options={suppliers} empty="All suppliers" />
    <SelectOption label="Material" value={materialId} setValue={value => { setMaterialId(value); setPage(0); }} options={materials} empty="All materials" />
    {tab !== 'pending' && <>
      <SelectOption label="Planning version" value={versionId} setValue={value => { setVersionId(value); setPage(0); }} options={versions} empty="All versions" />
      <label className="text-sm">Approval status<select className={`${control} block mt-1`} value={approvalStatus} onChange={event => { setApprovalStatus(event.target.value); setPage(0); }}>
        <option value="">All</option>{['PENDING', 'APPROVED', 'MODIFIED', 'REJECTED'].map(value => <option key={value}>{value}</option>)}</select></label>
    </>}
    <label className="text-sm">Submitted from<input type="datetime-local" className={`${control} block mt-1`} value={submittedFrom} onChange={event => { setSubmittedFrom(event.target.value); setPage(0); }} /></label>
    <label className="text-sm">Submitted until (exclusive)<input type="datetime-local" className={`${control} block mt-1`} value={submittedUntil} onChange={event => { setSubmittedUntil(event.target.value); setPage(0); }} /></label>
      {tab !== 'pending' && <label className="text-sm">PO status<select className={`${control} block mt-1`} value={poStatus} onChange={event => { setPoStatus(event.target.value); setPage(0); }}>
        <option value="">All PO statuses</option><option value="DRAFT">Draft</option><option value="ISSUED">Issued</option><option value="CANCELLED">Cancelled</option></select></label>}
      <label className="text-sm">PO date from<input type="date" className={`${control} block mt-1`} value={poDateFrom} onChange={event => { setPoDateFrom(event.target.value); setPage(0); }} /></label>
      <label className="text-sm">PO date until (exclusive)<input type="date" className={`${control} block mt-1`} value={poDateUntil} onChange={event => { setPoDateUntil(event.target.value); setPage(0); }} /></label>
    <button type="button" className={button} disabled={busy} onClick={queryAgain}>Apply filters</button>
  </div>;

  return <section className="max-w-7xl mx-auto space-y-5">
    <div><h1 className="text-2xl font-semibold">Inventory and purchase reports</h1>
      <p className="text-gray-600">Reports show dated source evidence and domain results. Inventory and receipt figures from the existing ERP are not live.</p></div>
    {error && <p role="alert" className="bg-red-50 text-red-800 border border-red-200 rounded p-3">{error}</p>}
    <nav aria-label="Report categories" className="flex flex-wrap gap-2 border-b pb-3">
      {visible.map(item => <button key={item.id} className={`rounded px-3 py-2 ${tab === item.id ? 'bg-brand-navy text-white' : 'bg-white border'}`}
        onClick={() => { setTab(item.id); setPage(0); setError(''); }}>{item.label}</button>)}
    </nav>

    {tab === 'stock' && canInventory && <div className="space-y-4">
      <p className="bg-amber-50 rounded p-3">Latest usable snapshot from the existing ERP; no movement is added again. Historical as-of stock is not available through this report.</p>
      <div className="flex flex-wrap gap-3 items-end"><label className="text-sm">Search material<input className={`${control} block mt-1`} value={search} onChange={event => { setSearch(event.target.value); setStockPage(0); }} /></label>
        <label className="text-sm">Material status<select className={`${control} block mt-1`} value={active} onChange={event => { setActive(event.target.value); setStockPage(0); }}><option value="true">Active</option><option value="">All</option><option value="false">Inactive</option></select></label>
        <button className={button} disabled={busy} onClick={() => void loadStock()}>Refresh report</button></div>
      {busy && <p role="status">Loading material stock…</p>}
      {stock && <><Table><thead><tr>{['Material', 'Usable stock', 'Unit', 'Source time', 'Imported time', 'Source export'].map(value => <th className="p-3 border-b" key={value}>{value}</th>)}</tr></thead>
        <tbody>{stock.items.map(row => <tr className="border-b" key={row.consumable_id}><td className="p-3">{row.code} · {row.name}{!row.is_active && ' (inactive)'}</td>
          <td className="p-3">{row.usable_quantity ?? 'Not imported'}</td><td>{row.unit_code}</td><td>{formatDate(row.as_of)}</td><td>{formatDate(row.imported_at)}</td><td>{row.source_export_id ?? '—'}</td></tr>)}</tbody></Table>
        {!stock.items.length && <p>No matching materials.</p>}<Pager page={stockPage} total={stock.total} setPage={setStockPage} /></>}
    </div>}

    {tab === 'projection' && canInventory && <div className="space-y-4">{projectionForm}
      {projection && <article className="bg-white border rounded p-4 space-y-3"><div className="flex flex-wrap gap-x-6 gap-y-2">
        <p>Status: <strong>{projection.status}</strong></p><p>Projected stock: <strong>{projection.projected_stock ?? 'Unknown'}</strong></p>
        <p>Current MSL: {projection.current_msl ?? 'Unknown'} ({projection.current_msl_condition})</p>
        <p>MSL at cutoff: {projection.projected_msl ?? 'Unknown'} ({projection.projected_msl_condition})</p>
        <p>First future MSL breach: {formatDate(projection.first_future_breach_at)}</p>
        <p>Source set: {projection.source_set_id ?? 'No reconciled source set selected'}</p><p>Stock snapshot: {projection.stock_snapshot_id ?? 'Unavailable'} · {formatDate(projection.stock_as_of)}</p>
      </div>
      {!projection.is_live && <p className="bg-amber-50 rounded p-3">This projection is dated and non-live. Read each source limitation before relying on it.</p>}
      {!!projection.limitations.length && <ul className="list-disc pl-5">{projection.limitations.map((row, index) => <li key={`${row.code}-${index}`}>{row.code}: {row.message}</li>)}</ul>}
      {!!projection.timeline.length && <Table><thead><tr>{['Event time', 'Before', 'Receipts', 'Requirements', 'After', 'MSL', 'Condition', 'Sources'].map(value => <th className="p-3 border-b" key={value}>{value}</th>)}</tr></thead>
        <tbody>{projection.timeline.map((row, index) => <tr key={`${row.at}-${index}`} className="border-b"><td className="p-3">{formatDate(row.at)}</td><td>{row.balance_before}</td><td>{row.receipts}</td><td>{row.requirements}</td><td className="font-medium">{row.balance_after}</td><td>{row.msl ?? 'Unknown'}</td><td>{row.msl_condition}</td><td>{row.sources.join(', ')}</td></tr>)}</tbody></Table>}</article>}
      <details className="bg-white border rounded p-4"><summary className="cursor-pointer font-semibold">Assess reorder timing with approved evidence</summary>
        <p className="text-sm my-3">The M4.3 service requires explicit policy and lead-time evidence. No defaults are supplied. Enter these optional evidence objects as JSON exactly as approved by KNL; leaving either out returns an incomplete assessment.</p>
        <form className="space-y-3" onSubmit={runReorder}><div className="flex flex-wrap gap-3 items-end">
          <label className="text-sm">Evaluation time<input className={`${control} block mt-1`} type="datetime-local" required value={evaluatedAt} onChange={event => setEvaluatedAt(event.target.value)} /></label>
          <button className={button} disabled={busy || !materialId || !versionId || !evaluatedAt || !cutoff}>Assess reorder timing</button></div>
          <label className="block text-sm">Approved MSL policy evidence (JSON)<textarea className={`${control} mt-1 w-full font-mono`} rows={4} value={policyEvidence} onChange={event => setPolicyEvidence(event.target.value)} placeholder="Approval reference, effective interval, violation rule and availability boundary" /></label>
          <label className="block text-sm">Approved supplier lead-time evidence (JSON, optional)<textarea className={`${control} mt-1 w-full font-mono`} rows={4} value={leadEvidence} onChange={event => setLeadEvidence(event.target.value)} placeholder="Supplier, approved duration, basis and effective interval" /></label>
        </form>
        {reorder && <div className="mt-4 space-y-2"><p>Status: <strong>{reorder.status}</strong> · Reorder required: {reorder.reorder_required === null ? 'Unknown' : reorder.reorder_required ? 'Yes' : 'No'}</p>
          <p>First crossing: {formatDate(reorder.expected_msl_crossing_at)} · Latest safe order time: {formatDate(reorder.latest_safe_order_at)}</p><p>{reorder.explanation}</p>
          {reorder.limitations.map(row => <p key={row.code} className="text-amber-800">{row.code}: {row.message}</p>)}</div>}
      </details>
    </div>}

    {['supplier-plan', 'pending', 'trace'].includes(tab) && canPurchase && <div className="space-y-4">{flowFilters}
      {flow?.is_live === false && <p className="bg-amber-50 rounded p-3">Received and pending quantities reflect imported GRNs only; the ERP may have newer receipts.</p>}
      {busy && <p role="status">Loading purchase report…</p>}
      {flow && <><Table><thead><tr>{['Supplier', 'Material', 'Recommendation', 'Approved', 'Approval', 'Draft', 'Ordered', 'Cancelled', 'Received', 'Accepted', 'Rejected', 'Pending', 'Evidence'].map(value => <th className="p-3 border-b" key={value}>{value}</th>)}</tr></thead>
        <tbody>{flow.items.map(row => <tr className="border-b" key={row.approval_id}><td className="p-3">{row.supplier_code} · {row.supplier_name}</td><td>{row.consumable_code} · {row.consumable_name} ({row.unit_code})</td>
          <td>{row.recommended_quantity ?? row.recommendation_status}</td><td>{row.approved_quantity ?? 'Not approved'}</td><td>{row.approval_status}</td>
          <td>{row.draft_allocated_quantity}</td><td>{row.issued_ordered_quantity}</td><td>{row.cancelled_order_quantity}</td><td>{row.received_quantity}</td><td>{row.accepted_quantity}</td><td>{row.rejected_quantity}</td><td>{row.pending_quantity}</td>
          <td>{row.evidence_id ?? 'No saved recommendation evidence'}<span className="block text-xs text-gray-600">{row.pending_basis}</span></td></tr>)}</tbody></Table>
        {!flow.items.length && <p>No matching purchase records.</p>}<p className="text-sm text-gray-600">{flow.total} records · Recommendation status uses saved M5.1 evidence; legacy rows without evidence are unknown.</p>
        <Pager page={page} total={flow.total} setPage={setPage} /></>}
    </div>}

    {tab === 'grns' && canPurchase && <div className="space-y-4"><div className="bg-amber-50 rounded p-3">Posted receipts imported from the existing ERP. Physical, accepted and rejected quantities are separate; report coverage is not live.</div>
      <div className="bg-white border rounded p-4 flex flex-wrap gap-3 items-end"><SelectOption label="Supplier" value={supplierId} setValue={setSupplierId} options={suppliers} empty="All suppliers" />
        <SelectOption label="Material" value={materialId} setValue={setMaterialId} options={materials} empty="All materials" />
        <label className="text-sm">Event from<input type="datetime-local" className={`${control} block mt-1`} value={eventFrom} onChange={event => { setEventFrom(event.target.value); setPage(0); }} /></label>
        <label className="text-sm">Event until (exclusive)<input type="datetime-local" className={`${control} block mt-1`} value={eventUntil} onChange={event => { setEventUntil(event.target.value); setPage(0); }} /></label>
        <button className={button} disabled={busy} onClick={() => void loadGrns()}>Apply filters</button></div>
      {busy && <p role="status">Loading GRN report…</p>}
      {grns && <><Table><thead><tr>{['ERP GRN', 'PO', 'Supplier', 'Material', 'Event time', 'Received', 'Accepted', 'Rejected', 'Stock receipt', 'Balance source'].map(value => <th className="p-3 border-b" key={value}>{value}</th>)}</tr></thead>
        <tbody>{grns.items.map(row => <tr className="border-b" key={`${row.grn_id}-${row.source_line_id}`}><td className="p-3">{row.source_grn_id}<span className="block text-xs">Line {row.source_line_id}</span></td><td>{row.po_number}</td>
          <td>{row.supplier_code} · {row.supplier_name}</td><td>{row.consumable_code} · {row.consumable_name} ({row.unit_code})</td><td>{formatDate(row.event_at)}</td>
          <td>{row.received_quantity}</td><td>{row.accepted_quantity}</td><td>{row.rejected_quantity}</td><td>{row.stock_transaction_id ?? 'No accepted stock'}</td><td>{row.stock_snapshot_id}</td></tr>)}</tbody></Table>
        {!grns.items.length && <p>No imported GRN lines match these filters.</p>}<p>{grns.total} GRN lines · imported from {grns.source}</p><Pager page={page} total={grns.total} setPage={setPage} /></>}
    </div>}
  </section>;
}
