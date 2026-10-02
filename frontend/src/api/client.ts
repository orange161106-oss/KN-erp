const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;
export function setAccessToken(value: string | null) { accessToken = value; }
export function setUnauthorizedHandler(handler: (() => void) | null) { unauthorizedHandler = handler; }

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message); this.status = status; this.code = code;
  }
}

async function request<T>(endpoint: string, method: string, data?: unknown): Promise<T> {
  const requestToken = accessToken;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  const formData = data instanceof FormData;
  if (data !== undefined && !formData) headers['Content-Type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${endpoint}`, { method, headers, body: data === undefined ? undefined : formData ? data : JSON.stringify(data) });
  } catch { throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.'); }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && requestToken === accessToken) { setAccessToken(null); unauthorizedHandler?.(); }
    let message = typeof body?.message === 'string' ? body.message : `Request failed (${response.status}).`;
    if (response.status === 422 && Array.isArray(body?.details?.errors)) {
      const fields = [...new Set(body.details.errors.flatMap((error: { location?: unknown[] }) =>
        (error.location || []).slice(1).filter((field): field is string => typeof field === 'string')))];
      if (fields.length) message = `Check these fields: ${fields.join(', ')}.`;
    }
    throw new ApiError(response.status, typeof body?.code === 'string' ? body.code : 'API_ERROR', message);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const apiClient = {
  get: <T>(endpoint: string) => request<T>(endpoint, 'GET'),
  post: <T>(endpoint: string, data: unknown) => request<T>(endpoint, 'POST', data),
  patch: <T>(endpoint: string, data: unknown) => request<T>(endpoint, 'PATCH', data),
  postFormData: <T>(endpoint: string, data: FormData) => request<T>(endpoint, 'POST', data),
};
