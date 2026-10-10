import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import Requirements from '../features/requirements/Requirements';

const fetchMock = vi.fn<typeof fetch>();

const mockRequirements = [
  {
    id: 'req-1',
    planning_version_id: 'plan-1',
    part_name: 'Excavator Bucket Arm',
    part_number: 'P-10023',
    consumable_code: 'WLD-WIRE-01',
    consumable_name: 'MIG Welding Wire 1.2mm',
    process_name: 'Welding',
    part_thickness: '12.5',
    process_count: 2,
    production_order_qty: '500.0000',
    scheduled_consumable_qty: '250.0000',
    description: 'MIG Welding Wire 1.2mm',
    plant: 'Plant 1',
    process: 'Welding',
    unit: 'Kg',
    required_qty: '250.0000',
    stock_qty: '50.0000',
    shortage_qty: '200.0000',
    po_pending_qty: '100.0000',
    status: 'Critical shortage',
    remarks: 'Immediate replenishment needed',
    msl: '100.0000',
  },
  {
    id: 'req-2',
    planning_version_id: 'plan-1',
    part_name: 'Chassis Frame Base',
    part_number: 'P-10088',
    consumable_code: 'PNT-THIN-01',
    consumable_name: 'Industrial Thinner',
    process_name: 'Painting',
    part_thickness: '8.0',
    process_count: 1,
    production_order_qty: '300.0000',
    scheduled_consumable_qty: '80.0000',
    description: 'Industrial Thinner',
    plant: 'Plant 1',
    process: 'Painting',
    unit: 'Ltr',
    required_qty: '80.0000',
    stock_qty: '90.0000',
    shortage_qty: '0.0000',
    po_pending_qty: '0.0000',
    status: 'Normal',
    remarks: 'Sufficient stock',
    msl: '50.0000',
  },
];

const mockMetadata = {
  has_plan: true,
  planning_version_id: 'plan-1',
  planning_month: 10,
  planning_year: 2026,
  planning_period: '2026-10',
  created_at: '2026-10-06T08:30:00Z',
  created_by: 'planner',
  last_modified_at: '2026-10-06T09:15:00Z',
  last_modified_by: 'planner',
  source_filename: 'October_Plan.xlsx',
  record_count: 2,
};

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function renderRequirements() {
  return render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'test-user',
          username: 'planner',
          roles: ['PLANNER'],
          permissions: ['requirements.read', 'requirements.calculate'],
        },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Requirements />
    </AuthContext.Provider>
  );
}

test('renders Requirements table with Section 7A headers, metadata card, and records', async () => {
  fetchMock.mockImplementation(async input => {
    const urlStr = String(input);
    if (urlStr.includes('/plan-metadata')) {
      return jsonResponse(mockMetadata);
    }
    if (urlStr.includes('/records')) {
      return jsonResponse(mockRequirements);
    }
    return jsonResponse([]);
  });

  renderRequirements();

  expect(await screen.findByText('Consumable Planning Module')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Recalculate/ })).toBeInTheDocument();
  expect(screen.getByText('Export Excel ▾')).toBeInTheDocument();

  // Period selector
  expect(screen.getByLabelText('Planning Month')).toBeInTheDocument();
  expect(screen.getByLabelText('Planning Year')).toBeInTheDocument();

  // Records rendered
  expect(await screen.findByText('MIG Welding Wire 1.2mm')).toBeInTheDocument();
  expect(screen.getByText('CRITICAL SHORTAGE')).toBeInTheDocument();

  expect(screen.getByText('Industrial Thinner')).toBeInTheDocument();
  expect(screen.getByText('NORMAL')).toBeInTheDocument();

  // Identifying columns rendered
  expect(screen.getByText('Excavator Bucket Arm')).toBeInTheDocument();
  expect(screen.getByText('P-10023')).toBeInTheDocument();
});

test('user can trigger recalculation', async () => {
  fetchMock.mockImplementation(async (url, init) => {
    const urlStr = String(url);
    if (init?.method === 'POST' && urlStr.includes('/recalculate')) {
      return jsonResponse({
        message: 'Recalculation completed using approved deterministic KNL consumption rules.',
        record_count: 2,
        critical_shortages: 1,
        low_stock: 0,
        records: mockRequirements,
        plan_metadata: mockMetadata,
      });
    }
    if (urlStr.includes('/plan-metadata')) {
      return jsonResponse(mockMetadata);
    }
    return jsonResponse(mockRequirements);
  });

  renderRequirements();
  await screen.findByText('MIG Welding Wire 1.2mm');

  const recalcBtn = screen.getByRole('button', { name: /Recalculate/ });
  await userEvent.click(recalcBtn);

  expect(await screen.findByText(/Recalculation completed/)).toBeInTheDocument();
  const call = fetchMock.mock.calls.find(([url, init]) => String(url).includes('/recalculate') && init?.method === 'POST');
  expect(call).toBeDefined();
});
