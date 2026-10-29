import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import Requirements from '../features/requirements/Requirements';

const fetchMock = vi.fn<typeof fetch>();

const mockRequirements = [
  // 1. Production item (Plant 1)
  {
    id: 'req-prod-1',
    planning_period: '2026-10',
    planning_month: 10,
    planning_year: 2026,
    part_name: 'Excavator Bucket Arm',
    part_number: 'P-10023',
    consumable_code: 'WLD-WIRE-01',
    consumable_name: 'MIG Welding Wire 1.2mm',
    process_name: 'Welding',
    part_thickness: '12.5',
    process_count: 2,
    production_order_qty: '500.0000',
    scheduled_consumable_qty: '250.0000',
    plant: 'Plant 1',
    process: 'Welding',
    description: 'MIG Welding Wire 1.2mm',
    unit: 'Kg',
    rule_type: 'PRODUCTION_RATE',
    required_qty: '250.0000',
    stock_qty: '50.0000',
    grn_received_qty: '200.0000',
    shortage_qty: '0.0000',
    po_pending_qty: '0.0000',
    msl: '100.0000',
    status: 'Normal',
    remarks: 'Standard production allocation',
  },
  // 2. Departmental item (Tool Room)
  {
    id: 'req-dept-tr-1',
    planning_period: '2026-10',
    planning_month: 10,
    planning_year: 2026,
    part_name: '',
    part_number: 'DEPARTMENT_INDENT',
    consumable_code: 'TR-TOOL-01',
    consumable_name: 'Carbide End Mill 10mm',
    process_name: 'DEPARTMENT_INDENT',
    part_thickness: '0.0000',
    process_count: 1,
    production_order_qty: '0.0000',
    scheduled_consumable_qty: '12.0000',
    plant: 'Tool Room',
    process: 'DEPARTMENT_INDENT',
    description: 'Carbide End Mill 10mm',
    unit: 'NOS',
    rule_type: 'PLANT_REQUEST',
    required_qty: '12.0000',
    stock_qty: '4.0000',
    grn_received_qty: '10.0000',
    shortage_qty: '0.0000',
    po_pending_qty: '0.0000',
    msl: '5.0000',
    status: 'Normal',
    remarks: 'Monthly CNC cutter indent',
    historical_avg_qty: '10.5000',
    active_month_count: 4,
    doc_ref: 'KNL/TR/DI/01',
  },
  // 3. Departmental item (PMD / Maintenance)
  {
    id: 'req-dept-pmd-1',
    planning_period: '2026-10',
    planning_month: 10,
    planning_year: 2026,
    part_name: '',
    part_number: 'KNL/PMD/DI/33',
    consumable_code: 'PMD-HYD-68',
    consumable_name: 'Hydraulic Oil ISO VG 68',
    process_name: 'MAINTENANCE',
    part_thickness: '0.0000',
    process_count: 1,
    production_order_qty: '0.0000',
    scheduled_consumable_qty: '210.0000',
    plant: 'PMD',
    process: 'MAINTENANCE',
    description: 'Hydraulic Oil ISO VG 68',
    unit: 'LTRS',
    rule_type: 'PLANT_REQUEST',
    required_qty: '210.0000',
    stock_qty: '20.0000',
    grn_received_qty: '0.0000',
    shortage_qty: '190.0000',
    po_pending_qty: '0.0000',
    msl: '50.0000',
    status: 'Critical shortage',
    remarks: 'Press overhaul top-up',
    historical_avg_qty: '185.0000',
    active_month_count: 5,
    doc_ref: 'KNL/PMD/DI/33',
  },
];

const mockPlanMetadata = {
  has_plan: true,
  plan_id: 'plan-10-2026',
  planning_month: 10,
  planning_year: 2026,
  planning_period: '2026-10',
  status: 'DRAFT',
  revision_label: 'R0',
  source_workflow: 'BASIC_CENTRAL_V1',
  source_filename: 'Consumable_Plan_Oct26.xlsx',
  created_at: '2026-10-06T08:30:00Z',
  created_by_name: 'Central Planner',
  updated_at: '2026-10-06T09:15:00Z',
  updated_by_name: 'Central Planner',
  record_count: 3,
  issue_count: 2,
  grn_reconciled: true,
};

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderRequirements() {
  return render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'test-admin-id',
          username: 'admin',
          is_super_admin: true,
          roles: ['ADMIN'],
          permissions: ['requirements.read', 'requirements.calculate', 'requirements.update'],
        },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Requirements />
    </AuthContext.Provider>
  );
}

