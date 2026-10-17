import { useState } from 'react';
import { useApi } from './useApi';
import { useDebouncedValue } from './useDebouncedValue';
import { endpoint } from './types';
import type { Master, Page, Resource } from './types';
export default function ReferenceSelect({ resource, label, value, onChange }: {
  resource: Resource; label: string; value: string; onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState('');
  const settledSearch = useDebouncedValue(search);
  const options = useApi<Page<Master>>(`${endpoint(resource)}?is_active=true&limit=100&q=${encodeURIComponent(settledSearch)}`);
  return <fieldset className="space-y-2">
    <label className="block text-sm">Search {label.toLowerCase()}<input value={search} onChange={e => setSearch(e.target.value)} maxLength={100} className="mt-1 w-full border rounded p-2" /></label>
    <label className="block text-sm font-medium">{label}<select aria-label={label} required value={value} onChange={e => onChange(e.target.value)} className="mt-1 w-full border rounded p-2">
      <option value="">Select {label.toLowerCase()}</option>
      {value && !options?.data?.items.some(item => item.id === value) && <option value={value}>Current selection (retained)</option>}
      {options?.data?.items.map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}
    </select></label>
    {!options && <p role="status" className="text-sm text-gray-500">Loading choices…</p>}
    {options?.error && <p role="alert" className="text-sm text-red-700">{options.error}</p>}
    {options?.data && options.data.total > 100 && <p className="text-sm text-gray-600">Type a more specific search to find your selection.</p>}
  </fieldset>;
}
