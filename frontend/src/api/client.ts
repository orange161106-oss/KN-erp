const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;
// Share simultaneous reads (including React StrictMode's repeated effects).
// Completed responses are not cached, so new reads see current permissions/data.
const pendingReads = new Map<string, Promise<unknown>>();
export function setAccessToken(value: string | null) { pendingReads.clear(); accessToken = value; }
export function setUnauthorizedHandler(handler: (() => void) | null) { unauthorizedHandler = handler; }

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message); this.status = status; this.code = code;
  }
}

async function request<T>(endpoint: string, method: string, data?: unknown, timeoutMs?: number): Promise<T> {
  const requestToken = accessToken;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  const formData = data instanceof FormData;
  if (data !== undefined && !formData) headers['Content-Type'] = 'application/json';
  let response: Response;
  const controller = new AbortController();
  const timeout = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : undefined;
  try {
    response = await fetch(`${BASE_URL}${endpoint}`, { method, headers, signal: controller.signal, body: data === undefined ? undefined : formData ? data : JSON.stringify(data) });
  } catch {
    if (controller.signal.aborted) throw new ApiError(0, 'REQUEST_TIMEOUT', 'The preview timed out. Check the backend, then try again.');
    throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.');
  } finally { if (timeout !== undefined) clearTimeout(timeout); }
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
function read<T>(endpoint: string): Promise<T> {
  const pending = pendingReads.get(endpoint);
  if (pending) return pending as Promise<T>;
  const operation = request<T>(endpoint, 'GET');
  pendingReads.set(endpoint, operation);
  const clear = () => { if (pendingReads.get(endpoint) === operation) pendingReads.delete(endpoint); };
  // Both outcomes release the entry; failures can always be retried.
  void operation.then(clear, clear);
  return operation;
}

async function write<T>(endpoint: string, method: string, data?: unknown, timeoutMs?: number): Promise<T> {
  pendingReads.clear();
  try { return await request<T>(endpoint, method, data, timeoutMs); }
  finally { pendingReads.clear(); }
}

export const apiClient = {
  get: read,
  post: <T>(endpoint: string, data: unknown) => write<T>(endpoint, 'POST', data),
  put: <T>(endpoint: string, data: unknown) => write<T>(endpoint, 'PUT', data),
  patch: <T>(endpoint: string, data: unknown) => write<T>(endpoint, 'PATCH', data),
  delete: <T>(endpoint: string, data?: unknown) => write<T>(endpoint, 'DELETE', data),
  postFormData: <T>(endpoint: string, data: FormData, timeoutMs?: number) => write<T>(endpoint, 'POST', data, timeoutMs),
};