test('renders top-level tabs and switches cleanly between Production and Departmental views', async () => {
  fetchMock.mockImplementation(async input => {
    const urlStr = String(input);
    if (urlStr.includes('/workspace/view')) {
      return jsonResponse({
        records: mockRequirements,
        plan_metadata: mockPlanMetadata,
      });
    }
    return jsonResponse([]);
  });

  renderRequirements();

  // 1. Verify Top-Level Tabs exist
  const prodTab = await screen.findByRole('button', { name: /Production Consumables \(Plants 1–5\)/i });
  const deptTab = screen.getByRole('button', { name: /Departmental & Maintenance/i });
  expect(prodTab).toBeInTheDocument();
  expect(deptTab).toBeInTheDocument();

  // 2. By default, Production tab is active:
  // Shows manufacturing headers
  expect(await screen.findByText('Used For – Part Name')).toBeInTheDocument();
  expect(screen.getByText('Number of Processes')).toBeInTheDocument();
  expect(screen.getByText('Part Thickness (mm)')).toBeInTheDocument();
  expect(screen.getByText('Production Order for Selected Month')).toBeInTheDocument();

  // Shows production row and norm issue banner
  expect(await screen.findByText('Excavator Bucket Arm')).toBeInTheDocument();
  expect(screen.getByText(/missing norms or unmapped processes/i)).toBeInTheDocument();

  // 3. Switch to Departmental & Maintenance tab
  await userEvent.click(deptTab);

  // 4. Verify manufacturing columns are hidden
  expect(screen.queryByText('Used For – Part Name')).not.toBeInTheDocument();
  expect(screen.queryByText('Number of Processes')).not.toBeInTheDocument();
  expect(screen.queryByText('Part Thickness (mm)')).not.toBeInTheDocument();
  expect(screen.queryByText('Production Order for Selected Month')).not.toBeInTheDocument();

  // 5. Verify dedicated 14 departmental columns are rendered
  expect(screen.getByText('Department')).toBeInTheDocument();
  expect(screen.getByText('Item ID')).toBeInTheDocument();
  expect(screen.getByText('Item Description')).toBeInTheDocument();
  expect(screen.getByText('Part / Doc Ref')).toBeInTheDocument();
  expect(screen.getByText('Historical Avg (Active Mos)')).toBeInTheDocument();
  expect(screen.getByText('Required Qty')).toBeInTheDocument();
  expect(screen.getByText('Stock Qty (T-2)')).toBeInTheDocument();
  expect(screen.getByText('GRN Received')).toBeInTheDocument();
  expect(screen.getByText('Shortage Qty')).toBeInTheDocument();
  expect(screen.getByText('Remarks')).toBeInTheDocument();

  // 6. Verify departmental rows are displayed with historical averages & doc refs
  expect(await screen.findByText('Carbide End Mill 10mm')).toBeInTheDocument();
  expect(screen.getByText('Hydraulic Oil ISO VG 68')).toBeInTheDocument();
  expect(screen.getByText('KNL/PMD/DI/33')).toBeInTheDocument();
  expect(screen.getByText('10.5000')).toBeInTheDocument();
  expect(screen.getByText('4 mo')).toBeInTheDocument();

  // 7. Verify missing norms banner and production notice are suppressed in Departmental tab
  expect(screen.queryByText(/missing norms or unmapped processes/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Production-based requirements calculated deterministically/i)).not.toBeInTheDocument();
});

test('department filter pills filter rows by department in Departmental tab', async () => {
  fetchMock.mockImplementation(async input => {
    const urlStr = String(input);
    if (urlStr.includes('/workspace/view')) {
      return jsonResponse({
        records: mockRequirements,
        plan_metadata: mockPlanMetadata,
      });
    }
    return jsonResponse([]);
  });

  renderRequirements();

  // Switch to Departmental tab
  const deptTab = await screen.findByRole('button', { name: /Departmental & Maintenance/i });
  await userEvent.click(deptTab);

  // Both Tool Room and PMD items initially visible
  expect(await screen.findByText('Carbide End Mill 10mm')).toBeInTheDocument();
  expect(screen.getByText('Hydraulic Oil ISO VG 68')).toBeInTheDocument();

  // Click PMD filter pill
  const pmdPill = screen.getByRole('button', { name: /^PMD/i });
  await userEvent.click(pmdPill);

  // PMD item remains, Tool Room item filtered out
  expect(screen.getByText('Hydraulic Oil ISO VG 68')).toBeInTheDocument();
  expect(screen.queryByText('Carbide End Mill 10mm')).not.toBeInTheDocument();

  // Click All Depts pill to reset filter
  const allDeptsPill = screen.getByRole('button', { name: /^All Depts/i });
  await userEvent.click(allDeptsPill);

  // Both visible again
  expect(screen.getByText('Carbide End Mill 10mm')).toBeInTheDocument();
  expect(screen.getByText('Hydraulic Oil ISO VG 68')).toBeInTheDocument();
});

