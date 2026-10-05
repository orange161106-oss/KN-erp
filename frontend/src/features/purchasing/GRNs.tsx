import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';

const BASE = '/api/v1/grns';
type ReceiptLine = { id: string; source_line_id: string; purchase_order_item_id: string; consumable_id: string;
  consumable_code: string; consumable_name: string; unit_code: string;
  unit_id: string; received_quantity: string; accepted_quantity: string; rejected_quantity: string;
  stock_transaction_id: string | null; stock_snapshot_id: string };
type Receipt = { id: string; source_grn_id: string; purchase_order_id: string; supplier_id: string;
  po_number: string; supplier_name: string;
  event_at: string; source_actor: string; imported_at: string; reason: string; items: ReceiptLine[]; replayed: boolean };
type SourceFile = { source_grn_id: string; purchase_order_id: string; event_at: string;
  items: { source_line_id: string; received_quantity: string; accepted_quantity: string; rejected_quantity: string }[] };
const message = (error: unknown) => error instanceof Error ? error.message : 'Unable to load receipts. Please retry.';
const button = 'rounded bg-brand-navy text-white px-4 py-2 disabled:opacity-50';

function preview(value: unknown): SourceFile {
  if (!value || typeof value !== 'object') throw new Error('Choose a normalized ERP receipt export.');
  const source = value as Partial<SourceFile>;
  if (typeof source.source_grn_id !== 'string' || typeof source.purchase_order_id !== 'string'
      || typeof source.event_at !== 'string' || !Array.isArray(source.items) || !source.items.length) {
    throw new Error('This file is missing receipt details. Ask for a normalized ERP GRN export.');
  }
  for (const line of source.items) {
    if (!line || typeof line.source_line_id !== 'string' || ['received_quantity', 'accepted_quantity', 'rejected_quantity']
      .some(field => typeof line[field as keyof typeof line] !== 'string')) {
      throw new Error('Receipt quantities must be exact decimal text in the ERP export.');
    }
  }
  return source as SourceFile;
}

export default function GRNs() {
  const { user } = useAuth();
  const canRead = !!user?.permissions.includes('purchase.grns.read');
  const canImport = !!user?.permissions.includes('purchase.grns.import') && !!user?.permissions.includes('inventory.stock.import');
  const [rows, setRows] = useState<Receipt[]>([]);
  const [selected, setSelected] = useState<Receipt | null>(null);
  const [source, setSource] = useState<SourceFile | null>(null);
  const [payload, setPayload] = useState<unknown>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const load = useCallback(() => apiClient.get<Receipt[]>(`${BASE}?limit=25&offset=${offset}`), [offset]);
  useEffect(() => {
    if (!canRead) return;
    let active = true;
    void load().then(receipts => { if (active) { setRows(receipts); setError(''); } })
      .catch(failure => { if (active) setError(message(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [canRead, load]);

  const choose = async (file?: File) => {
    setSource(null); setPayload(null); setError(''); setSuccess('');
    if (!file) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('Choose an export smaller than 1 MB.');
      const parsed: unknown = JSON.parse(await file.text());
      setSource(preview(parsed)); setPayload(parsed);
    } catch (failure) { setError(message(failure)); }
  };
  const importReceipt = async () => {
    setBusy(true); setError(''); setSuccess('');
    try {
      const saved = await apiClient.post<Receipt>(BASE + '/imports', payload);
      setSelected(saved); setSource(null); setPayload(null);
      setSuccess(saved.replayed ? 'This receipt was already imported. No quantities were added again.' : 'Receipt imported. Accepted quantities are linked to the PO and reported stock.');
      setRows(await load());
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  const view = async (id: string) => {
    setBusy(true); setError('');
    try { setSelected(await apiClient.get<Receipt>(`${BASE}/${id}`)); }
    catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  if (!canRead) return <p role="alert">You do not have permission to view goods receipts.</p>;
  return <section className="space-y-5">
    <h2 className="text-2xl font-semibold">Goods receipts</h2>
    <p>The existing ERP posts receipts. This screen imports posted receipts and their reported usable stock. Accepted material fulfils the PO; rejected material remains pending for replacement.</p>
    <p className="bg-amber-50 p-3 rounded">Figures reflect imported ERP records, with source dates shown below. They are not a live warehouse balance. Receipts above the outstanding quantity require KNL confirmation.</p>
    {error && <p role="alert" className="bg-red-50 p-3 rounded">{error}</p>}
    {success && <p role="status" className="bg-green-50 p-3 rounded">{success}</p>}
    {canImport && <div className="bg-white border rounded p-4 space-y-3">
      <label className="block">Posted ERP receipt export<input aria-label="Posted ERP receipt export" type="file" accept=".json,application/json" disabled={busy}
        className="block mt-2" onChange={event => { void choose(event.target.files?.[0]); }} /></label>
      <p>Use the verified normalized export containing the PO reference, inspection result, stock events and post-receipt usable balance.</p>
      {source && <div className="space-y-2"><h3 className="font-semibold">Review receipt {source.source_grn_id}</h3>
        <p>PO reference: {source.purchase_order_id} · Receipt time: {source.event_at}</p>
        <ul>{source.items.map(line => <li key={line.source_line_id}>{line.source_line_id}: Received {line.received_quantity} · Accepted {line.accepted_quantity} · Rejected {line.rejected_quantity}</li>)}</ul>
        <button className={button} disabled={busy} onClick={() => { void importReceipt(); }}>Import posted receipt</button>
      </div>}
    </div>}
    {loading && <p role="status">Loading receipts…</p>}
    {!loading && !rows.length && <p>No imported receipts on this page.</p>}
    {!!rows.length && <div className="overflow-x-auto"><table className="w-full bg-white text-left"><thead><tr><th className="p-3">ERP receipt</th><th>PO reference</th><th>Receipt time</th><th>Imported</th><th>Details</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><td className="p-3">{row.source_grn_id}</td><td className="break-all">{row.po_number}</td><td>{new Date(row.event_at).toLocaleString()}</td><td>{new Date(row.imported_at).toLocaleString()}</td>
        <td><button className={button} disabled={busy} onClick={() => { void view(row.id); }}>View {row.source_grn_id}</button></td></tr>)}</tbody></table></div>}
    <div className="flex gap-3"><button disabled={offset === 0 || busy} onClick={() => setOffset(value => Math.max(0, value - 25))}>Previous receipts</button>
      <button disabled={rows.length < 25 || busy} onClick={() => setOffset(value => value + 25)}>Next receipts</button></div>
    {selected && <article className="bg-white border rounded p-4 space-y-3"><h3 className="text-lg font-semibold">{selected.source_grn_id}</h3>
      <p>{selected.po_number} · {selected.supplier_name}</p>
      <p>Source operator: {selected.source_actor} · Reason: {selected.reason}</p>
      {selected.items.map(line => <div key={line.id} className="border rounded p-3 space-y-2"><p>Source line: {line.source_line_id} · PO item: {line.purchase_order_item_id}</p>
        <p>{line.consumable_code} · {line.consumable_name} · Unit: {line.unit_code}</p>
        <p>Received: {line.received_quantity} · Accepted usable: {line.accepted_quantity} · Rejected: {line.rejected_quantity}</p>
        <p>Stock receipt reference: {line.stock_transaction_id ?? 'None—no accepted usable quantity'}</p>
        <p>Reported balance reference: {line.stock_snapshot_id}</p></div>)}
    </article>}
  </section>;
}
