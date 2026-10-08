import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';

const BASE = '/api/v1/purchase-orders';
type Demand = { approval_id: string; supplier_id: string; supplier_name: string; consumable_code: string; consumable_name: string;
  unit_code: string; approved_quantity: string | null; remaining_quantity: string | null; eligible: boolean; limitation: string | null };
type Line = { id: string; approval_id: string; code: string; name: string; unit_code: string; ordered_quantity: string;
  pending_quantity: string | null; expected_delivery: string; line_value: string | null;
  received_quantity: string; accepted_quantity: string; rejected_quantity: string;
  pricing: { unit_rate: string; currency: string; approval_reference: string } | null;
  approval_snapshot: { approved_qty: string; reviewed_by: string; reviewed_at: string; reason: string | null };
  recommendation_evidence: { engine_version: string; raw_quantity: string; recommended_quantity: string;
    projection: { source_set_id: string; stock_snapshot_id: string; requirement_fingerprint: string } } };
type Order = { id: string; po_number: string; supplier_name: string; po_date: string; status: 'DRAFT' | 'ISSUED' | 'CANCELLED';
  total_value: string | null; currency: string | null; pending_basis: string; items: Line[];
  fulfilment_status: string;
  history: { action: string; at: string; reason: string; actor_id: string }[] };
type DraftLine = { approval_id: string; quantity: string; delivery: string; rate: string };
const message = (error: unknown) => error instanceof Error ? error.message : 'The request failed. Please retry.';
const field = 'border rounded p-2 w-full bg-white';
const button = 'rounded bg-brand-navy text-white px-4 py-2 disabled:opacity-50';