test('+ Add Row opens modal and successfully calls departmental-row API', async () => {
  let createdPayload: any = null;
  let newRow: any = null;

  fetchMock.mockImplementation(async (input, init) => {
    const urlStr = String(input);
    if (urlStr.includes('/departmental-row') && init?.method === 'POST') {
      createdPayload = JSON.parse(String(init.body));
      newRow = {
        id: 'req-new-dept-1',
        planning_period: '2026-10',
        planning_month: 10,
        planning_year: 2026,
        part_name: '',
        part_number: createdPayload.part_number,
        consumable_code: createdPayload.consumable_code,
        consumable_name: createdPayload.consumable_name,
        process_name: 'DEPARTMENT_INDENT',
        part_thickness: '0.0000',
        process_count: 1,
        production_order_qty: '0.0000',
        scheduled_consumable_qty: createdPayload.scheduled_consumable_qty,
        plant: createdPayload.plant,
        process: 'DEPARTMENT_INDENT',
        description: createdPayload.consumable_name,
        unit: createdPayload.unit,
        rule_type: 'PLANT_REQUEST',
        required_qty: createdPayload.scheduled_consumable_qty,
        stock_qty: '0.0000',
        grn_received_qty: '0.0000',
        shortage_qty: createdPayload.scheduled_consumable_qty,
        po_pending_qty: '0.0000',
        msl: '0.0000',
        status: 'Critical shortage',
        remarks: createdPayload.remarks,
        historical_avg_qty: '0.0000',
        active_month_count: 0,
        doc_ref: createdPayload.part_number,
      };
      return jsonResponse(newRow);
    }
    if (urlStr.includes('/workspace/view')) {
      return jsonResponse({
        records: newRow ? [newRow, ...mockRequirements] : mockRequirements,
        plan_metadata: mockPlanMetadata,
      });
    }
    return jsonResponse([]);
  });

  renderRequirements();

  // Switch to Departmental tab
  const deptTab = await screen.findByRole('button', { name: /Departmental & Maintenance/i });
  await userEvent.click(deptTab);

  // Click + Add Row button
  const addRowBtn = await screen.findByRole('button', { name: /\+ Add Row/i });
  await userEvent.click(addRowBtn);

  // Verify modal is open
  expect(screen.getByText('Add Departmental Requirement Row')).toBeInTheDocument();

  // Fill in form inputs
  const codeInput = screen.getByLabelText(/Item ID/i);
  const descInput = screen.getByLabelText(/Item Description/i);
  const refInput = screen.getByLabelText(/Part \/ Doc Ref/i);
  const qtyInput = screen.getByLabelText(/Initial Required Qty/i);

  await userEvent.type(codeInput, 'BEAR-6205');
  await userEvent.type(descInput, 'Ball Bearing 6205-2RS');
  await userEvent.type(refInput, 'KNL/PMD/DI/45');
  await userEvent.clear(qtyInput);
  await userEvent.type(qtyInput, '25');

  // Submit form
  const submitBtn = screen.getByRole('button', { name: /Add Departmental Item/i });
  await userEvent.click(submitBtn);

  // Wait for submission to complete and modal to close
  await waitFor(() => {
    expect(screen.queryByText('Add Departmental Requirement Row')).not.toBeInTheDocument();
  });

  // Verify API call payload
  expect(createdPayload).toBeDefined();
  expect(createdPayload.consumable_code).toBe('BEAR-6205');
  expect(createdPayload.consumable_name).toBe('Ball Bearing 6205-2RS');
  expect(createdPayload.part_number).toBe('KNL/PMD/DI/45');
  expect(createdPayload.scheduled_consumable_qty).toBe('25');
  expect(createdPayload.month).toBe(10);
  expect(createdPayload.year).toBe(2026);

  // Verify new row rendered
  expect(await screen.findByText('Ball Bearing 6205-2RS')).toBeInTheDocument();
});

test('inline editing and Save Changes calls batch endpoint with updated fields', async () => {
  let batchPayload: any = null;

  fetchMock.mockImplementation(async (input, init) => {
    const urlStr = String(input);
    if ((urlStr.includes('/workspace/batch') || urlStr.includes('/workspace/records')) && (init?.method === 'PATCH' || init?.method === 'PUT')) {
      batchPayload = JSON.parse(String(init.body));
      return jsonResponse({
        message: 'Changes saved successfully (1 record updated).',
        updated_count: 1,
        records: mockRequirements.map(r =>
          r.id === 'req-dept-tr-1' ? { ...r, scheduled_consumable_qty: '30.0000', remarks: 'Updated cutter order' } : r
        ),
        plan_metadata: mockPlanMetadata,
      });
    }
    if (urlStr.includes('/workspace/view')) {
      return jsonResponse({
        records: mockRequirements,
        plan_metadata: mockPlanMetadata,
      });
    }
    return jsonResponse([]);
  });

  renderRequirements();

  // Switch to Departmental tab
  const deptTab = await screen.findByRole('button', { name: /Departmental & Maintenance/i });
  await userEvent.click(deptTab);

  expect(await screen.findByText('Carbide End Mill 10mm')).toBeInTheDocument();

  // Double click cell to edit
  const qtyCell = screen.getByText('12.0000');
  await userEvent.dblClick(qtyCell);

  const input = screen.getByLabelText('Edit Required Qty');
  await userEvent.clear(input);
  await userEvent.type(input, '30.0000{enter}');

  // Save Changes button should be enabled
  const saveBtn = await screen.findByRole('button', { name: /Save Changes/i });
  expect(saveBtn).toBeInTheDocument();
  await userEvent.click(saveBtn);

  await waitFor(() => {
    expect(batchPayload).toBeDefined();
  });
  expect(batchPayload.records[0].id).toBe('req-dept-tr-1');
});

