import { useApi } from './useApi';
import { endpoint } from './types';
import type { Master, Resource } from './types';
export default function ReferenceName({ resource, id }: { resource: Resource; id: string }) {
  const result = useApi<Master>(`${endpoint(resource)}/${id}`);
  return <span>{result?.data ? `${result.data.code} — ${result.data.name}${result.data.is_active ? '' : ' (inactive)'}` : result?.error ? 'Details unavailable' : 'Loading details…'}</span>;
}
