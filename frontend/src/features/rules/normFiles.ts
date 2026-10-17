import { getAccessToken, getApiBaseUrl } from '../../api/client';
import { NORM_ENDPOINT } from './types';

export async function downloadNormFile(kind: 'template' | 'export', format: 'xlsx' | 'csv') {
  const token = getAccessToken();
  const response = await fetch(`${getApiBaseUrl()}${NORM_ENDPOINT}/${kind}?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.message === 'string' ? body.message : `Could not download the ${kind}. Please try again.`);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url; link.download = `Consumption_Norms_${kind}.${format}`;
  document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}