test('multi-row selection and Delete Selected calls delete-batch API', async () => {
  let deleteBatchPayload: any = null;
  vi.spyOn(window, 'confirm').mockReturnValue(true);

  fetchMock.mockImplementation(async (input, init) => {
    const urlStr = String(input);
    if (urlStr.includes('/delete-batch') && init?.method === 'POST') {
      deleteBatchPayload = JSON.parse(String(init.body));
      return jsonResponse({
        message: 'Successfully deleted 1 requirement record(s).',
        deleted_count: 1,
        plan_metadata: mockPlanMetadata,
      });
    }
    if (urlStr.includes('/workspace/view')) {
      return jsonResponse({
        records: mockRequirements,
        plan_metadata: mockPlanMetadata,
      });
    }
    return jsonResponse([]);
  });

  renderRequirements();

  // Switch to Departmental tab
  const deptTab = await screen.findByRole('button', { name: /Departmental & Maintenance/i });
  await userEvent.click(deptTab);

  expect(await screen.findByText('Carbide End Mill 10mm')).toBeInTheDocument();

  // Check the first row checkbox
  const checkboxes = screen.getAllByRole('checkbox');
  // checkboxes[0] is header select-all, checkboxes[1] is first row
  await userEvent.click(checkboxes[1]);

  // Verify Delete Selected button appears
  const deleteBtn = await screen.findByRole('button', { name: /Delete Selected \(1\)/i });
  expect(deleteBtn).toBeInTheDocument();

  // Click Delete Selected
  await userEvent.click(deleteBtn);

  // Verify delete-batch API called with row ID and period
  await waitFor(() => {
    expect(deleteBatchPayload).toBeDefined();
  });
  expect(deleteBatchPayload.record_ids).toContain('req-dept-tr-1');
  expect(deleteBatchPayload.month).toBe(10);
  expect(deleteBatchPayload.year).toBe(2026);

  // Verify row removed from view
  expect(screen.queryByText('Carbide End Mill 10mm')).not.toBeInTheDocument();
});

test('dedicated departmental toolbar renders Upload Dept Excel and Export Dept Excel', async () => {
  let exportUrl = '';
  const originalCreateObjectURL = window.URL.createObjectURL;
  const originalRevokeObjectURL = window.URL.revokeObjectURL;
  window.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
  window.URL.revokeObjectURL = vi.fn();

  try {
    fetchMock.mockImplementation(async input => {
      const urlStr = String(input);
      if (urlStr.includes('/workspace/export')) {
        exportUrl = urlStr;
        return new Response('mock-excel-bytes', {
          status: 200,
          headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': 'attachment; filename="departmental_requirements_2026_10.xlsx"',
          },
        });
      }
      if (urlStr.includes('/workspace/view')) {
        return jsonResponse({
          records: mockRequirements,
          plan_metadata: mockPlanMetadata,
        });
      }
      return jsonResponse([]);
    });

    renderRequirements();

    // Switch to Departmental tab
    const deptTab = await screen.findByRole('button', { name: /Departmental & Maintenance/i });
    await userEvent.click(deptTab);

    // Verify Dedicated Toolbar elements
    expect(screen.getByRole('button', { name: /Upload Dept Excel/i })).toBeInTheDocument();
    const exportBtn = screen.getByRole('button', { name: /Export Dept Excel/i });
    expect(exportBtn).toBeInTheDocument();

    // Click Export Dept Excel
    await userEvent.click(exportBtn);

    await waitFor(() => {
      expect(exportUrl).toContain('/workspace/export');
      expect(exportUrl).toContain('scope=departmental');
      expect(exportUrl).toContain('month=10');
      expect(exportUrl).toContain('year=2026');
    });
  } finally {
    window.URL.createObjectURL = originalCreateObjectURL;
    window.URL.revokeObjectURL = originalRevokeObjectURL;
  }
});
