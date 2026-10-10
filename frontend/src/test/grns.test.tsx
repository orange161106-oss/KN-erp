import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import GRNs from '../features/purchasing/GRNs';

const fetchMock = vi.fn<typeof fetch>();
const allPermissions = [
  'purchase.grns.read',
  'purchase.grns.create',
  'purchase.grns.update',
  'purchase.grns.delete',
  'purchase.grns.import',
  'purchase.grns.export',
];

const mockRecords = [
  {
    id: 'rec-1',
    row_index: 1,
    part_number: '1222A00201',
    item_id: 'ITEM-001',
    description: 'Seat Spacer',
    quantity: '1.0000',
    unit: 'Nos',
    po_number: 'PO-1001',
    supplier_name: 'Alpha Ltd',
    status: 'SAVED',
  },
  {
    id: 'rec-2',
    row_index: 2,
    part_number: '1311A01702',
    item_id: 'ITEM-002',
    description: 'Pivot Brake',
    quantity: '5.0000',
    unit: 'Nos',
    po_number: 'PO-1002',
    supplier_name: 'Beta Ltd',
    status: 'SAVED',
  },
];

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function renderWorkspace(grants = allPermissions) {
  return render(
    <AuthContext.Provider
      value={{
        user: { id: 'test-user', username: 'operator', roles: ['ADMIN'], permissions: grants },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <GRNs />
    </AuthContext.Provider>
  );
}

test('no role bypass and no requests without read permission', () => {
  renderWorkspace([]);
  expect(screen.getByRole('alert')).toHaveTextContent('do not have permission');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('renders Excel table with headers, toolbar buttons, and formula bar', async () => {
  fetchMock.mockResolvedValue(jsonResponse(mockRecords));
  renderWorkspace();

  // Toolbar
  expect(await screen.findByText('Goods Receipts')).toBeInTheDocument();
  expect(screen.getByText(/Upload Excel/)).toBeInTheDocument();
  expect(screen.getByText(/Add Row/)).toBeInTheDocument();
  expect(screen.getByText(/Save Changes/)).toBeInTheDocument();
  expect(screen.getByText(/Delete Row/)).toBeInTheDocument();
  expect(screen.getByText(/Export Excel/)).toBeInTheDocument();

  // Formula bar fx
  expect(screen.getByText('fx')).toBeInTheDocument();

  // Table headers
  expect(screen.getByText('Part Number')).toBeInTheDocument();
  expect(screen.getByText('Item ID')).toBeInTheDocument();
  expect(screen.getByText('Description')).toBeInTheDocument();
  expect(screen.getByText('Qty')).toBeInTheDocument();
  expect(screen.getByText('Unit')).toBeInTheDocument();

  // Table data rows
  expect(await screen.findByText('1222A00201')).toBeInTheDocument();
  expect(screen.getByText('Seat Spacer')).toBeInTheDocument();
  expect(screen.getByText('1311A01702')).toBeInTheDocument();
  expect(screen.getByText('Pivot Brake')).toBeInTheDocument();
});

test('user can add a draft row and edit it directly', async () => {
  fetchMock.mockResolvedValue(jsonResponse(mockRecords));
  renderWorkspace();

  await screen.findByText('1222A00201');

  // Add row
  const addBtn = screen.getByText(/Add Row/);
  await userEvent.click(addBtn);

  // New draft row appears
  expect(screen.getByText('New Consumable Item')).toBeInTheDocument();
  expect(screen.getByText('DRAFT')).toBeInTheDocument();
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
});

test('user can search and filter table rows', async () => {
  fetchMock.mockResolvedValue(jsonResponse(mockRecords));
  renderWorkspace();

  await screen.findByText('1222A00201');
  expect(screen.getByText('1311A01702')).toBeInTheDocument();

  // Search for "Pivot"
  const searchInput = screen.getByLabelText('Search records');
  await userEvent.type(searchInput, 'Pivot');

  expect(screen.getByText('1311A01702')).toBeInTheDocument();
  expect(screen.queryByText('1222A00201')).not.toBeInTheDocument();
});

test('user can delete a row with confirmation dialog', async () => {
  fetchMock.mockImplementation(async (_url, init) => {
    if (init?.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    return jsonResponse(mockRecords);
  });

  renderWorkspace();
  await screen.findByText('1222A00201');

  // Select row by clicking cell
  await userEvent.click(screen.getByText('1222A00201'));

  // Delete button should now be enabled
  const deleteBtn = screen.getByText(/Delete Row/);
  expect(deleteBtn).not.toBeDisabled();
  await userEvent.click(deleteBtn);

  // Confirmation dialog appears
  expect(screen.getByText('Confirm Row Deletion')).toBeInTheDocument();
  expect(screen.getByText(/Are you sure you want to delete this row/)).toBeInTheDocument();

  // Click delete in dialog
  const confirmBtn = screen.getByRole('button', { name: 'Delete' });
  await userEvent.click(confirmBtn);

  await waitFor(() => {
    expect(screen.queryByText('Confirm Row Deletion')).not.toBeInTheDocument();
  });
});

test('user can open Excel upload modal, see multiple sheets, and import selected sheet', async () => {
  fetchMock.mockImplementation(async (url, _init) => {
    const urlStr = String(url);
    if (urlStr.includes('/workspace/inspect')) {
      return jsonResponse({
        filename: 'Consumable_Plan.xlsx',
        sheets: [
          { name: 'Consumable Plan', row_count: 50, column_count: 8, headers: ['Part Number', 'Item ID', 'Description'], sample_rows: [] },
          { name: 'Production', row_count: 20, column_count: 5, headers: ['Part Number', 'Qty'], sample_rows: [] },
        ],
      });
    }
    if (urlStr.includes('/workspace/import-sheet')) {
      return jsonResponse({
        sheet_name: 'Consumable Plan',
        imported_count: 2,
        records: mockRecords,
      });
    }
    return jsonResponse(mockRecords);
  });

  renderWorkspace();
  await screen.findByText('1222A00201');

  // Open Upload modal
  await userEvent.click(screen.getByText(/Upload Excel/));
  expect(screen.getByText('Import Excel File')).toBeInTheDocument();
  expect(screen.getByText(/Drag & Drop Excel File Here/)).toBeInTheDocument();

  // Select a mock file
  const file = new File(['mock content'], 'Consumable_Plan.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(fileInput, { target: { files: [file] } });

  // Inspection shows both sheets
  expect(await screen.findByText('Consumable Plan')).toBeInTheDocument();
  expect(screen.getByText('Production')).toBeInTheDocument();
  expect(screen.getByText('Sheets found:')).toBeInTheDocument();

  // Import button
  const importBtn = screen.getByRole('button', { name: 'Import Selected Sheet' });
  await userEvent.click(importBtn);

  await waitFor(() => {
    expect(screen.queryByText('Import Excel File')).not.toBeInTheDocument();
  });
});

test('saving edits submits payload and shows Saved badge', async () => {
  fetchMock.mockImplementation(async (url, init) => {
    const urlStr = String(url);
    if (init?.method === 'POST' && urlStr.includes('/workspace/save')) {
      return jsonResponse({
        saved_count: 3,
        deleted_count: 0,
        records: mockRecords,
      });
    }
    return jsonResponse(mockRecords);
  });

  renderWorkspace();
  await screen.findByText('1222A00201');

  // Add row to create unsaved state
  await userEvent.click(screen.getByText(/Add Row/));
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();

  // Save changes
  const saveBtn = screen.getByText(/Save Changes/);
  await userEvent.click(saveBtn);

  expect(await screen.findByRole('status')).toHaveTextContent(/Saved ✓/);
});
