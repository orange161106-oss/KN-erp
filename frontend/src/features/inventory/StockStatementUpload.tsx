import { useState } from 'react';
import { apiClient } from '../../api/client';
interface Preview { export_id: string; generated_at: string; import_reason: string; movements: unknown[];
  snapshots: Array<{ consumable_id: string; usable_quantity: string; as_of: string }>; }

export default function StockStatementUpload({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState('Stk. statement Opening stock');
  const [cutoff, setCutoff] = useState('');
  const [generated, setGenerated] = useState('');
  const [excluded, setExcluded] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const reset = () => setPreview(null);
  const act = async (operation: () => Promise<void>) => {
    setBusy(true); setMessage('');
    try { await operation(); } catch (e) { setMessage(e instanceof Error ? e.message : 'Import failed.'); }
    finally { setBusy(false); }
  };
  return <section className="mt-6 border rounded p-5 space-y-3 bg-white">
    <h2 className="text-lg font-semibold">Daily stock statement upload</h2>
    <p>Select the central-store export. Closing quantity must be usable stock after all exclusions.</p>
    <input aria-label="Stock statement workbook" type="file" accept=".xlsx" disabled={busy}
      onChange={e => { setFile(e.target.files?.[0] || null); reset(); }} />
    <label className="block">Stock sheet name <input className="border p-1" value={sheet} onChange={e => { setSheet(e.target.value); reset(); }} /></label>
    <label className="block">Stock reported at <input type="datetime-local" value={cutoff} onChange={e => { setCutoff(e.target.value); reset(); }} /></label>
    <label className="block">Export generated at <input type="datetime-local" value={generated} onChange={e => { setGenerated(e.target.value); reset(); }} /></label>
    <label className="block"><input type="checkbox" checked={excluded} onChange={e => { setExcluded(e.target.checked); reset(); }} /> I verified this is central usable stock excluding damaged, rejected, held and reserved quantities.</label>
    <button disabled={busy || !file || !cutoff || !generated || !excluded} onClick={() => void act(async () => {
      if (!file) return;
      const data = new FormData(); data.append('file', file); data.append('sheet_name', sheet);
      data.append('as_of', new Date(cutoff).toISOString()); data.append('generated_at', new Date(generated).toISOString());
      data.append('exclusions_confirmed', 'true');
      const result = await apiClient.postFormData<Preview>('/api/v1/inventory/statement/preview', data); setPreview(result);
    })}>Validate and preview statement</button>
    {preview && <>
      <p>{preview.snapshots.length} material balances validated. Reported at {new Date(preview.snapshots[0]?.as_of || cutoff).toLocaleString()}.</p>
      <table><thead><tr><th>Material ID</th><th>Usable quantity</th></tr></thead><tbody>{preview.snapshots.map(s =>
        <tr key={s.consumable_id}><td>{s.consumable_id}</td><td>{s.usable_quantity}</td></tr>)}</tbody></table>
      <button disabled={busy} onClick={() => void act(async () => {
        const result = await apiClient.post<{ replayed: boolean }>('/api/v1/inventory/imports', preview);
        setMessage(result.replayed ? 'Already imported; no balances were duplicated.' : 'Daily usable-stock statement imported.');
        setPreview(null); onImported();
      })}>Import validated statement</button>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
