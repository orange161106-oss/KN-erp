import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient, setAccessToken, setUnauthorizedHandler } from '../api/client';
import ProductionMappings from '../features/mappings/ProductionMappings';
import ReferenceName from '../features/masters/ReferenceName';
import ReferenceSelect from '../features/masters/ReferenceSelect';

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const product = { id: 'product-1', code: 'P1', name: 'Product' };
afterEach(() => { setAccessToken(null); setUnauthorizedHandler(null); vi.unstubAllGlobals(); });

test('simultaneous reads share a request, but completed results are read fresh', async () => {
  let complete!: (value: Response) => void;
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  vi.stubGlobal('fetch', fetchMock);
  const first = apiClient.get('/api/v1/masters/products');
  const second = apiClient.get('/api/v1/masters/products');
  expect(fetchMock).toHaveBeenCalledTimes(1);
  complete(response([product]));
  expect(await first).toEqual([product]);
  expect(await second).toEqual([product]);
  fetchMock.mockResolvedValue(response([]));
  expect(await apiClient.get('/api/v1/masters/products')).toEqual([]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('logout/account switch cannot reuse or evict the new account pending read', async () => {
  const completions: Array<(value: Response) => void> = [];
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(() => new Promise(resolve => completions.push(resolve)));
  vi.stubGlobal('fetch', fetchMock);
  const logout = vi.fn(); setUnauthorizedHandler(logout);
  setAccessToken('old-session');
  const oldRead = apiClient.get('/api/v1/auth/me').catch(error => error);
  setAccessToken('new-session');
  const newRead = apiClient.get('/api/v1/auth/me');
  completions[0](response({ code: 'NOT_AUTHENTICATED', message: 'Expired' }, 401));
  await oldRead;
  expect(logout).not.toHaveBeenCalled();
  const sameNewRead = apiClient.get('/api/v1/auth/me');
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock.mock.calls[1][1]?.headers).toMatchObject({ Authorization: 'Bearer new-session' });
  completions[1](response({ id: 'new-user' }));
  expect(await newRead).toEqual({ id: 'new-user' });
  expect(await sameNewRead).toEqual({ id: 'new-user' });
});

test('writes invalidate pending reads so refresh cannot reuse a pre-save result', async () => {
  let complete!: (value: Response) => void;
  const fetchMock = vi.fn<typeof fetch>().mockImplementation((_input, init) => {
    if (init?.method === 'GET' && fetchMock.mock.calls.length === 1) return new Promise(resolve => { complete = resolve; });
    return Promise.resolve(response({ saved: true }));
  });
  vi.stubGlobal('fetch', fetchMock);
  const stale = apiClient.get('/api/v1/masters/products');
  await apiClient.post('/api/v1/masters/products', product);
  expect(await apiClient.get('/api/v1/masters/products')).toEqual({ saved: true });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  complete(response([])); await stale;
});

test('failed reads are retryable', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(response({ message: 'Temporary error' }, 503))
    .mockResolvedValueOnce(response([]));
  vi.stubGlobal('fetch', fetchMock);
  await expect(apiClient.get('/api/v1/masters/products')).rejects.toThrow('Temporary error');
  await expect(apiClient.get('/api/v1/masters/products')).resolves.toEqual([]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('mapping opening loads only visible data and avoids StrictMode duplicate reads', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async input => {
    const url = String(input);
    if (url.endsWith('/products')) return response([product]);
    if (url.includes('/resolve/')) return response({ product_id: product.id, product_code: 'P1', product_name: 'Product', uom: 'PCS', plant_mappings: [] });
    if (url.includes('/consumables?')) return response({ items: [] });
    return response([]);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<StrictMode><ProductionMappings /></StrictMode>);
  await screen.findByRole('option', { name: 'P1 - Product' });
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/resolve/'))).toBe(true));
  expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/products'))).toHaveLength(1);
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/product-plants'))).toBe(false);
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/consumables?'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Product-Plant Routes' }));
  await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/product-plants'))).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', { name: 'Process Consumables' }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/consumables?'))).toBe(true));
  fireEvent.click(screen.getByRole('button', { name: /Product-Plant Routes/ }));
  expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/product-plants'))).toHaveLength(1);
});

test('repeated unit names in rows share one lookup', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response({ code: 'KG', name: 'Kilogram', is_active: true }));
  vi.stubGlobal('fetch', fetchMock);
  render(<>{Array.from({ length: 25 }, (_, i) => <ReferenceName key={i} resource="units" id="unit-1" />)}</>);
  await waitFor(() => expect(screen.getAllByText('KG — Kilogram')).toHaveLength(25));
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('failed lazy mapping loads can be retried', async () => {
  let failures = 1;
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async input => {
    const url = String(input);
    if (url.endsWith('/products')) return response([]);
    if (url.endsWith('/product-plants') && failures-- > 0) return response({ message: 'Temporary database error' }, 503);
    return response([]);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<ProductionMappings />);
  fireEvent.click(screen.getByRole('button', { name: 'Product-Plant Routes' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Temporary database error');
  fireEvent.click(screen.getByRole('button', { name: 'Retry mappings' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/product-plants'))).toHaveLength(2);
});

test('search waits for a pause instead of querying on each keystroke', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response({ items: [], total: 0 }));
  vi.stubGlobal('fetch', fetchMock);
  render(<ReferenceSelect resource="units" label="Unit" value="" onChange={vi.fn()} />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const input = screen.getByLabelText('Search unit');
  fireEvent.change(input, { target: { value: 'K' } });
  fireEvent.change(input, { target: { value: 'KG' } });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(String(fetchMock.mock.calls[1][0])).toContain('q=KG');
});
