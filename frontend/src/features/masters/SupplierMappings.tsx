import { useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import ReferenceSelect from './ReferenceSelect';
import ReferenceName from './ReferenceName';
import StatusForm from './StatusForm';
import { useApi } from './useApi';
import { endpoint } from './types';
import type { Mapping, Master, Page } from './types';
function MappingForm({ supplier, record, onSaved, onCancel }: {
  supplier: Master; record?: Mapping; onSaved: () => void; onCancel: () => void;
}) {
  const [consumableId, setConsumableId] = useState(record?.consumable_id || '');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setPending(true); setError('');
    const data = { supplier_id: supplier.id, consumable_id: consumableId, change_reason: reason };
    try {
      if (record) await apiClient.patch(`${endpoint('supplier-consumables')}/${record.id}`, data);
      else await apiClient.post(endpoint('supplier-consumables'), data);
      onSaved();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Mapping could not be saved.'); }
    finally { setPending(false); }
  }
  return <form onSubmit={submit} className="border rounded p-4 space-y-3 max-w-xl" aria-label={record ? 'Edit supplier mapping' : 'Create supplier mapping'}>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    <ReferenceSelect resource="consumables" label="Consumable" value={consumableId} onChange={setConsumableId} />
    <label className="block text-sm font-medium">Reason for change<textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
    <div className="flex gap-3"><button disabled={pending} className="rounded bg-brand-navy text-white px-4 py-2 disabled:opacity-50">{pending ? 'Saving…' : 'Save mapping'}</button><button type="button" disabled={pending} onClick={onCancel} className="border rounded px-4 py-2">Cancel</button></div>
  </form>;
}
export default function SupplierMappings({ supplier, onClose }: { supplier: Master; onClose: () => void }) {
  const { user } = useAuth();
  const [revision, setRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState('');
  const [form, setForm] = useState<{ kind: 'edit' | 'status'; record: Mapping } | 'create' | null>(null);
  const isSuperAdmin = Boolean(user?.is_super_admin);
  const hasModernFlags = user && ('masters_read' in user || 'masters_create' in user || 'masters_update' in user || 'masters_delete' in user);
  const canWrite = Boolean(isSuperAdmin || (hasModernFlags ? user?.masters_update : user?.permissions?.includes('masters.supplier_consumables.write')));
  const canReadConsumables = Boolean(isSuperAdmin || (hasModernFlags ? user?.masters_read : user?.permissions?.includes('masters.consumables.read')));
  const result = useApi<Page<Mapping>>(`${endpoint('supplier-consumables')}?supplier_id=${supplier.id}&limit=25&offset=${offset}${status ? `&is_active=${status}` : ''}`, revision);
  const saved = () => { setForm(null); setRevision(value => value + 1); };
  return <section className="border rounded-lg bg-white p-5 space-y-4" aria-label="Supplier mappings">
    <div className="flex justify-between gap-4"><h3 className="font-semibold">Consumable mappings — {supplier.code}</h3><button onClick={onClose} className="underline">Close mappings</button></div>
    {!supplier.is_active && <p className="text-sm text-gray-600">This supplier is inactive. Existing mappings are retained; reactivate the supplier before adding or reactivating mappings.</p>}
    {canWrite && supplier.is_active && canReadConsumables && <button onClick={() => setForm('create')} className="rounded bg-brand-navy text-white px-4 py-2">Add mapping</button>}
    {form === 'create' && <MappingForm supplier={supplier} onSaved={saved} onCancel={() => setForm(null)} />}
    {typeof form === 'object' && form?.kind === 'edit' && <MappingForm key={form.record.id} supplier={supplier} record={form.record} onSaved={saved} onCancel={() => setForm(null)} />}
    {typeof form === 'object' && form?.kind === 'status' && <StatusForm key={form.record.id} resource="supplier-consumables" record={form.record} label="supplier mapping" onSaved={saved} onCancel={() => setForm(null)} />}
    <label className="block text-sm">Mapping status<select aria-label="Mapping status" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }} className="ml-3 border rounded p-2"><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
    {!result && <p role="status">Loading mappings…</p>}{result?.error && <p role="alert" className="text-red-700">{result.error}</p>}
    {result?.data && <>
      <ul className="divide-y">{result.data.items.map(record => <li key={record.id} className="py-3 flex flex-wrap items-center gap-4">
        {canReadConsumables ? <ReferenceName resource="consumables" id={record.consumable_id} /> : <span>Consumable (read access required)</span>}<span className="text-sm">{record.is_active ? 'Active' : 'Inactive'}</span>
        {canWrite && <>{supplier.is_active && canReadConsumables && <button className="underline text-sm" onClick={() => setForm({ kind: 'edit', record })}>Edit mapping</button>}<button className="underline text-sm disabled:opacity-40" disabled={!record.is_active && !supplier.is_active} onClick={() => setForm({ kind: 'status', record })}>{record.is_active ? 'Deactivate mapping' : 'Reactivate mapping'}</button></>}
      </li>)}</ul>
      {!result.data.total && <p className="text-sm text-gray-600">No matching supplier mappings.</p>}
      <div className="flex items-center gap-4 text-sm"><span>{result.data.total} mappings</span><button disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 25))} className="border rounded px-3 py-1 disabled:opacity-40">Previous mappings</button><button disabled={offset + 25 >= result.data.total} onClick={() => setOffset(value => value + 25)} className="border rounded px-3 py-1 disabled:opacity-40">Next mappings</button></div>
    </>}
  </section>;
}
