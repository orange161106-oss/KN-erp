import { useState } from 'react';
import { apiClient } from '../../api/client';
import ReferenceSelect from './ReferenceSelect';
import { endpoint, titles } from './types';
import type { Master, Resource } from './types';
export default function MasterForm({ resource, record, onSaved, onCancel }: {
  resource: Resource; record?: Master; onSaved: () => void; onCancel: () => void;
}) {
  const [code, setCode] = useState(record?.code || '');
  const [name, setName] = useState(record?.name || '');
  const [description, setDescription] = useState(record?.description || '');
  const [unitId, setUnitId] = useState(record?.unit_id || '');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setPending(true); setError('');
    const data = { code, name, change_reason: reason, ...(resource === 'consumables' ? { description: description || null, unit_id: unitId } : {}) };
    try {
      if (record) await apiClient.patch(`${endpoint(resource)}/${record.id}`, data);
      else await apiClient.post(endpoint(resource), data);
      onSaved();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Save failed.'); }
    finally { setPending(false); }
  }
  return <form onSubmit={submit} aria-label={`${record ? 'Edit' : 'Create'} ${titles[resource].toLowerCase()}`} className="border rounded-lg bg-white p-5 space-y-4 max-w-xl">
    <h3 className="font-semibold">{record ? 'Edit' : 'Create'} {titles[resource].toLowerCase()}</h3>
    {error && <p role="alert" className="text-red-700 text-sm">{error}</p>}
    <label className="block text-sm font-medium">Code<input required maxLength={resource === 'units' ? 16 : 64} value={code} onChange={e => setCode(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    <label className="block text-sm font-medium">Name<input required maxLength={255} value={name} onChange={e => setName(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    {resource === 'consumables' && <>
      <ReferenceSelect resource="units" label="Unit" value={unitId} onChange={setUnitId} />
      <label className="block text-sm">Description<textarea maxLength={10000} value={description} onChange={e => setDescription(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    </>}
    <label className="block text-sm font-medium">Reason for change<textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    <div className="flex gap-3"><button disabled={pending} className="bg-brand-navy text-white rounded px-4 py-2 disabled:opacity-50">{pending ? 'Saving…' : 'Save'}</button><button type="button" disabled={pending} onClick={onCancel} className="border rounded px-4 py-2">Cancel</button></div>
  </form>;
}