export default function PurchaseOrders() {
  const { user } = useAuth();
  const can = (permission: string) => Boolean(user?.is_super_admin || user?.permissions.includes(permission));
  const canRead = can('purchase.orders.read');
  const [orders, setOrders] = useState<Order[]>([]);
  const [demands, setDemands] = useState<Demand[]>([]);
  const [selected, setSelected] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [offset, setOffset] = useState(0);
  const [demandOffset, setDemandOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [poDate, setPoDate] = useState('');
  const [reason, setReason] = useState('');
  const [actionReason, setActionReason] = useState('');
  const [currency, setCurrency] = useState('');
  const [places, setPlaces] = useState('');
  const [rounding, setRounding] = useState('');
  const [priceReference, setPriceReference] = useState('');
  const retry = useRef<{ body: string; key: string } | null>(null);

  const loadPage = useCallback(() => Promise.all([
    apiClient.get<Order[]>(`${BASE}?limit=25&offset=${offset}`),
    apiClient.get<Demand[]>(`${BASE}/eligible?limit=25&offset=${demandOffset}`),
  ]), [offset, demandOffset]);
  const reload = useCallback(async () => {
    if (!canRead) return;
    try {
      const [rows, eligible] = await loadPage();
      setOrders(rows); setDemands(eligible); setError('');
    } catch (failure) { setError(message(failure)); }
    finally { setLoading(false); }
  }, [canRead, loadPage]);
  useEffect(() => {
    if (!canRead) return;
    let active = true;
    void loadPage().then(([rows, eligible]) => {
      if (active) { setOrders(rows); setDemands(eligible); setError(''); }
    }).catch(failure => { if (active) setError(message(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [canRead, loadPage]);

  if (!canRead) return <p role="alert">You do not have permission to view purchase orders.</p>;
  const changeLine = (index: number, change: Partial<DraftLine>) => setLines(old => old.map((line, i) => i === index ? { ...line, ...change } : line));
  const create = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('');
    try {
      const first = demands.find(row => row.approval_id === lines[0]?.approval_id);
      if (!first || !lines.length) throw new Error('Select at least one approved recommendation.');
      const data = { supplier_id: first.supplier_id, po_date: poDate, reason,
        items: lines.map(line => ({ approval_id: line.approval_id, ordered_quantity: line.quantity,
          expected_delivery: new Date(line.delivery).toISOString(), pricing: line.rate ? {
            unit_rate: line.rate, currency, decimal_places: Number(places), rounding, approval_reference: priceReference,
          } : null })) };
      if (lines.some(line => line.rate) && (!currency || places === '' || !rounding || !priceReference)) {
        throw new Error('Enter currency, decimal places, rounding and the pricing approval reference.');
      }
      const body = JSON.stringify(data);
      if (retry.current?.body !== body) retry.current = { body, key: crypto.randomUUID() };
      const saved = await apiClient.post<Order>(BASE, { ...data, creation_key: retry.current.key });
      setSelected(saved); setCreating(false); setLines([]); retry.current = null;
      await reload(); setSuccess('Purchase order draft saved. Stock is unchanged.');
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  const act = async (action: 'issue' | 'cancel') => {
    if (!selected) return;
    setBusy(true); setError(''); setSuccess('');
    try {
      const saved = await apiClient.post<Order>(`${BASE}/${selected.id}/${action}`, { reason: actionReason });
      setSelected(saved); setActionReason(''); await reload(); setSuccess(action === 'issue' ? 'PO issued as a commitment. Stock is unchanged.' : 'Draft cancelled; approved demand is available again.');
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  const view = async (id: string) => {
    setBusy(true); setError('');
    try { setSelected(await apiClient.get<Order>(`${BASE}/${id}`)); setActionReason(''); }
    catch (failure) { setError(message(failure)); } finally { setBusy(false); }
  };
  return <section className="max-w-7xl mx-auto space-y-5">
    <div className="flex justify-between gap-4"><div><h2 className="text-2xl font-bold">Purchase orders</h2>
      <p className="text-gray-600">A PO commits to a purchase. It does not receive stock or record consumption.</p></div>
      {can('purchase.orders.create') && <button className={button} onClick={() => { setCreating(!creating); setError(''); }} disabled={busy}>New purchase order</button>}</div>
    {error && <p role="alert" className="bg-red-50 border border-red-200 p-3 rounded">{error}</p>}
    {success && <p role="status" className="bg-green-50 p-3 rounded">{success}</p>}
    {loading && <p role="status">Loading purchase orders…</p>}
    {creating && <form onSubmit={create} className="bg-white border rounded p-5 space-y-4">
      <h3 className="font-semibold text-lg">Create from approved demand</h3>
      <p>Choose recommendations for one supplier. Drafts reserve the selected approved quantity.</p>
      <div className="grid sm:grid-cols-2 gap-3"><label>PO date<input type="date" required className={field} value={poDate} onChange={e => setPoDate(e.target.value)} /></label>
        <label>Creation reason<input required className={field} value={reason} onChange={e => setReason(e.target.value)} /></label></div>
      {!demands.length && <p>No reviewed recommendations on this page.</p>}
      <ul className="space-y-2">{demands.map(d => <li key={d.approval_id} className="border rounded p-3">
        <span className="font-medium">{d.consumable_code} — {d.consumable_name}</span> · {d.supplier_name} · Available: {d.remaining_quantity ?? 'Unknown'} {d.unit_code}
        {d.limitation && <p className="text-amber-800">{d.limitation}</p>}
        <button type="button" className="ml-3 underline" disabled={!d.eligible || busy || lines.some(l => l.approval_id === d.approval_id) ||
          (!!lines.length && demands.find(v => v.approval_id === lines[0].approval_id)?.supplier_id !== d.supplier_id)}
          onClick={() => setLines([...lines, { approval_id: d.approval_id, quantity: d.remaining_quantity ?? '', delivery: '', rate: '' }])}>Add {d.consumable_code}</button>
      </li>)}</ul>
      <div className="flex gap-4"><button type="button" disabled={demandOffset === 0 || !!lines.length || loading} onClick={() => { setLoading(true); setDemandOffset(Math.max(0, demandOffset - 25)); }}>Previous demand</button>
        <button type="button" disabled={demands.length < 25 || !!lines.length || loading} onClick={() => { setLoading(true); setDemandOffset(demandOffset + 25); }}>More demand</button></div>
      {lines.map((line, i) => <div className="grid md:grid-cols-4 gap-3 border-t pt-3" key={line.approval_id}>
        <label>Ordered quantity {i + 1}<input required inputMode="decimal" className={field} value={line.quantity} onChange={e => changeLine(i, { quantity: e.target.value })} /></label>
        <label>Expected delivery {i + 1}<input required type="datetime-local" className={field} value={line.delivery} onChange={e => changeLine(i, { delivery: e.target.value })} /></label>
        {can('purchase.orders.price') && <label>Approved unit rate {i + 1} (optional)<input inputMode="decimal" className={field} value={line.rate} onChange={e => changeLine(i, { rate: e.target.value })} /></label>}
        <button type="button" onClick={() => setLines(lines.filter((_, index) => index !== i))}>Remove line {i + 1}</button>
      </div>)}
      {lines.some(line => line.rate) && <fieldset className="grid sm:grid-cols-2 gap-3"><legend className="font-semibold">Approved pricing terms</legend>
        <label>Currency code<input className={field} required pattern="[A-Z]{3}" value={currency} onChange={e => setCurrency(e.target.value)} placeholder="Three-letter currency code" /></label>
        <label>Value decimal places<select className={field} required value={places} onChange={e => setPlaces(e.target.value)}><option value="">Select approved precision</option>{[0, 1, 2, 3, 4].map(p => <option key={p}>{p}</option>)}</select></label>
        <label>Rounding<select className={field} required value={rounding} onChange={e => setRounding(e.target.value)}><option value="">Select approved rule</option><option value="HALF_UP">Half up</option><option value="HALF_EVEN">Half even</option><option value="DOWN">Down</option></select></label>
        <label>Pricing approval reference<input className={field} required value={priceReference} onChange={e => setPriceReference(e.target.value)} /></label>
      </fieldset>}
      <p className="text-sm text-gray-600">Delivery times use your local timezone. Unpriced lines remain unknown; tax and freight are not calculated.</p>
      <button className={button} disabled={busy || !lines.length}>Save draft</button>
    </form>}
    <div className="bg-white border rounded overflow-x-auto"><table className="w-full text-left"><thead><tr>{['PO', 'Supplier', 'Date', 'Status', 'Value', ''].map((h, i) => <th className="p-3 border-b" key={i}>{h}</th>)}</tr></thead>
      <tbody>{orders.map(order => <tr key={order.id}><td className="p-3 break-all">{order.po_number}</td><td>{order.supplier_name}</td><td>{order.po_date}</td><td>{order.status}</td><td>{order.total_value === null ? 'Not fully priced' : `${order.total_value} ${order.currency}`}</td>
        <td><button disabled={busy} className="underline p-3" onClick={() => void view(order.id)}>View {order.po_number}</button></td></tr>)}</tbody></table>
      {!loading && !orders.length && <p className="p-4">No purchase orders on this page.</p>}</div>
    <div className="flex gap-4"><button disabled={offset === 0 || loading} onClick={() => { setLoading(true); setOffset(Math.max(0, offset - 25)); }}>Previous orders</button><button disabled={orders.length < 25 || loading} onClick={() => { setLoading(true); setOffset(offset + 25); }}>More orders</button></div>
    {selected && <article className="bg-white border rounded p-5 space-y-4"><h3 className="text-lg font-semibold">{selected.po_number} · {selected.status}</h3>
      <p>{selected.supplier_name} · PO date {selected.po_date}</p>
      {selected.pending_basis === 'IMPORTED_ACCEPTED_GRNS' && <p className="bg-amber-50 p-3">Receipt status: {selected.fulfilment_status}. Pending quantity uses imported accepted usable GRNs. ERP receipts not yet imported are not included; this is not a live fulfilment report.</p>}
      {selected.items.map(line => <section key={line.id} className="border-t pt-3 space-y-2"><h4 className="font-semibold">{line.code} — {line.name}</h4>
        <p>Ordered: {line.ordered_quantity} {line.unit_code} · Pending commitment: {line.pending_quantity ?? 'Unknown'} · Expected: {new Date(line.expected_delivery).toLocaleString()}</p>
        <p>Received: {line.received_quantity} · Accepted usable: {line.accepted_quantity} · Rejected: {line.rejected_quantity}</p>
        <p>Unit rate: {line.pricing?.unit_rate ?? 'Not approved'} · Line value: {line.line_value ?? 'Unknown'} {line.pricing?.currency ?? ''}</p>
        <details><summary className="cursor-pointer">Approval and calculation traceability</summary><dl className="text-sm space-y-1 break-all">
          <dt>Approval</dt><dd>{line.approval_id} · Approved quantity: {line.approval_snapshot.approved_qty}</dd>
          <dt>Reviewed by / at</dt><dd>{line.approval_snapshot.reviewed_by} · {line.approval_snapshot.reviewed_at}</dd>
          <dt>Review reason</dt><dd>{line.approval_snapshot.reason ?? 'No quantity override'}</dd>
          <dt>Recommendation</dt><dd>{line.recommendation_evidence.engine_version} · Raw: {line.recommendation_evidence.raw_quantity} · Recommended: {line.recommendation_evidence.recommended_quantity}</dd>
          <dt>Projection source / stock snapshot</dt><dd>{line.recommendation_evidence.projection.source_set_id} / {line.recommendation_evidence.projection.stock_snapshot_id}</dd>
          {line.pricing && <><dt>Pricing reference</dt><dd>{line.pricing.approval_reference}</dd></>}
        </dl></details></section>)}
      {selected.status === 'DRAFT' && (can('purchase.orders.issue') || can('purchase.orders.cancel')) && <div className="space-y-3">
        <label>Action reason<input className={field} value={actionReason} onChange={e => setActionReason(e.target.value)} /></label>
        <div className="flex gap-3">{can('purchase.orders.issue') && <button className={button} disabled={busy || !actionReason.trim()} onClick={() => void act('issue')}>Issue PO</button>}
          {can('purchase.orders.cancel') && <button className={button} disabled={busy || !actionReason.trim()} onClick={() => void act('cancel')}>Cancel draft</button>}</div>
      </div>}
      <h4 className="font-semibold">History</h4><ul>{selected.history.map((entry, i) => <li key={i}>{entry.action} · {new Date(entry.at).toLocaleString()} · {entry.reason}</li>)}</ul>
    </article>}
  </section>;
}
