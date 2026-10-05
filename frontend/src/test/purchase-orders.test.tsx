import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../features/auth/context';
import PurchaseOrders from '../features/purchasing/PurchaseOrders';

const permissions = ['purchase.orders.read', 'purchase.orders.create', 'purchase.orders.issue', 'purchase.orders.cancel'];
const fetchMock = vi.fn<typeof fetch>();
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const demand = { approval_id: 'approval-1', supplier_id: 'supplier-1', supplier_name: 'Supplier A', consumable_code: 'C1',
  consumable_name: 'Synthetic consumable', unit_code: 'KG', approved_quantity: '60.0000', remaining_quantity: '60.0000', eligible: true, limitation: null };
const order = { id: 'po-1', po_number: 'PO-TEST', supplier_name: 'Supplier A', po_date: '2020-01-02', status: 'DRAFT',
  total_value: null, currency: null, pending_basis: 'NOT_COMMITTED', items: [], history: [] };
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());
function show(grants = permissions) {
  return render(<AuthContext.Provider value={{ user: { id: 'user', username: 'operator', roles: ['ADMIN'], permissions: grants }, login: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter><PurchaseOrders /></MemoryRouter></AuthContext.Provider>);
}
function source(demands: unknown[] = [demand], orders: unknown[] = [], post?: (body: unknown) => Response) {
  fetchMock.mockImplementation(async (input, init) => {
    if (init?.method === 'POST') return post ? post(JSON.parse(String(init.body))) : response(order, 201);
    if (String(input).includes('/eligible')) return response(demands);
    if (String(input).endsWith('/po-1')) return response(orders[0] ?? order);
    return response(orders);
  });
}

test('no role-name bypass and no requests without read grant', () => {
  show([]);
  expect(screen.getByRole('alert')).toHaveTextContent('do not have permission');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('read-only operator sees empty state without creation action', async () => {
  source([], []); show(['purchase.orders.read']);
  expect(await screen.findByText('No purchase orders on this page.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'New purchase order' })).not.toBeInTheDocument();
});

test('legacy approvals explain missing evidence and cannot be selected', async () => {
  source([{ ...demand, eligible: false, remaining_quantity: null, limitation: 'Resubmit through traced demand.' }]); show();
  await userEvent.click(screen.getByRole('button', { name: 'New purchase order' }));
  expect(await screen.findByText('Resubmit through traced demand.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add C1' })).toBeDisabled();
});

test('draft preserves decimal strings and retries unchanged creation key', async () => {
  const bodies: Record<string, unknown>[] = [];
  source([demand], [], body => {
    bodies.push(body as Record<string, unknown>);
    return bodies.length === 1 ? response({ message: 'Retry this request.', code: 'PO_RETRY_REQUIRED' }, 409) : response(order, 201);
  }); show();
  await userEvent.click(screen.getByRole('button', { name: 'New purchase order' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Add C1' }));
  fireEvent.change(screen.getByLabelText('PO date'), { target: { value: '2020-01-02' } });
  fireEvent.change(screen.getByLabelText('Creation reason'), { target: { value: 'Approved demand' } });
  fireEvent.change(screen.getByLabelText('Ordered quantity 1'), { target: { value: '1.0001' } });
  fireEvent.change(screen.getByLabelText('Expected delivery 1'), { target: { value: '2020-01-07T12:00' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Retry this request.');
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(await screen.findByText('Purchase order draft saved. Stock is unchanged.')).toBeInTheDocument();
  expect(bodies[0].creation_key).toBe(bodies[1].creation_key);
  expect((bodies[0].items as { ordered_quantity: string }[])[0].ordered_quantity).toBe('1.0001');
});

test('issued PO explains imported fulfilment and offers no unsafe cancellation', async () => {
  source([], [{ ...order, status: 'ISSUED', pending_basis: 'IMPORTED_ACCEPTED_GRNS' }]); show();
  await userEvent.click(await screen.findByRole('button', { name: 'View PO-TEST' }));
  expect(await screen.findByText(/Pending quantity uses imported accepted usable GRNs/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Cancel draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Issue PO' })).not.toBeInTheDocument();
});

test('loading and network errors remain visible', async () => {
  let reject: (reason: Error) => void = () => {};
  fetchMock.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
  show(); expect(screen.getByText('Loading purchase orders…')).toBeInTheDocument();
  reject(new Error('Offline'));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the server'));
});

test('issuing a draft requires a reason and displays the returned commitment state', async () => {
  source([], [order], body => {
    expect(body).toEqual({ reason: 'Approved supplier commitment' });
    return response({ ...order, status: 'ISSUED', pending_basis: 'IMPORTED_ACCEPTED_GRNS' });
  }); show();
  await userEvent.click(await screen.findByRole('button', { name: 'View PO-TEST' }));
  expect(await screen.findByRole('button', { name: 'Issue PO' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Action reason'), { target: { value: 'Approved supplier commitment' } });
  await userEvent.click(screen.getByRole('button', { name: 'Issue PO' }));
  expect(await screen.findByText('PO issued as a commitment. Stock is unchanged.')).toBeInTheDocument();
  expect(screen.getByText(/Pending quantity uses imported accepted usable GRNs/)).toBeInTheDocument();
});
