import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
export function useApi<T>(url: string, revision = 0) {
  const key = `${url}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    apiClient.get<T>(url).then(data => { if (!cancelled) setResult({ key, data }); })
      .catch(error => { if (!cancelled) setResult({ key, error: error instanceof Error ? error.message : 'Request failed.' }); });
    return () => { cancelled = true; };
  }, [url, key]);
  return result?.key === key ? result : null;
}
