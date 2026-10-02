import { useState } from 'react';
import { apiClient } from '../../api/client';
import { endpoint } from './types';
export default function StatusForm({ resource, record, label, onSaved, onCancel }: {
  resource: string; record: { id: string; is_active: boolean }; label: string; onSaved: () => void; onCancel: () => void;
}) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const action = record.is_active ? 'Deactivate' : 'Reactivate';
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setPending(true); setError('');
    try { await apiClient.patch(`${endpoint(resource)}/${record.id}/status`, { is_active: !record.is_active, change_reason: reason }); onSaved(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Status change failed.'); }
    finally { setPending(false); }
  }
  return <form onSubmit={submit} className="bg-white border rounded-lg p-5 space-y-3 max-w-xl">
    <h3 className="font-semibold">{action} {label}?</h3>
    <p className="text-sm text-gray-600">Existing records and history will be retained.</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <label className="block text-sm font-medium">Reason for change<textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    <div className="flex gap-3"><button disabled={pending} className="bg-brand-navy text-white rounded px-4 py-2 disabled:opacity-50">{pending ? 'Saving…' : `Confirm ${action.toLowerCase()}`}</button><button type="button" onClick={onCancel} disabled={pending} className="border rounded px-4 py-2">Cancel</button></div>
  </form>;
}
