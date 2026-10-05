import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import GRNs from '../features/purchasing/GRNs';

const fetchMock = vi.fn<typeof fetch>();
const permissions = ['purchase.grns.read', 'purchase.grns.import', 'inventory.stock.import'];
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const source = { source_grn_id: 'ERP-GRN-1', purchase_order_id: 'po-1', event_at: '2020-01-08T12:00:00Z',
  items: [{ source_line_id: '1', received_quantity: '1.0001', accepted_quantity: '1.0000', rejected_quantity: '0.0001' }] };
const receipt = { ...source, id: 'grn-1', source_actor: 'ERP operator', reason: 'Source import', imported_at: '2020-01-09T12:00:00Z',
  items: [{ ...source.items[0], id: 'item-1', stock_transaction_id: 'stock-1', stock_snapshot_id: 'snapshot-1' }], replayed: false };
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());
function show(grants = permissions) {
  return render(<AuthContext.Provider value={{ user: { id: 'user', username: 'operator', roles: ['ADMIN'], permissions: grants }, login: vi.fn(), logout: vi.fn() }}><GRNs /></AuthContext.Provider>);
}
function upload(value: unknown) {
  const file = new File([JSON.stringify(value)], 'receipt.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => JSON.stringify(value) });
  fireEvent.change(screen.getByLabelText('Posted ERP receipt export'), { target: { files: [file] } });
}

test('no role bypass and no requests without read permission', () => {
  show([]); expect(screen.getByRole('alert')).toHaveTextContent('do not have permission');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('read only sees empty state and no import control', async () => {
  fetchMock.mockResolvedValue(response([])); show(['purchase.grns.read']);
  expect(await screen.findByText('No imported receipts on this page.')).toBeInTheDocument();
  expect(screen.queryByLabelText('Posted ERP receipt export')).not.toBeInTheDocument();
});

test('both import permissions are required to show the import control', async () => {
  fetchMock.mockResolvedValue(response([])); show(['purchase.grns.read', 'purchase.grns.import']);
  await screen.findByText('No imported receipts on this page.');
  expect(screen.queryByLabelText('Posted ERP receipt export')).not.toBeInTheDocument();
});

test('preview preserves decimal text and retry sends identical source', async () => {
  const bodies: unknown[] = [];
  fetchMock.mockImplementation(async (_input, init) => {
    if (init?.method === 'POST') {
      bodies.push(JSON.parse(String(init.body)));
      return bodies.length === 1 ? response({ code: 'GRN_RETRY_REQUIRED', message: 'Retry unchanged.' }, 409) : response({ ...receipt, replayed: true });
    }
    return response([]);
  });
  show(); await screen.findByText('No imported receipts on this page.'); upload(source);
  expect(await screen.findByText(/Received 1.0001 · Accepted 1.0000 · Rejected 0.0001/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Import posted receipt' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Retry unchanged');
  await userEvent.click(screen.getByRole('button', { name: 'Import posted receipt' }));
  expect(await screen.findByText('This receipt was already imported. No quantities were added again.')).toBeInTheDocument();
  expect(bodies).toEqual([source, source]);
  expect(screen.getByText('Stock receipt reference: stock-1')).toBeInTheDocument();
});

test('invalid numeric quantity cannot reach import submission', async () => {
  fetchMock.mockResolvedValue(response([])); show(); await screen.findByText('No imported receipts on this page.');
  upload({ ...source, items: [{ ...source.items[0], accepted_quantity: 1.0 }] });
  expect(await screen.findByRole('alert')).toHaveTextContent('exact decimal text');
  expect(screen.queryByRole('button', { name: 'Import posted receipt' })).not.toBeInTheDocument();
});

test('loading and network failure are visible', async () => {
  let reject: (error: Error) => void = () => {};
  fetchMock.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
  show(); expect(screen.getByText('Loading receipts…')).toBeInTheDocument();
  reject(new Error('Offline'));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the server'));
});
