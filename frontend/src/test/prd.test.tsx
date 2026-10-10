import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import PRDPlanning from '../features/prd/PRDPlanning';

const fetchMock = vi.fn<typeof fetch>();

const mockPRDRecords = [
  {
    id: 'prd-1',
    row_index: 1,
    plant: 'Plant 1',
    customer: 'Toyota',
    product_code: 'PRD-T01',
    description: 'Chassis Mount Bracket',
    planned_quantity: '500.0000',
    uom: 'Nos',
    target_period: '2026-10',
    planning_version: 'V1',
    status: 'SAVED',
    remarks: 'Regular batch',
  },
  {
    id: 'prd-2',
    row_index: 2,
    plant: 'Plant 2',
    customer: 'Honda',
    product_code: 'PRD-H02',
    description: 'Radiator Side Plate',
    planned_quantity: '300.0000',
    uom: 'Nos',
    target_period: '2026-10',
    planning_version: 'V1',
    status: 'CONFIRMED',
    remarks: 'Priority batch',
  },
];

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function renderPRDWorkspace() {
  return render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'test-user',
          username: 'planner',
          roles: ['PLANNER'],
          permissions: ['prd.plan.read', 'prd.plan.create', 'prd.plan.update', 'prd.plan.delete', 'prd.plan.import'],
        },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <PRDPlanning />
    </AuthContext.Provider>
  );
}

test('renders PRD planning table with toolbar buttons and rows', async () => {
  fetchMock.mockResolvedValue(jsonResponse(mockPRDRecords));
  renderPRDWorkspace();

  expect(await screen.findByText('PRD / Planning Workspace')).toBeInTheDocument();
  expect(screen.getByText(/Upload Excel/)).toBeInTheDocument();
  expect(screen.getByText(/Add Row/)).toBeInTheDocument();
  expect(screen.getByText(/Save Changes/)).toBeInTheDocument();
  expect(screen.getByText(/Delete/)).toBeInTheDocument();
  expect(screen.getByText(/Export Excel/)).toBeInTheDocument();

  expect(await screen.findByText('PRD-T01')).toBeInTheDocument();
  expect(screen.getByText('Chassis Mount Bracket')).toBeInTheDocument();
  expect(screen.getByText('PRD-H02')).toBeInTheDocument();
});

test('user can add a draft row and trigger save', async () => {
  fetchMock.mockImplementation(async (url, init) => {
    const urlStr = String(url);
    if (init?.method === 'POST' && urlStr.includes('/workspace/save')) {
      return jsonResponse({
        saved_count: 3,
        deleted_count: 0,
        records: mockPRDRecords,
      });
    }
    return jsonResponse(mockPRDRecords);
  });

  renderPRDWorkspace();
  await screen.findByText('PRD-T01');

  // Click Add Row
  await userEvent.click(screen.getByText(/Add Row/));
  expect(screen.getByText('New Planned Product')).toBeInTheDocument();
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();

  // Save changes
  await userEvent.click(screen.getByText(/Save Changes/));
  expect(await screen.findByText(/Saved 3 records successfully/)).toBeInTheDocument();
});

test('user can select a row and delete with confirmation dialog', async () => {
  fetchMock.mockImplementation(async (url, init) => {
    const urlStr = String(url);
    if (init?.method === 'POST' && urlStr.includes('/workspace/bulk-delete')) {
      return jsonResponse({ deleted_count: 1 });
    }
    return jsonResponse(mockPRDRecords);
  });

  renderPRDWorkspace();
  await screen.findByText('PRD-T01');

  // Select row
  await userEvent.click(screen.getByText('PRD-T01'));

  // Click delete
  const deleteBtn = screen.getByText(/Delete/);
  await userEvent.click(deleteBtn);

  // Dialog appears
  expect(screen.getByText('Confirm Row Deletion')).toBeInTheDocument();
  const confirmBtn = screen.getByRole('button', { name: 'Delete' });
  await userEvent.click(confirmBtn);

  await waitFor(() => {
    expect(screen.queryByText('Confirm Row Deletion')).not.toBeInTheDocument();
  });
});
