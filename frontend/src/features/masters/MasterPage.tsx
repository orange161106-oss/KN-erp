import { useState } from 'react';
import { useAuth } from '../auth/context';
import MasterForm from './MasterForm';
import StatusForm from './StatusForm';
import SupplierMappings from './SupplierMappings';
import ReferenceName from './ReferenceName';
import { useApi } from './useApi';
import { useDebouncedValue } from './useDebouncedValue';
import { endpoint, titles } from './types';
import type { Master, Page, Resource } from './types';
import { TableSkeleton } from '../../components/ui/Skeleton';
export default function MasterPage({ resource }: { resource: Resource }) {
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const settledSearch = useDebouncedValue(search);
  const [status, setStatus] = useState('true');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState<{ kind: 'create' | 'edit' | 'status'; record?: Master } | null>(null);
  const [supplier, setSupplier] = useState<Master | null>(null);
  const isSuperAdmin = Boolean(user?.is_super_admin);
  const canWrite = Boolean(isSuperAdmin || user?.permissions?.includes(`masters.${resource}.write`) || user?.permissions?.includes('masters.write'));
  const canCreate = Boolean(canWrite || user?.masters_create);
  const canUpdate = Boolean(canWrite || user?.masters_update);
  const canDelete = Boolean(canWrite || user?.masters_delete);
  const url = `${endpoint(resource)}?limit=25&offset=${offset}&q=${encodeURIComponent(settledSearch)}${status ? `&is_active=${status}` : ''}`;
  const result = useApi<Page<Master>>(url, revision);
  const saved = () => { setForm(null); setSupplier(null); setRevision(value => value + 1); };
  return <section className="space-y-5">
    <div className="flex items-center justify-between"><h2 className="text-xl font-semibold text-brand-navy">{titles[resource]}</h2>
      {canCreate && <button onClick={() => setForm({ kind: 'create' })} className="bg-brand-navy text-white rounded px-4 py-2">Add {resource === 'units' ? 'unit' : resource === 'suppliers' ? 'supplier' : 'consumable'}</button>}
    </div>
    {!canCreate && !canUpdate && <p className="text-sm text-gray-600">You have read-only access.</p>}
    {form?.kind !== 'status' && form && <MasterForm key={`${resource}:${form.record?.id || 'new'}`} resource={resource} record={form.record} onSaved={saved} onCancel={() => setForm(null)} />}
    {form?.kind === 'status' && form.record && <StatusForm key={form.record.id} resource={resource} record={form.record} label={form.record.code} onSaved={saved} onCancel={() => setForm(null)} />}
    <div className="flex flex-wrap gap-4">
      <label className="text-sm">Search code or name<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} maxLength={100} className="block mt-1 border rounded p-2" /></label>
      <label className="text-sm">Status<select aria-label="Status" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }} className="block mt-1 border rounded p-2"><option value="true">Active</option><option value="false">Inactive</option><option value="">All</option></select></label>
      <button onClick={() => setRevision(value => value + 1)} className="self-end border rounded px-4 py-2">Refresh</button>
    </div>
    {!result && <TableSkeleton columns={resource === 'consumables' ? 5 : 4} rows={5} />}
    {result?.error && <p role="alert" className="text-red-700">{result.error}</p>}
    {result?.data && <>
      <div className="overflow-x-auto bg-white border rounded-lg"><table className="w-full text-sm text-left">
        <thead className="bg-gray-50"><tr><th className="p-3">Code</th><th className="p-3">Name</th>{resource === 'consumables' && <th className="p-3">Unit</th>}<th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead>
        <tbody>{result.data.items.map(record => <tr key={record.id} className="border-t"><td className="p-3 font-medium">{record.code}</td><td className="p-3">{record.name}</td>
          {resource === 'consumables' && <td className="p-3">{record.unit_id && (isSuperAdmin || user?.masters_read || user?.permissions?.includes('masters.units.read')) ? <ReferenceName resource="units" id={record.unit_id} /> : 'Unit read access required'}</td>}
          <td className="p-3">{record.is_active ? 'Active' : 'Inactive'}</td>
          <td className="p-3"><div className="flex flex-wrap gap-3">
            {canUpdate && <button onClick={() => setForm({ kind: 'edit', record })} className="text-brand-navy underline">Edit</button>}
            {canDelete && <button onClick={() => setForm({ kind: 'status', record })} className="text-brand-navy underline">{record.is_active ? 'Deactivate' : 'Reactivate'}</button>}
            {resource === 'suppliers' && (isSuperAdmin || user?.masters_read || user?.permissions?.includes('masters.suppliers.read')) && <button onClick={() => setSupplier(record)} className="text-brand-navy underline">Consumable mappings</button>}
          </div></td></tr>)}</tbody>
      </table>{result.data.items.length === 0 && <p className="p-5 text-gray-600">No matching {resource}.</p>}</div>
      <div className="flex items-center gap-4 text-sm"><span>{result.data.total} records</span><button disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 25))} className="border rounded px-3 py-1 disabled:opacity-40">Previous</button><button disabled={offset + 25 >= result.data.total} onClick={() => setOffset(value => value + 25)} className="border rounded px-3 py-1 disabled:opacity-40">Next</button></div>
    </>}
    {supplier && <SupplierMappings key={supplier.id} supplier={supplier} onClose={() => setSupplier(null)} />}
  </section>;
}
