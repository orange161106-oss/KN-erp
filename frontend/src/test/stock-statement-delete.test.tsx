import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { AuthContext } from '../features/auth/context';
import StockStatementWorkspace from '../features/inventory/StockStatementWorkspace';

const now = new Date();
const month = now.getMonth() === 0 ? 12 : now.getMonth();
const year = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
const operator = { id: 'operator', username: 'store', roles: [], permissions: [], inventory_read: true,
  inventory_create: true, inventory_delete: true, is_super_admin: false };
let deleted = false;

function statement(periodMonth = month, periodYear = year, empty = false) {
  return {
    metadata: { has_statement: !empty, batch_id: empty ? null : `batch-${periodMonth}-${periodYear}`,
      statement_month: periodMonth, statement_year: periodYear, row_count: empty ? 0 : 1755,
      source_filename: 'synthetic-stock.xlsx' },
    summary: { item_count: empty ? 0 : 1755, total_opening_value: '100', total_receipt_value: '0',
      total_issue_value: '0', total_closing_value: '100', warning_rows_count: 0 },
    records: empty ? [] : [{ id: 'line-1', item_id: 'TEST-MAT-1', item_description: 'Synthetic material',
      unit: 'KG', closing_qty: '10', warning_codes: [] }],
  };
}

function renderPage(user = operator) {
  return render(<AuthContext.Provider value={{ user, login: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter><StockStatementWorkspace /></MemoryRouter>
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
  await waitFor(() => expect(screen.getByRole('button', { name: 'Delete statement' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Delete statement' }));
  return { user, dialog: screen.getByRole('dialog') };
}

test('deletes only the captured month and year after reason and confirmation, including filtered rows', async () => {
  const remove = vi.spyOn(apiClient, 'delete').mockImplementation(async () => { deleted = true; return {} as never; });
  renderPage();
  const { user, dialog } = await openDelete();
  const confirm = within(dialog).getByRole('button', { name: 'Delete statement' });
  expect(confirm).toBeDisabled();
  expect(within(dialog).getByText(/1755 rows in the complete statement/)).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Statement month' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Statement year' })).toBeDisabled();
  await user.type(screen.getByLabelText('Reason for deletion'), ' Wrong period ');
  await user.click(confirm);
  expect(remove).toHaveBeenCalledExactlyOnceWith(`/api/v1/inventory/statement?month=${month}&year=${year}`, {
    batch_id: `batch-${month}-${year}`, reason: 'Wrong period',
  });
  expect(await screen.findByText(/Deleted the .* stock statement\./)).toBeInTheDocument();
  expect(screen.queryByText('TEST-MAT-1')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Delete statement' })).toBeDisabled();

  const otherYear = year === 2026 ? 2025 : 2026;
  await user.selectOptions(screen.getByRole('combobox', { name: 'Statement year' }), String(otherYear));
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
  expect(screen.queryByRole('button', { name: 'Delete statement' })).not.toBeInTheDocument();
});

test('stale upload errors retain the statement and show the server message', async () => {
  vi.spyOn(apiClient, 'delete').mockRejectedValue(new ApiError(409, 'STATEMENT_CHANGED', 'This statement has been replaced. Refresh first.'));
  renderPage();
  const { user, dialog } = await openDelete();
  await user.type(screen.getByLabelText('Reason for deletion'), 'Wrong upload');
  await user.click(within(dialog).getByRole('button', { name: 'Delete statement' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This statement has been replaced.');
  expect(screen.getByText('TEST-MAT-1')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});
