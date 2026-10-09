import { useState } from 'react';
import StockStatementUpload from './StockStatementUpload';
import type { FormEvent } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { canOpen } from '../../core/rbac';
import { useApi } from '../masters/useApi';
import { endpoint } from './types';
import type { Balance, ImportResult, InventoryStatus, Page, StockTransaction } from './types';

const control = 'border rounded p-2 bg-white';
const date = (value: string | null) => value ? new Date(value).toLocaleString() : 'Not available';
const movementName = (value: string) => ({ RECEIPT: 'Accepted receipt', ISSUE: 'Plant issue', RETURN: 'Usable plant return' })[value] || value;

function Pager({ offset, total, setOffset }: { offset: number; total: number; setOffset: (offset: number) => void }) {
  return <div className="flex gap-3 items-center mt-4 text-sm">
    <span>{total} records</span>
    <button className={control} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
    <button className={control} disabled={offset + 25 >= total} onClick={() => setOffset(offset + 25)}>Next</button>
  </div>;
}

function SourceImport({ onImported }: { onImported: () => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setResult(null);
    let payload: unknown;
    try { payload = JSON.parse(text); } catch { setError('The stock export must contain valid JSON data.'); return; }
    setBusy(true);
    try {
      const imported = await apiClient.post<ImportResult>(`${endpoint}/imports`, payload);
      setResult(imported); onImported();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Import failed.'); }
    finally { setBusy(false); }
  }
  return <section className="mt-6 bg-white border rounded p-5 space-y-3">
    <h2 className="font-semibold text-lg">Import existing ERP stock export</h2>
    <p className="text-sm text-gray-600">Use the verified stock export format. Usable balances must already exclude damaged, held and reserved material. This records source data; it does not authorize warehouse movements.</p>
    <form onSubmit={submit} className="space-y-3">
      <label className="block">Stock export data<textarea className={`${control} w-full mt-1 font-mono text-sm`} rows={6} required maxLength={2097152} value={text} onChange={event => setText(event.target.value)} disabled={busy} /></label>
      <button className="bg-brand-navy text-white rounded px-4 py-2 disabled:opacity-50" disabled={busy}>{busy ? 'Importing…' : 'Import source records'}</button>
    </form>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {result && <p role="status">{result.replayed ? 'This export was already imported. No duplicate records were added.' : `Imported ${result.movement_count} movements and ${result.snapshot_count} stock snapshots.`}</p>}
  </section>;
}

function InventoryContent() {
  const { user } = useAuth();
  const [tab, setTab] = useState<'balances' | 'history'>('balances');
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState('');
  const [active, setActive] = useState('true');
  const [balanceOffset, setBalanceOffset] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [material, setMaterial] = useState<{ id: string; code: string } | null>(null);
  const [movement, setMovement] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const status = useApi<InventoryStatus>(`${endpoint}/status`);
  const balanceParams = new URLSearchParams({ limit: '25', offset: String(balanceOffset), q: search });
  if (active) balanceParams.set('is_active', active);
  const balances = useApi<Page<Balance>>(`${endpoint}/balances?${balanceParams}`, revision);
  const historyParams = new URLSearchParams({ limit: '25', offset: String(historyOffset) });
  if (material) historyParams.set('consumable_id', material.id);
  if (movement) historyParams.set('movement', movement);
  if (since) historyParams.set('since', new Date(since).toISOString());
  if (until) historyParams.set('until', new Date(until).toISOString());
  const history = useApi<Page<StockTransaction>>(`${endpoint}/transactions?${historyParams}`, revision);
  const canImport = Boolean(user?.is_super_admin || user?.inventory_create || user?.permissions?.includes('inventory.stock.import'));
  function viewHistory(row: Balance) { setMaterial({ id: row.consumable_id, code: row.code }); setHistoryOffset(0); setTab('history'); }

  return <div className="max-w-7xl space-y-5">
    <div className="flex justify-between items-center gap-4"><h1 className="text-2xl font-semibold">Central inventory</h1>
      <button className={control} onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
    <div className="rounded border border-brand-steel bg-white p-4 text-sm space-y-1">
      <p>Stock and movements are reported by KNL's existing ERP. Opening stock, reservations, approvals and corrections stay there.</p>
      <p className="font-medium">Balances are dated reports, not a live stock feed. Check the reported time before using them.</p>
      <p>Only usable accepted material is included. Plant issues do not automatically represent consumption.</p>
    </div>
    {status?.error && <p role="alert" className="text-red-700">{status.error}</p>}
    <nav className="flex gap-4 border-b pb-2" aria-label="Inventory views">
      <button className={tab === 'balances' ? 'font-semibold underline' : ''} onClick={() => setTab('balances')}>Reported stock</button>
      <button className={tab === 'history' ? 'font-semibold underline' : ''} onClick={() => setTab('history')}>Stock history</button>
    </nav>
    {tab === 'balances' && <section className="space-y-4">
      <div className="flex flex-wrap gap-4 items-end">
        <label className="text-sm">Search code or name<input className={`${control} block mt-1`} maxLength={100} value={search} onChange={event => { setSearch(event.target.value); setBalanceOffset(0); }} /></label>
        <label className="text-sm">Material status<select aria-label="Material status" className={`${control} block mt-1`} value={active} onChange={event => { setActive(event.target.value); setBalanceOffset(0); }}>
          <option value="true">Active</option><option value="">All</option><option value="false">Inactive</option></select></label>
      </div>
      {!balances && <p role="status">Loading reported stock…</p>}
      {balances?.error && <p role="alert" className="text-red-700">{balances.error}</p>}
      {balances?.data && <>
        <div className="overflow-x-auto border rounded bg-white"><table className="w-full text-left text-sm">
          <thead className="border-b"><tr>{['Code', 'Material', 'Reported usable stock', 'Unit', 'Reported at', 'History'].map(label => <th key={label} className="p-3">{label}</th>)}</tr></thead>
          <tbody>{balances.data.items.map(row => <tr key={row.consumable_id} className="border-b last:border-0">
            <td className="p-3">{row.code}{!row.is_active && <span className="block text-gray-500">Inactive</span>}</td><td className="p-3">{row.name}</td>
            <td className="p-3 font-medium">{row.usable_quantity === null ? 'Not imported' : row.usable_quantity}</td>
            <td className="p-3">{row.unit_code}</td><td className="p-3">{date(row.as_of)}</td>
            <td className="p-3"><button className="underline" aria-label={`View history for ${row.code}`} onClick={() => viewHistory(row)}>View history</button></td>
          </tr>)}</tbody></table></div>
        {balances.data.items.length === 0 && <p>No matching consumables.</p>}
        <Pager offset={balanceOffset} total={balances.data.total} setOffset={setBalanceOffset} />
      </>}
    </section>}
    {tab === 'history' && <section className="space-y-4">
      <div className="flex gap-3 items-center"><h2 className="font-semibold">{material ? `Stock history — ${material.code}` : 'Stock history — all materials'}</h2>
        {material && <button className="underline text-sm" onClick={() => { setMaterial(null); setHistoryOffset(0); }}>Show all materials</button>}</div>
      <div className="flex gap-4 flex-wrap">
        <label className="text-sm">Movement<select aria-label="Movement" className={`${control} block mt-1`} value={movement} onChange={event => { setMovement(event.target.value); setHistoryOffset(0); }}>
          <option value="">All movements</option>{['RECEIPT', 'ISSUE', 'RETURN'].map(value => <option key={value} value={value}>{movementName(value)}</option>)}</select></label>
        <label className="text-sm">From<input type="datetime-local" className={`${control} block mt-1`} value={since} onChange={event => { setSince(event.target.value); setHistoryOffset(0); }} /></label>
        <label className="text-sm">Until<input type="datetime-local" className={`${control} block mt-1`} value={until} onChange={event => { setUntil(event.target.value); setHistoryOffset(0); }} /></label>
      </div>
      <p className="text-xs text-gray-600">Times are displayed in your local time zone. Entries were already posted in the existing ERP.</p>
      {!history && <p role="status">Loading stock history…</p>}
      {history?.error && <p role="alert" className="text-red-700">{history.error}</p>}
      {history?.data && <>
        <div className="overflow-x-auto border rounded bg-white"><table className="w-full text-left text-sm">
          <thead className="border-b"><tr>{['Event time', 'Material', 'Movement', 'Stock change', 'Source quantity', 'Source actor'].map(label => <th className="p-3" key={label}>{label}</th>)}</tr></thead>
          <tbody>{history.data.items.map(row => <tr key={row.id} className="border-b last:border-0">
            <td className="p-3">{date(row.event_at)}</td><td className="p-3">{row.code} — {row.name}</td><td className="p-3">{movementName(row.movement)}</td>
            <td className="p-3 font-medium">{row.signed_quantity.startsWith('-') ? '' : '+'}{row.signed_quantity} {row.unit_code}</td>
            <td className="p-3">{row.source_quantity} {row.source_unit_code}{row.conversion_reference && <span className="block text-xs text-gray-600">Conversion: ×{row.conversion_factor}</span>}</td>
            <td className="p-3">{row.source_actor}</td>
          </tr>)}</tbody></table></div>
        {history.data.items.length === 0 && <p>No imported movements match these filters.</p>}
        <Pager offset={historyOffset} total={history.data.total} setOffset={setHistoryOffset} />
      </>}
    </section>}
    {canImport && status?.data?.import_enabled && <>
      <StockStatementUpload onImported={() => setRevision(value => value + 1)} />
      <details><summary>Advanced source integration</summary><SourceImport onImported={() => setRevision(value => value + 1)} /></details>
    </>}
    {canImport && status?.data && !status.data.import_enabled && <p className="text-sm text-gray-600">Source imports are disabled until the export mapping is verified and enabled.</p>}
  </div>;
}

export default function Inventory() {
  const { user } = useAuth();
  return canOpen(user, '/inventory') ? <InventoryContent /> : <p role="alert">You do not have permission to view central inventory.</p>;
}
