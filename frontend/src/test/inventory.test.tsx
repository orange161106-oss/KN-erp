import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../features/auth/context';
import type { CurrentUser } from '../features/auth/context';
import Inventory from '../features/inventory/Inventory';
import Sidebar from '../components/Sidebar';
import type { Balance, StockTransaction } from '../features/inventory/types';

const identity: CurrentUser = { id: 'user-1', username: 'operator', roles: ['ADMIN'], permissions: ['inventory.stock.read'] };
const balance: Balance = { consumable_id: 'material-1', code: 'C1', name: 'Synthetic material', is_active: true, unit_id: 'kg', unit_code: 'KG',
  usable_quantity: '100.1234', as_of: '2020-01-02T12:00:00Z', imported_at: '2020-01-03T12:00:00Z', source_export_id: 'source-export', availability: 'REPORTED', is_live: false };
const entry: StockTransaction = { id: 'entry-1', source_event_id: 'event-1', consumable_id: 'material-1', code: 'C1', name: 'Synthetic material',
  unit_id: 'kg', unit_code: 'KG', source_unit_id: 'kg', source_unit_code: 'KG', source_quantity: '2.0001', conversion_factor: '1', conversion_reference: null,
  movement: 'ISSUE', quantity: '2.0001', signed_quantity: '-2.0001', event_at: '2020-01-01T12:00:00Z', source_actor: 'source operator',
  imported_at: '2020-01-03T12:00:00Z', imported_by: 'user-1', source_export_id: 'source-export' };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 25, offset: 0 });
const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => vi.stubGlobal('fetch', fetchMock));
afterEach(() => vi.unstubAllGlobals());
function show(user = identity) {
  return render(<AuthContext.Provider value={{ user, login: vi.fn(), logout: vi.fn() }}><MemoryRouter><Sidebar /><Inventory /></MemoryRouter></AuthContext.Provider>);
}
function source(enabled = false, balances = [balance], transactions = [entry], post?: () => Response) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === 'POST') return post ? post() : response({ code: 'SOURCE_CONFLICT', message: 'Source content conflicts with stored history.' }, 409);
    if (url.includes('/status')) return response({ source: 'EXISTING_ERP', mode: 'READ_ONLY_REPLICA', is_live: false, import_enabled: enabled, warehouse_posting: false, msl_alert_policy: 'TBD' });
    if (url.includes('/balances')) return response(page(balances));
    return response(page(transactions));
  });
}

test('ADMIN without explicit inventory permission cannot navigate or request data', () => {
  show({ ...identity, permissions: [] });
  expect(screen.getByRole('alert')).toHaveTextContent('do not have permission');
  expect(screen.queryByRole('link', { name: 'Inventory' })).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('reported stock retains four decimals and clearly identifies the external dated source', async () => {
  source(); show();
  expect(await screen.findByText('100.1234')).toBeInTheDocument();
  expect(screen.getByText(/Balances are dated reports/)).toBeInTheDocument();
  expect(screen.getByText(/opening stock, reservations, approvals and corrections stay there/i)).toBeInTheDocument();
  expect(screen.getByText('KNL Consumable ERP')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /issue stock|adjust stock|opening stock/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Import source records' })).not.toBeInTheDocument();
});

test('missing balance is unavailable rather than a fabricated zero', async () => {
  source(false, [{ ...balance, usable_quantity: null, availability: 'NOT_IMPORTED', as_of: null }]); show();
  expect(await screen.findByText('Not imported')).toBeInTheDocument();
  expect(screen.queryByText('0.0000')).not.toBeInTheDocument();
});

test('history displays issue direction and original source actor without consumption claims', async () => {
  source(); show(); const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'View history for C1' }));
  expect(await screen.findByText('-2.0001 KG')).toBeInTheDocument();
  expect(screen.getByRole('cell', { name: 'Plant issue' })).toBeInTheDocument();
  expect(screen.getByText('source operator')).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('consumable_id=material-1'))).toBe(true);
  await user.selectOptions(screen.getByLabelText('Movement'), 'RETURN');
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('movement=RETURN'))).toBe(true));
});

test('source unit conversion is visible while stock quantities stay exact strings', async () => {
  source(false, [balance], [{ ...entry, movement: 'RECEIPT', signed_quantity: '50.2500', source_quantity: '2.0000', source_unit_code: 'BOX', conversion_factor: '25.125', conversion_reference: 'approved-source-factor' }]);
  show(); await userEvent.setup().click(screen.getByRole('button', { name: 'Stock history' }));
  expect(await screen.findByText('+50.2500 KG')).toBeInTheDocument();
  expect(screen.getByText('2.0000 BOX')).toBeInTheDocument();
  expect(screen.getByText('Conversion: ×25.125')).toBeInTheDocument();
});

test('imports remain unavailable even to a granted importer until explicitly enabled', async () => {
  source(); show({ ...identity, permissions: [...identity.permissions, 'inventory.stock.import'] });
  expect(await screen.findByText(/Source imports are disabled/)).toBeInTheDocument();
  expect(screen.queryByLabelText('Stock export data')).not.toBeInTheDocument();
});

test('source import reports replay accurately and refreshes data', async () => {
  source(true, [balance], [], () => response({ id: 'batch-1', export_id: 'source-1', movement_count: 1, snapshot_count: 1, replayed: true }, 200));
  show({ ...identity, permissions: [...identity.permissions, 'inventory.stock.import'] });
  const textarea = await screen.findByLabelText('Stock export data');
  fireEvent.change(textarea, { target: { value: '{"export_id":"source-1"}' } });
  await userEvent.setup().click(screen.getByRole('button', { name: 'Import source records' }));
  expect(await screen.findByText(/No duplicate records were added/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

test('malformed export does not submit, and conflicting source data remains visible', async () => {
  source(true); show({ ...identity, permissions: [...identity.permissions, 'inventory.stock.import'] });
  const textarea = await screen.findByLabelText('Stock export data');
  fireEvent.change(textarea, { target: { value: 'invalid' } });
  await userEvent.setup().click(screen.getByRole('button', { name: 'Import source records' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('valid JSON');
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  fireEvent.change(textarea, { target: { value: '{}' } });
  await userEvent.setup().click(screen.getByRole('button', { name: 'Import source records' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('conflicts with stored history');
  expect(textarea).toHaveValue('{}');
});

test('API errors are shown and stock search uses server filtering', async () => {
  fetchMock.mockResolvedValue(response({ message: 'Database is unavailable.', code: 'DATABASE_UNAVAILABLE' }, 503));
  show(); expect((await screen.findAllByRole('alert'))[0]).toHaveTextContent('Database is unavailable.');
  fireEvent.change(screen.getByLabelText('Search code or name'), { target: { value: 'needle' } });
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('q=needle'))).toBe(true));
});
