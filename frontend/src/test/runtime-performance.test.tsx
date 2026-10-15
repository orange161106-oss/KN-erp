import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient, setAccessToken } from '../api/client';
import DataTable from '../components/DataTable';
import Statement from '../features/inventory/StockStatementWorkspace';
import Management from '../features/inventory/StockManagementWorkspace';
import { AuthContext } from '../features/auth/context';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const unavailable = (category = 'connection', retryable = true) => reply({
  code: 'DATABASE_UNAVAILABLE', message: 'Database is unavailable.', details: { category, retryable },
}, 503);

test('simultaneous transient reads share one bounded automatic recovery', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(unavailable()).mockResolvedValue(reply({ value: 'fresh' }));
  vi.stubGlobal('fetch', fetchMock);
  const first = apiClient.get('/api/v1/inventory/statement');
  const second = apiClient.get('/api/v1/inventory/statement');
  expect(await first).toEqual({ value: 'fresh' });
  expect(await second).toEqual({ value: 'fresh' });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test.each(['schema', 'credentials', 'capacity'])('does not retry %s failures', async category => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(unavailable(category, false));
  vi.stubGlobal('fetch', fetchMock);
  await expect(apiClient.get('/api/v1/masters/products')).rejects.toThrow('Database is unavailable.');
  expect(fetchMock).toHaveBeenCalledOnce();
});

test('never repeats a stock save, deletion or login after an ambiguous failure', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async () => unavailable());
  vi.stubGlobal('fetch', fetchMock);
  await expect(apiClient.patch('/api/v1/inventory/management/batch-update', {})).rejects.toThrow();
  await expect(apiClient.delete('/api/v1/inventory/statement', {})).rejects.toThrow();
  await expect(apiClient.post('/api/v1/auth/login', {})).rejects.toThrow();
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test('account switch prevents a delayed retry from running under another user', async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async () => unavailable());
  vi.stubGlobal('fetch', fetchMock);
  setAccessToken('old');
  const result = apiClient.get('/api/v1/auth/me').catch(error => error);
  await vi.advanceTimersByTimeAsync(1);
  setAccessToken('new');
  await vi.advanceTimersByTimeAsync(300);
  expect(await result).toMatchObject({ code: 'DATABASE_UNAVAILABLE' });
  expect(fetchMock).toHaveBeenCalledOnce();
});

test('a mutation invalidates any scheduled read recovery', async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (_input, options) =>
    options?.method === 'GET' ? unavailable() : reply({ saved: true }));
  vi.stubGlobal('fetch', fetchMock);
  const result = apiClient.get('/api/v1/inventory/statement').catch(error => error);
  await vi.advanceTimersByTimeAsync(1);
  await apiClient.patch('/api/v1/inventory/statement/batch-update', {});
  await vi.advanceTimersByTimeAsync(300);
  expect(await result).toMatchObject({ code: 'DATABASE_UNAVAILABLE' });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

const initial = Array.from({ length: 5000 }, (_, index) => ({ id: `row-${index}`, name: `Material ${index}`, quantity: String(index) }));
const originals = new Map(initial.map(row => [row.id, row]));
const largeColumns = [{ key: 'name', label: 'Material', isEditable: false }, { key: 'quantity', label: 'Quantity' }] as const;
function LargeGrid() {
  const [rows, setRows] = useState(initial);
  const [selected, setSelected] = useState(new Set<string>());
  return <DataTable virtualize data={rows} originalData={originals} selectedIds={selected} onSelectionChange={setSelected}
    columns={[...largeColumns]}
    onCellChange={(id, key, value) => setRows(previous => previous.map(row => row.id === id ? { ...row, [key]: value } : row))} />;
}

test('5,000-row grid bounds DOM work while select-all still includes every record', () => {
  const { container } = render(<LargeGrid />);
  expect(container.querySelectorAll('tbody tr[data-row-index]').length).toBeLessThan(60);
  expect(screen.queryByText('Material 4999')).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('checkbox')[0]);
  expect(screen.getByText('5000 rows selected')).toBeInTheDocument();
  const scroller = container.querySelector('table')!.parentElement!;
  fireEvent.scroll(scroller, { target: { scrollTop: 139000 } });
  expect(container.querySelectorAll('tbody tr[data-row-index]').length).toBeLessThan(60);
  expect(screen.getByLabelText('Select row 4960')).toBeChecked();
});

test('virtual scrolling keeps row coordinates, edits and undo intact', () => {
  const { container } = render(<LargeGrid />);
  const scroller = container.querySelector('table')!.parentElement!;
  fireEvent.scroll(scroller, { target: { scrollTop: 14000 } });
  const target = container.querySelector('[data-row-index="500"] [data-column-key="quantity"]')!;
  fireEvent.doubleClick(target);
  const editor = screen.getByRole('textbox', { name: 'Edit Quantity' });
  fireEvent.change(editor, { target: { value: '0.1234' } });
  fireEvent.keyDown(editor, { key: 'Enter' });
  expect(screen.getByRole('cell', { name: '0.1234' })).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: 'z', ctrlKey: true });
  expect(container.querySelector('[data-row-index="500"] [data-column-key="quantity"]')).toHaveTextContent('500');
});

test('keyboard navigation moves focus beyond the initially rendered window', () => {
  const { container } = render(<LargeGrid />);
  const renderedRows = container.querySelectorAll<HTMLElement>('tbody tr[data-row-index]');
  const lastRow = renderedRows[renderedRows.length - 1];
  const nextIndex = Number(lastRow.dataset.rowIndex) + 1;
  const target = lastRow.querySelector('[data-column-key="quantity"]') as HTMLElement;
  fireEvent.click(target); target.focus();
  expect(container.querySelector(`[data-row-index="${nextIndex}"]`)).not.toBeInTheDocument();
  fireEvent.keyDown(target, { key: 'ArrowDown' });
  expect(document.activeElement!.closest('tr')).toHaveAttribute('data-row-index', String(nextIndex));
});

for (const module of ['statement', 'management'] as const) {
  test(`${module} search waits for settled text instead of refetching on every key`, async () => {
    const get = vi.spyOn(apiClient, 'get').mockImplementation(async () => ({ metadata: {}, summary: {}, records: [] }) as never);
    const user = { id: 'user', username: 'operator', roles: [], permissions: [], inventory_read: true };
    render(<AuthContext.Provider value={{ user, login: vi.fn(), logout: vi.fn() }}>{module === 'statement' ? <Statement /> : <Management />}</AuthContext.Provider>);
    await waitFor(() => expect(get).toHaveBeenCalledOnce());
    const search = screen.getByPlaceholderText(module === 'statement' ? 'Search items...' : 'Search items or category...');
    fireEvent.change(search, { target: { value: 'G' } });
    fireEvent.change(search, { target: { value: 'Gas' } });
    expect(get).toHaveBeenCalledOnce();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(get.mock.calls[1][0]).toContain('search=Gas');
  });
}
