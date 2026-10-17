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
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && ('masters_read' in user || 'masters_create' in user || 'masters_update' in user || 'masters_delete' in user);
  const canCreate = Boolean(isSuperAdmin || (hasModernFlags ? user.masters_create : user?.permissions?.includes(`masters.${resource}.write`) || user?.permissions?.includes('masters.write')));
  const canUpdate = Boolean(isSuperAdmin || (hasModernFlags ? user.masters_update : user?.permissions?.includes(`masters.${resource}.write`) || user?.permissions?.includes('masters.write')));
  const canDelete = Boolean(isSuperAdmin || (hasModernFlags ? user.masters_delete : user?.permissions?.includes(`masters.${resource}.write`) || user?.permissions?.includes('masters.write')));
  const canViewSupplierMappings = resource === 'suppliers' && Boolean(isSuperAdmin || (hasModernFlags ? user.masters_read : user?.permissions?.includes('masters.suppliers.read')));
  const hasActions = Boolean(isSuperAdmin || canUpdate || canDelete || canViewSupplierMappings);

  const url = `${endpoint(resource)}?limit=25&offset=${offset}&q=${encodeURIComponent(settledSearch)}${status ? `&is_active=${status}` : ''}`;
  const result = useApi<Page<Master>>(url, revision);
  const saved = () => { setForm(null); setSupplier(null); setRevision(value => value + 1); };
  return <section className="space-y-5">
    <div className="flex items-center justify-between"><h2 className="text-xl font-semibold text-ink-text">{titles[resource]}</h2>
      {canCreate && <button onClick={() => setForm({ kind: 'create' })} className="bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded px-4 py-2 font-medium shadow-xs transition-colors">Add {resource === 'units' ? 'unit' : resource === 'suppliers' ? 'supplier' : 'consumable'}</button>}
    </div>
    {!canCreate && !canUpdate && <p className="text-sm text-gray-600">You have read-only access.</p>}
    {form?.kind !== 'status' && form && <MasterForm key={`${resource}:${form.record?.id || 'new'}`} resource={resource} record={form.record} onSaved={saved} onCancel={() => setForm(null)} />}
    {form?.kind === 'status' && form.record && <StatusForm key={form.record.id} resource={resource} record={form.record} label={form.record.code} onSaved={saved} onCancel={() => setForm(null)} />}
    <div className="flex flex-wrap gap-4">
      <label className="text-sm">Search code or name<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} maxLength={100} className="block mt-1 border rounded p-2" /></label>
      <label className="text-sm">Status<select aria-label="Status" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }} className="block mt-1 border rounded p-2"><option value="true">Active</option><option value="false">Inactive</option><option value="">All</option></select></label>
      <button onClick={() => setRevision(value => value + 1)} className="self-end border rounded px-4 py-2 hover:bg-vanilla-surface">Refresh</button>
    </div>
    {!result && <TableSkeleton columns={(resource === 'consumables' ? 4 : 3) + (hasActions ? 1 : 0)} rows={5} />}
    {result?.error && <p role="alert" className="text-red-700">{result.error}</p>}
    {result?.data && <>
      <div className="overflow-x-auto bg-white border border-ink-text/10 rounded-lg shadow-2xs">
        <table className="w-full text-sm text-left">
          <thead className="bg-vanilla-surface border-b border-ink-text/10 text-ink-text">
            <tr>
              <th className="p-3 font-semibold">Code</th>
              <th className="p-3 font-semibold">Name</th>
              {resource === 'consumables' && <th className="p-3 font-semibold">Unit</th>}
              <th className="p-3 font-semibold">Status</th>
              {hasActions && <th className="p-3 font-semibold text-right">Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-text/10">
            {result.data.items.map(record => (
              <tr key={record.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="p-3 font-medium text-gray-900">{record.code}</td>
                <td className="p-3 text-gray-700">{record.name}</td>
                {resource === 'consumables' && (
                  <td className="p-3 text-gray-600">
                    {record.unit_id && (isSuperAdmin || user?.masters_read || user?.permissions?.includes('masters.units.read'))
                      ? <ReferenceName resource="units" id={record.unit_id} />
                      : 'Unit read access required'}
                  </td>
                )}
                <td className="p-3">
                  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                    record.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {record.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                {hasActions && (
                  <td className="p-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {canUpdate && <button onClick={() => setForm({ kind: 'edit', record })} className="text-brand-navy hover:text-indigo-800 underline">Edit</button>}
                      {canDelete && <button onClick={() => setForm({ kind: 'status', record })} className="text-brand-navy hover:text-indigo-800 underline">{record.is_active ? 'Deactivate' : 'Reactivate'}</button>}
                      {canViewSupplierMappings && <button onClick={() => setSupplier(record)} className="text-brand-navy hover:text-indigo-800 underline">Consumable mappings</button>}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {result.data.items.length === 0 && <p className="p-5 text-gray-600">No matching {resource}.</p>}
      </div>
      <div className="flex items-center gap-4 text-sm">
        <span>{result.data.total} records</span>
        <button disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 25))} className="border rounded px-3 py-1 disabled:opacity-40">Previous</button>
        <button disabled={offset + 25 >= result.data.total} onClick={() => setOffset(value => value + 25)} className="border rounded px-3 py-1 disabled:opacity-40">Next</button>
      </div>
    </>}
    {supplier && <SupplierMappings key={supplier.id} supplier={supplier} onClose={() => setSupplier(null)} />}
  </section>;
}
