const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;
let readGeneration = 0;
// Share simultaneous reads (including React StrictMode's repeated effects).
// Completed responses are not cached, so new reads see current permissions/data.
const pendingReads = new Map<string, Promise<unknown>>();
export function setAccessToken(value: string | null) { ++readGeneration; pendingReads.clear(); accessToken = value; }
export function getAccessToken(): string | null { return accessToken; }
export function getApiBaseUrl(): string { return BASE_URL; }
export function setUnauthorizedHandler(handler: (() => void) | null) { unauthorizedHandler = handler; }

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;
  constructor(status: number, code: string, message: string, retryable = false) {
    super(message); this.status = status; this.code = code; this.retryable = retryable;
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
    if (controller.signal.aborted) throw new ApiError(0, 'REQUEST_TIMEOUT', 'The request timed out. Check the server, then try again.');
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
    throw new ApiError(response.status, typeof body?.code === 'string' ? body.code : 'API_ERROR', message,
      response.status === 503 && body?.code === 'DATABASE_UNAVAILABLE' && body?.details?.retryable === true);
  }
  return response.status === 204 ? undefined as T : response.json();
}
function read<T>(endpoint: string, timeoutMs = 30000): Promise<T> {
  const key = `${timeoutMs}:${endpoint}`;
  const pending = pendingReads.get(key);
  if (pending) return pending as Promise<T>;
  const generation = readGeneration;
  const operation = request<T>(endpoint, 'GET', undefined, timeoutMs).catch(async error => {
    // Repeat only an explicitly transient read. Account/permission changes and
    // mutations invalidate recovery; writes, schema errors and capacity are never retried.
    if (!(error instanceof ApiError) || !error.retryable || generation !== readGeneration) throw error;
    await new Promise(resolve => setTimeout(resolve, 250));
    if (generation !== readGeneration) throw error;
    return request<T>(endpoint, 'GET', undefined, timeoutMs);
  });
  pendingReads.set(key, operation);
  const clear = () => { if (pendingReads.get(key) === operation) pendingReads.delete(key); };
  // Both outcomes release the entry; failures can always be retried.
  void operation.then(clear, clear);
  return operation;
}

async function write<T>(endpoint: string, method: string, data?: unknown, timeoutMs?: number): Promise<T> {
  ++readGeneration;
  pendingReads.clear();
  try { return await request<T>(endpoint, method, data, timeoutMs); }
  finally { ++readGeneration; pendingReads.clear(); }
}

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const requestToken = accessToken;
  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };
  if (requestToken && !headers.Authorization && !headers.authorization) {
    headers.Authorization = `Bearer ${requestToken}`;
  }
  const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });
  if (response.status === 401 && requestToken === accessToken) {
    setAccessToken(null);
    unauthorizedHandler?.();
  }
  return response;
}

export const apiClient = {
  get: read,
  post: <T>(endpoint: string, data: unknown) => write<T>(endpoint, 'POST', data),
  put: <T>(endpoint: string, data: unknown) => write<T>(endpoint, 'PUT', data),
  patch: <T>(endpoint: string, data?: unknown) => write<T>(endpoint, 'PATCH', data),
  delete: <T>(endpoint: string, data?: unknown) => write<T>(endpoint, 'DELETE', data),
  postFormData: <T>(endpoint: string, data: FormData, timeoutMs?: number) => write<T>(endpoint, 'POST', data, timeoutMs),
  fetchWithAuth,
};
