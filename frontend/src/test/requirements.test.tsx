import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import Requirements from '../features/requirements/Requirements';

const fetchMock = vi.fn<typeof fetch>();

const mockRequirements = [
  {
    id: 'req-1',
    plant: 'Plant 1',
    process: 'Welding',
    consumable_code: 'WLD-WIRE-01',
    description: 'MIG Welding Wire 1.2mm',
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
    plant: 'Plant 1',
    process: 'Painting',
    consumable_code: 'PNT-THIN-01',
    description: 'Industrial Thinner',
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

test('renders Requirements table with critical shortages and normal status', async () => {
  fetchMock.mockImplementation(async input => String(input).endsWith('/prd/planning-versions')
    ? jsonResponse([{ id: 'version-1', planning_period: '2026-08', revision_label: 'R3', status: 'CALCULATED' }])
    : jsonResponse(mockRequirements));
  renderRequirements();

  expect(await screen.findByText('Consumable Requirements Workspace')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Recalculate/ })).toBeInTheDocument();
  expect(screen.getByText(/Export Excel/)).toBeInTheDocument();

  // Records rendered
  expect(await screen.findByText('MIG Welding Wire 1.2mm')).toBeInTheDocument();
  expect(screen.getByText('CRITICAL SHORTAGE')).toBeInTheDocument();

  expect(screen.getByText('Industrial Thinner')).toBeInTheDocument();
  expect(screen.getByText('NORMAL')).toBeInTheDocument();
});

test('user can trigger recalculation', async () => {
  fetchMock.mockImplementation(async (url, init) => {
    const urlStr = String(url);
    if (init?.method === 'POST' && urlStr.includes('/requirements/calculate')) {
      return jsonResponse({
        message: 'Recalculation complete',
        record_count: 2,
        critical_shortages: 1,
        low_stock: 0,
        records: mockRequirements,
      });
    }
    if (urlStr.includes('/prd/planning-versions')) return jsonResponse([{ id: 'version-1', planning_period: '2026-08', revision_label: 'R3', status: 'VALIDATED' }]);
    return jsonResponse(mockRequirements);
  });

  renderRequirements();
  await screen.findByText('MIG Welding Wire 1.2mm');

  const recalcBtn = screen.getByRole('button', { name: /Recalculate/ });
  await userEvent.click(recalcBtn);

  expect(await screen.findByText(/Calculation completed/)).toBeInTheDocument();
  const call = fetchMock.mock.calls.find(([url, init]) => String(url).includes('/requirements/calculate') && init?.method === 'POST');
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ planning_version_id: 'version-1' });
});
