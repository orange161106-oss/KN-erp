import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { AuthContext } from '../features/auth/context';
import StockManagementWorkspace from '../features/inventory/StockManagementWorkspace';

const now = new Date();
const month = now.getMonth() + 1;
const year = now.getFullYear();
const operator = { id: 'operator', username: 'store', roles: [], permissions: [], inventory_read: true,
  inventory_create: true, inventory_delete: true, is_super_admin: false };
let deleted = false;

function statement(periodMonth = month, periodYear = year, empty = false) {
  return {
    metadata: { has_parameters: !empty, batch_id: empty ? null : `batch-${periodMonth}-${periodYear}`,
      month: periodMonth, year: periodYear, row_count: empty ? 0 : 1755,
      source_filename: 'synthetic-stock.xlsx' },
    summary: { item_count: empty ? 0 : 1755, missing_limits_count: 0, min_exceeds_max_count: 0 },
    records: empty ? [] : [{ id: 'line-1', item_id: 'TEST-MAT-1', description: 'Synthetic material', min_stock_level: '10', max_stock_level: '20', min_order_qty: '5', lead_time_days: 2 }],
  };
}

function renderPage(user = operator) {
  return render(<AuthContext.Provider value={{ user, login: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter><StockManagementWorkspace /></MemoryRouter>
  </AuthContext.Provider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  deleted = false;
  vi.spyOn(apiClient, 'get').mockImplementation(async endpoint => {
    const params = new URL(endpoint, 'http://localhost').searchParams;
    const requestedMonth = Number(params.get('month'));
    const requestedYear = Number(params.get('year'));
    return statement(requestedMonth, requestedYear, deleted && requestedMonth === month && requestedYear === year) as never;
  });
});

async function openDelete() {
  const user = userEvent.setup();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Delete parameters' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Delete parameters' }));
  return { user, dialog: screen.getByRole('dialog') };
}

test('deletes only the captured month and year after reason and confirmation, including filtered rows', async () => {
  const remove = vi.spyOn(apiClient, 'delete').mockImplementation(async () => { deleted = true; return {} as never; });
  renderPage();
  const { user, dialog } = await openDelete();
  const confirm = within(dialog).getByRole('button', { name: 'Delete parameters' });
  expect(confirm).toBeDisabled();
  expect(within(dialog).getByText(/1755 rows in the complete parameter batch/)).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Parameters month' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Parameters year' })).toBeDisabled();
  await user.type(screen.getByLabelText('Reason for deletion'), ' Wrong period ');
  await user.click(confirm);
  expect(remove).toHaveBeenCalledExactlyOnceWith(`/api/v1/inventory/management?month=${month}&year=${year}`, {
    batch_id: `batch-${month}-${year}`, reason: 'Wrong period',
  });
  expect(await screen.findByText(/Deleted the .* stock parameters\./)).toBeInTheDocument();
  expect(screen.queryByText('TEST-MAT-1')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Delete parameters' })).toBeDisabled();

  const otherYear = year === 2026 ? 2025 : 2026;
  await user.selectOptions(screen.getByRole('combobox', { name: 'Parameters year' }), String(otherYear));
  expect(await screen.findByText('TEST-MAT-1')).toBeInTheDocument();
  expect(remove).toHaveBeenCalledTimes(1);
});

test('cancel leaves the uploaded statement intact', async () => {
  const remove = vi.spyOn(apiClient, 'delete').mockResolvedValue({});
  renderPage();
  const { user, dialog } = await openDelete();
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
  expect(remove).not.toHaveBeenCalled();
  expect(screen.getByText('TEST-MAT-1')).toBeInTheDocument();
});

test('read and upload permissions alone do not display delete', async () => {
  renderPage({ ...operator, inventory_delete: false });
  expect(await screen.findByText('TEST-MAT-1')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Delete parameters' })).not.toBeInTheDocument();
});

test('stale upload errors retain the parameters and show the server message', async () => {
  vi.spyOn(apiClient, 'delete').mockRejectedValue(new ApiError(409, 'PARAMETERS_CHANGED', 'These parameters have been replaced. Refresh first.'));
  renderPage();
  const { user, dialog } = await openDelete();
  await user.type(screen.getByLabelText('Reason for deletion'), 'Wrong upload');
  await user.click(within(dialog).getByRole('button', { name: 'Delete parameters' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('These parameters have been replaced.');
  expect(screen.getByText('TEST-MAT-1')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});


test('empty periods cannot be deleted', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue(statement(month, year, true));
  renderPage();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload parameters' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Delete parameters' })).toBeDisabled();
});

test('a response for another period cannot authorize deletion', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue(statement(month === 12 ? 1 : month + 1, year));
  renderPage();
  expect(await screen.findByText('TEST-MAT-1')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Delete parameters' })).toBeDisabled();
});
