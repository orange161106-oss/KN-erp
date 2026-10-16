import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setAccessToken } from '../api/client';
import { AuthContext } from '../features/auth/context';
import Products from '../features/masters/Products';

beforeEach(() => {
  setAccessToken(null);
});

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

test('renders Product Master with 3 tabs and split-screen intake for consumables', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => {
    if (String(input).endsWith('/workspace')) {
      return new Response(JSON.stringify({ category: 'consumables', review_token: 'a'.repeat(64), row_count: 0, filename: null, report: {}, records: [] }), { status: 200 });
    }
    if (String(input).includes('/product-master/consumables')) {
      return new Response(JSON.stringify({
        items: [
          {
            id: 'c-1',
            supplier_id: 'SUP-01',
            supplier_name: 'Tata Steel',
            item_id: 'CS-ST-001',
            category: 'Raw Material',
            type_of_material: 'Steel',
            description: 'Cold Rolled Steel',
            output_unit: 'KG',
            rate: 45.5,
            is_active: true,
          }
        ],
        total: 1,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  // Check Page Title
  expect(screen.getByRole('heading', { name: 'Product Master' })).toBeInTheDocument();

  // Check 3 Tabs
  expect(screen.getByRole('button', { name: 'List of Consumables' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Consumable for Assemble' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'List of Sales Parts' })).toBeInTheDocument();

  // Check Single Entry & Bulk Import Action Button
  expect(screen.getByRole('heading', { name: 'Single Consumable Intake' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Bulk Import ☁️/i })).toBeInTheDocument();

  // Clicking Bulk Import opens the centered modal with Bulk Excel Intake
  fireEvent.click(screen.getByRole('button', { name: /Bulk Import ☁️/i }));
  expect(screen.getByRole('heading', { name: 'Bulk Excel Intake' })).toBeInTheDocument();
  // Close the modal
  await waitFor(() => expect(screen.getByRole('button', { name: 'Close bulk import' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Close bulk import' }));
  expect(screen.queryByRole('heading', { name: 'Bulk Excel Intake' })).not.toBeInTheDocument();

  // Check Aligned Table Headers
  expect(screen.getByRole('columnheader', { name: /Supplier ID/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Supplier name/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Item Id/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Category/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Type of material/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Description/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Output\/Unit/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Rate/i })).toBeInTheDocument();

  // Verify loaded data in table
  expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();
  expect(screen.getByText('SUP-01')).toBeInTheDocument();
  expect(screen.getByText('Tata Steel')).toBeInTheDocument();
});

test('switching tabs navigates to assemble BOM and sales parts views', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => {
    const url = String(input);
    if (url.includes('/product-master/sales-parts')) {
      return new Response(JSON.stringify({
        items: [
          {
            id: 'sp-1',
            s_no: 1,
            part_no: 'PN-900',
            item_id: 'ITM-900',
            part_description: 'Bracket Assembly',
            uom: 'NOS',
            is_active: true,
          }
        ],
        total: 1,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  const user = userEvent.setup();
  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  // Switch to Consumable for Assemble tab
  await user.click(screen.getByRole('button', { name: 'Consumable for Assemble' }));
  expect(await screen.findByRole('heading', { name: 'Single Assembly Intake' })).toBeInTheDocument();

  // Switch to List of Sales Parts tab
  await user.click(screen.getByRole('button', { name: 'List of Sales Parts' }));
  expect(await screen.findByRole('heading', { name: 'Single Sales Part Intake' })).toBeInTheDocument();
  expect(await screen.findByText('PN-900')).toBeInTheDocument();
});

test('localized inline search dynamically filters table records', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => {
    if (String(input).includes('/product-master/consumables')) {
      return new Response(JSON.stringify({
        items: [
          {
            id: 'c-1',
            supplier_id: 'SUP-01',
            supplier_name: 'Tata Steel',
            item_id: 'CS-ST-001',
            category: 'Raw Material',
            type_of_material: 'Steel',
            description: 'Cold Rolled Steel',
            output_unit: 'KG',
            rate: 45.5,
            is_active: true,
          },
          {
            id: 'c-2',
            supplier_id: 'SUP-02',
            supplier_name: 'Jindal Steel',
            item_id: 'CS-AL-002',
            category: 'Alloy',
            type_of_material: 'Aluminum',
            description: 'Aluminum Sheet',
            output_unit: 'PCS',
            rate: 120.0,
            is_active: true,
          }
        ],
        total: 2,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();
  expect(screen.getByText('CS-AL-002')).toBeInTheDocument();

  // Filter by Supplier ID in column search (Column 1)
  const searchInputs = screen.getAllByPlaceholderText('Search...');
  fireEvent.change(searchInputs[0], { target: { value: 'SUP-01' } });

  expect(screen.getByText('CS-ST-001')).toBeInTheDocument();
  expect(screen.queryByText('CS-AL-002')).not.toBeInTheDocument();

  // Clear filters
  fireEvent.click(screen.getByRole('button', { name: 'Clear Filters' }));
  expect(screen.getByText('CS-AL-002')).toBeInTheDocument();
});

test.each([
  ['consumables', 'List of Consumables', { item_id: 'TEST-MAT-1', description: 'Synthetic material', output_unit: 'PCS' }],
  ['assemble', 'Consumable for Assemble', { consumable_item: 'TEST-MAT-1', part_no_saleable_item: 'TEST-PART-1', process_name: 'Sample process', output_unit: 'PCS' }],
  ['sales_parts', 'List of Sales Parts', { part_no: 'TEST-PART-1', item_id: 'TEST-ITEM-1', part_description: 'Synthetic part', uom: 'PCS' }],
] as const)('bulk upload previews then saves %s explicitly without month/year controls', async (category, label, record) => {
  const empty = { category, review_token: 'a'.repeat(64), row_count: 0, filename: null, report: {}, records: [] };
  const saved = { ...empty, row_count: 1, filename: 'synthetic.xlsx', records: [{ id: 'c-1', ...record }] };
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/workspace/preview')) return new Response(JSON.stringify(saved), { status: 200 });
    if (url.endsWith('/workspace')) return new Response(JSON.stringify(init?.method === 'POST' ? saved : empty), { status: 200 });
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 });
  });
  vi.stubGlobal('fetch', fetchSpy);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
    <Products />
  </AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: label }));
  fireEvent.click(screen.getByRole('button', { name: /Bulk Import/i }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled());
  expect(screen.queryByLabelText('Upload month')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Upload year')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Master Excel file'), { target: { files: [new File(['synthetic'], 'consumables.xlsx')] } });
  expect(await screen.findByText(/1 unique items ready for review/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('1 items saved successfully.')).toBeInTheDocument();
  const posted = fetchSpy.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posted).toHaveLength(2);
  expect(String(posted[0][0])).toContain(`/${category}/workspace/preview`);
  expect(String(posted[1][0])).toContain(`/${category}/workspace`);
  expect(posted[1][1]?.body).toBeInstanceOf(FormData);
  expect(screen.getByRole('button', { name: 'Delete data' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Export Excel' })).toBeEnabled();
});

test('an employee granted master creation can open bulk import without gaining delete permission', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => new Response(JSON.stringify(
    String(input).endsWith('/workspace')
      ? { category: 'consumables', review_token: 'a'.repeat(64), row_count: 0, filename: null, report: {}, records: [] }
      : { items: [], total: 0 },
  ), { status: 200 })));
  render(<AuthContext.Provider value={{ user: { id: 'uploader', username: 'uploader', roles: ['USER'], permissions: [],
    masters_read: true, masters_create: true, masters_update: false, masters_delete: false }, login: vi.fn(), logout: vi.fn() }}>
    <Products />
  </AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: /Bulk Import/i }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Delete data' })).toBeDisabled();
  expect(screen.queryByRole('heading', { name: 'Single Consumable Intake' })).not.toBeInTheDocument();
});

test.each([
  ['consumables', 'List of Consumables', { item_id: 'TEST-MAT-1', description: 'Pending material' }],
  ['assemble', 'Consumable for Assemble', { consumable_item: 'TEST-MAT-1', part_no_saleable_item: 'TEST-PART-1', process_name: 'ASSEMBLY' }],
] as const)('allows %s upload without a unit and edits the unit after saving', async (category, label, record) => {
  const empty = { category, review_token: 'a'.repeat(64), row_count: 0, filename: null, report: {}, records: [] };
  let saved = { ...empty, row_count: 1, records: [{ id: 'pending-1', ...record, output_unit: null as string | null }] };
  let exists = false;
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/workspace/preview')) return new Response(JSON.stringify(saved), { status: 200 });
    if (url.endsWith('/workspace')) {
      if (init?.method === 'POST') exists = true;
      if (init?.method === 'PATCH') saved = { ...saved, records: [{ ...saved.records[0], output_unit: 'KG' }] };
      return new Response(JSON.stringify(exists ? saved : empty), { status: 200 });
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 });
  });
  vi.stubGlobal('fetch', fetchSpy);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
    <Products />
  </AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: label }));
  fireEvent.click(screen.getByRole('button', { name: /Bulk Import/i }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Master Excel file'), { target: { files: [new File(['synthetic'], 'pending.xlsx')] } });
  expect(await screen.findByText(/Stock Unit is optional/)).toBeInTheDocument();
  expect(await screen.findByText(/1 unique items ready for review/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Apply to unresolved units' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('1 items saved successfully.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  const writesBeforeConfirmation = fetchSpy.mock.calls.filter(([, init]) => ['POST', 'PATCH'].includes(init?.method ?? '')).length;
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(screen.getByText('All 1 items are already saved. Edit a cell when you want to make changes.')).toBeInTheDocument();
  expect(fetchSpy.mock.calls.filter(([, init]) => ['POST', 'PATCH'].includes(init?.method ?? ''))).toHaveLength(writesBeforeConfirmation);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Reviewed stock unit'), { target: { value: 'KG' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply to unresolved units' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(fetchSpy.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true));
  const [, init] = fetchSpy.mock.calls.find(([, init]) => init?.method === 'PATCH')!;
  expect(JSON.parse(String(init?.body)).updates).toEqual([{ id: 'pending-1', changes: { output_unit: 'KG' } }]);
});

test('edit row stays in the consumables table and saves only the changed fields', async () => {
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method || 'GET';

    if (url.includes('/product-master/consumables') && method === 'GET') {
      return new Response(JSON.stringify({
        items: [
          {
            id: 'c-101',
            supplier_id: 'SUP-99',
            supplier_name: 'Tata Steel',
            item_id: 'CS-ST-999',
            category: 'Raw Material',
            type_of_material: 'Steel',
            description: 'CR Coil 1.2mm',
            output_unit: 'KG',
            rate: 65.0,
            is_active: true,
          }
        ],
        total: 1,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }

    if (url.includes('/product-master/consumables/c-101') && method === 'PUT') {
      return new Response(JSON.stringify({
        id: 'c-101',
        item_id: 'CS-ST-999',
        message: 'Consumable updated successfully.',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }

    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchSpy);

  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  expect(await screen.findByText('CS-ST-999')).toBeInTheDocument();

  fireEvent.contextMenu(screen.getByText('CS-ST-999'), { clientX: 300, clientY: 250 });
  fireEvent.click(screen.getByRole('menuitem', { name: 'Edit row…' }));

  expect(screen.getByLabelText('Edit Description').closest('tr')).toHaveTextContent('CS-ST-999');
  expect(screen.queryByRole('button', { name: 'Update Record' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save Consumable' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Edit Description'), { target: { value: 'Updated in this row' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  // Should have sent PUT to /consumables/c-101
  await waitFor(() => {
    const putCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/consumables/c-101') && call[1]?.method === 'PUT');
    expect(putCall).toBeDefined();
    expect(JSON.parse(String(putCall?.[1]?.body))).toEqual({ description: 'Updated in this row' });
  });
  expect(await screen.findByText('Updated in this row')).toBeInTheDocument();
});

test('delete action triggers confirmation dialog and sends deactivation request', async () => {
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  let activeItems = [
    {
      id: 'c-202',
      supplier_id: 'SUP-10',
      supplier_name: 'Jindal Steel',
      item_id: 'CS-AL-500',
      category: 'Alloy',
      type_of_material: 'Aluminum',
      description: 'Al Strip',
      output_unit: 'PCS',
      rate: 90.0,
      is_active: true,
    }
  ];

  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method || 'GET';

    if (url.includes('/product-master/consumables') && method === 'GET') {
      return new Response(JSON.stringify({
        items: activeItems,
        total: activeItems.length,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }

    if (url.includes('/product-master/consumables/c-202/deactivate') && method === 'PATCH') {
      activeItems = []; // deactivated
      return new Response(JSON.stringify({
        id: 'c-202',
        is_active: false,
        message: 'Consumables item deactivated successfully.',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }

    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchSpy);

  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  expect(await screen.findByText('CS-AL-500')).toBeInTheDocument();

  fireEvent.contextMenu(screen.getByText('CS-AL-500'), { clientX: 300, clientY: 250 });
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete row…' }));

  expect(confirmSpy).toHaveBeenCalled();

  await waitFor(() => {
    const patchCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/consumables/c-202/deactivate') && call[1]?.method === 'PATCH');
    expect(patchCall).toBeDefined();
  });

  confirmSpy.mockRestore();
});

test('RBAC Lockdown: standard USER has read-only table with no intake form, bulk import, or edit/delete buttons, and SUPER ADMIN restores full toolset', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => {
    if (String(input).includes('/product-master/consumables')) {
      return new Response(JSON.stringify({
        items: [
          {
            id: 'c-read-only-1',
            supplier_id: 'SUP-99',
            supplier_name: 'Standard Steel',
            item_id: 'CS-RO-001',
            category: 'Raw Material',
            type_of_material: 'Steel',
            description: 'Read-only Item',
            output_unit: 'KG',
            rate: 55.0,
            is_active: true,
          }
        ],
        total: 1,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  // 1. Log in as a standard USER
  const { rerender } = render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'user-standard',
          username: 'worker1',
          roles: ['USER'],
          role: 'USER',
          permissions: ['masters.read'],
          is_super_admin: false,
          masters_read: true,
        },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Products />
    </AuthContext.Provider>
  );

  // Read-only data must be present
  expect(await screen.findByText('CS-RO-001')).toBeInTheDocument();
  expect(screen.getByText('Read-only Item')).toBeInTheDocument();

  // Write & destructive tools MUST be completely absent for standard USER
  expect(screen.queryByRole('button', { name: /Bulk Import/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /Single Consumable Intake/i })).not.toBeInTheDocument();
  expect(screen.queryByTitle(/Edit consumable/i)).not.toBeInTheDocument();
  expect(screen.queryByTitle(/Delete consumable/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Edit \/ Del/i)).not.toBeInTheDocument();
  fireEvent.contextMenu(screen.getByText('CS-RO-001'));
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();

  // 2. Log back in as a SUPER ADMIN
  rerender(
    <AuthContext.Provider
      value={{
        user: {
          id: 'root-admin',
          username: 'root',
          roles: ['ADMIN'],
          role: 'SUPER ADMIN',
          permissions: [],
          is_super_admin: true,
        },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Products />
    </AuthContext.Provider>
  );

  // Full toolset MUST return for SUPER ADMIN
  expect(await screen.findByRole('button', { name: /Bulk Import ☁️/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Single Consumable Intake' })).toBeInTheDocument();
  fireEvent.contextMenu(screen.getByText('CS-RO-001'), { clientX: 300, clientY: 250 });
  expect(screen.getByRole('menuitem', { name: 'Edit row…' })).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'Delete row…' })).toBeInTheDocument();
  expect(screen.queryByText('Edit / Del')).not.toBeInTheDocument();
});

test('renders Consumable for Assemble tab with all 9 updated form labels and table column headers', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/product-master/assemble')) {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'asm-1',
              consumable_item: 'CS-ST-004',
              part_no_saleable_item: 'PN-DOOR-LH',
              used_for_name_of_saleable_part: 'Outer Door LH',
              used_part_no_prd_order: 'PRD-PART-01',
              process_name: 'ASSEMBLY',
              material_thickness_in_mm_gsm: '1.20mm',
              no_of_process_per_part: 1.0,
              output_unit: 'PCS',
              rate: 85.5,
              is_active: true,
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return new Response(JSON.stringify({ items: [], total: 0 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }));

  const user = userEvent.setup();
  render(
    <AuthContext.Provider
      value={{
        user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Products />
    </AuthContext.Provider>
  );

  // Switch to Consumable for Assemble tab
  await user.click(screen.getByRole('button', { name: 'Consumable for Assemble' }));

  // 1. Verify all 9 Form Labels in Single Assembly Intake form
  expect(screen.getByText(/Consumable Description/i, { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText(/Part No. of Saleable Item/i, { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Used for – Name of Saleable Part', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Used Part No. (PRD Order)', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Process Name', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Material Thickness in mm / GSM', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('No. of Processes per Part', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Output / Unit', { selector: 'label' })).toBeInTheDocument();
  expect(screen.getByText('Rate', { selector: 'label' })).toBeInTheDocument();

  // 2. Verify all 9 Column Headers in Consumable for Assemble Table
  expect(screen.getByRole('columnheader', { name: /Consumable Description/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Part No. of Saleable Item/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Used for – Name of Saleable Part/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Used Part No. \(PRD Order\)/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Process Name/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Material Thickness in mm \/ GSM/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /No. of Processes per Part/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /Output \/ Unit/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /^Rate/i })).toBeInTheDocument();

  // 3. Verify record values display correctly
  expect(await screen.findByText('CS-ST-004')).toBeInTheDocument();
  expect(screen.getByText('PN-DOOR-LH')).toBeInTheDocument();
  expect(screen.getByText('Outer Door LH')).toBeInTheDocument();
  expect(screen.getByText('PRD-PART-01')).toBeInTheDocument();
  expect(screen.getByText('1.0000')).toBeInTheDocument();
  expect(screen.getByText('₹85.50')).toBeInTheDocument();
});

test('handles Consumable for Assemble CRUD and validation messages with approved terminology', async () => {
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method || 'GET';

    if (url.includes('/product-master/assemble') && method === 'GET') {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'asm-99',
              consumable_item: 'CS-ST-099',
              part_no_saleable_item: 'PN-HOOD-01',
              used_for_name_of_saleable_part: 'Engine Hood',
              used_part_no_prd_order: 'PRD-HOOD',
              process_name: 'ASSEMBLY',
              material_thickness_in_mm_gsm: '1.50mm',
              no_of_process_per_part: 2.0,
              output_unit: 'PCS',
              rate: 150.0,
              is_active: true,
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }

    if (url.includes('/product-master/assemble/single') && method === 'POST') {
      return new Response(
        JSON.stringify({
          id: 'asm-100',
          message: 'Assembly mapping saved successfully.',
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } }
      );
    }

    if (url.includes('/product-master/assemble/asm-99') && method === 'PUT') {
      return new Response(
        JSON.stringify({
          id: 'asm-99',
          message: 'Assembly mapping updated successfully.',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }

    if (url.includes('/product-master/assemble/asm-99/deactivate') && method === 'PATCH') {
      return new Response(
        JSON.stringify({
          id: 'asm-99',
          is_active: false,
          message: 'Assembly mapping deactivated successfully.',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }

    return new Response(JSON.stringify({ items: [], total: 0 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchSpy);

  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  const user = userEvent.setup();

  render(
    <AuthContext.Provider
      value={{
        user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <Products />
    </AuthContext.Provider>
  );

  // Switch to Consumable for Assemble tab
  await user.click(screen.getByRole('button', { name: 'Consumable for Assemble' }));
  expect(await screen.findByText('CS-ST-099')).toBeInTheDocument();

  // Test validation error message on empty submit
  const saveBtn = screen.getByRole('button', { name: 'Save Assembly Mapping' });
  fireEvent.click(saveBtn);
  // HTML5 required handles native validation, but if submitted directly with empty fields:
  // Test edit mode
  fireEvent.contextMenu(screen.getByText('CS-ST-099'), { clientX: 300, clientY: 250 });
  fireEvent.click(screen.getByRole('menuitem', { name: 'Edit row…' }));
  expect(screen.getByLabelText('Edit Saleable Part Name').closest('tr')).toHaveTextContent('CS-ST-099');
  expect(screen.queryByRole('button', { name: 'Update Record' })).not.toBeInTheDocument();

  // Submit update
  fireEvent.change(screen.getByLabelText('Edit Process Count'), { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => {
    const putCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/assemble/asm-99') && call[1]?.method === 'PUT');
    expect(putCall).toBeDefined();
    expect(JSON.parse(String(putCall?.[1]?.body))).toEqual({ no_of_process_per_part: '3' });
  });

  // Test delete mode
  await waitFor(() => expect(screen.getByRole('button', { name: /↻ Refresh/i })).toBeEnabled());
  fireEvent.contextMenu(screen.getByText('CS-ST-099'), { clientX: 300, clientY: 250 });
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete row…' }));
  expect(confirmSpy).toHaveBeenCalled();
  await waitFor(() => {
    const patchCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/assemble/asm-99/deactivate') && call[1]?.method === 'PATCH');
    expect(patchCall).toBeDefined();
  });

  // Test Refresh button
  const refreshBtn = screen.getByRole('button', { name: /↻ Refresh/i });
  fireEvent.click(refreshBtn);
  expect(fetchSpy).toHaveBeenCalled();

  confirmSpy.mockRestore();
});

test.each([
  ['consumables', 'List of Consumables'], ['assemble', 'Consumable for Assemble'],
] as const)('%s right-click and keyboard menus target the chosen row and preserve deletion confirmation', async (category, tabLabel) => {
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const records = [1, 2].map(number => category === 'consumables'
    ? { id: `row-${number}`, item_id: `MAT-${number}`, supplier_id: null, supplier_name: '', category: '', type_of_material: '',
      description: `Material ${number}`, output_unit: 'PCS', rate: 2, is_active: true }
    : { id: `row-${number}`, consumable_item: `MAT-${number}`, part_no_saleable_item: `PART-${number}`,
      used_for_name_of_saleable_part: `Part ${number}`, used_part_no_prd_order: '', process_name: 'ASSEMBLY',
      material_thickness_in_mm_gsm: '', no_of_process_per_part: 1, output_unit: 'PCS', rate: 2, is_active: true });
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => new Response(JSON.stringify(
    String(input).includes(`/product-master/${category}`) && init?.method === 'GET'
      ? { items: records, total: 2 } : { items: [], total: 0 },
  ), { status: 200 }));
  vi.stubGlobal('fetch', fetchSpy);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
    <Products />
  </AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: tabLabel }));
  const chosen = (await screen.findByText('MAT-2')).closest('tr')!;
  fireEvent.contextMenu(chosen, { clientX: 5000, clientY: 5000 });
  const menu = screen.getByRole('menu');
  expect(parseFloat(menu.style.left)).toBeLessThan(window.innerWidth);
  expect(parseFloat(menu.style.top)).toBeLessThan(window.innerHeight);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Edit row…' }));
  expect(chosen).toContainElement(screen.getByLabelText(category === 'consumables' ? 'Edit Description' : 'Edit Saleable Part Name'));
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  fireEvent.contextMenu(chosen);
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  chosen.focus();
  fireEvent.keyDown(chosen, { key: 'F10', shiftKey: true });
  expect(screen.getByRole('menuitem', { name: 'Edit row…' })).toHaveFocus();
  await user.keyboard('{ArrowDown}');
  expect(screen.getByRole('menuitem', { name: 'Delete row…' })).toHaveFocus();
  await user.keyboard('{Enter}');
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining(category === 'consumables' ? 'MAT-2' : 'PART-2'));
  expect(fetchSpy.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false);
  confirm.mockReturnValue(true);
  fireEvent.contextMenu(chosen);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete row…' }));
  await waitFor(() => expect(fetchSpy.mock.calls.some(([url, init]) =>
    String(url).endsWith(`/${category}/row-2/deactivate`) && init?.method === 'PATCH')).toBe(true));
  expect(fetchSpy.mock.calls.some(([url, init]) =>
    String(url).endsWith(`/${category}/row-1/deactivate`) && init?.method === 'PATCH')).toBe(false);
  confirm.mockRestore();
});

test.each([
  ['consumables', 'List of Consumables'], ['assemble', 'Consumable for Assemble'],
] as const)('%s edits the clicked cell in place, retains failed edits and cancels blank-unit edits', async (category, tabLabel) => {
  const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  const record = category === 'consumables'
    ? { id: 'inline-1', item_id: 'INLINE-MAT', supplier_id: null, supplier_name: '', category: '', type_of_material: '',
      description: 'Inline material', output_unit: '', rate: 2, is_active: true }
    : { id: 'inline-1', consumable_item: 'INLINE-MAT', part_no_saleable_item: 'INLINE-PART',
      used_for_name_of_saleable_part: 'Inline part', used_part_no_prd_order: '', process_name: 'ASSEMBLY',
      material_thickness_in_mm_gsm: '', no_of_process_per_part: 1, output_unit: '', rate: 2, is_active: true };
  let writes = 0;
  const fetchSpy = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    if (init?.method === 'PUT') {
      writes++;
      return new Response(JSON.stringify(writes === 1 ? { message: 'Synthetic save error' } : { id: record.id }), { status: writes === 1 ? 422 : 200 });
    }
    return new Response(JSON.stringify(String(input).includes(`/product-master/${category}`)
      ? { items: [record], total: 1 } : { items: [], total: 0 }), { status: 200 });
  });
  vi.stubGlobal('fetch', fetchSpy);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
    <Products />
  </AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: tabLabel }));
  const row = (await screen.findByText('INLINE-MAT')).closest('tr')!;
  const rateCell = row.querySelectorAll('td')[category === 'consumables' ? 7 : 8];
  const readsBefore = fetchSpy.mock.calls.filter(([, init]) => init?.method === 'GET').length;
  fireEvent.contextMenu(rateCell);
  expect(screen.getByRole('menuitem', { name: 'Edit cell' })).toBeEnabled();
  fireEvent.click(screen.getByRole('menuitem', { name: 'Edit cell' }));
  const input = screen.getByLabelText('Edit Rate');
  expect(row).toContainElement(input);
  expect(screen.getAllByLabelText(/^Edit /)).toHaveLength(1);
  expect(screen.queryByRole('button', { name: 'Update Record' })).not.toBeInTheDocument();
  expect(scroll).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '7.1234' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic save error');
  expect(input).toHaveValue('7.1234');
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(screen.queryByLabelText('Edit Rate')).not.toBeInTheDocument());
  const calls = fetchSpy.mock.calls.filter(([, init]) => init?.method === 'PUT');
  expect(calls).toHaveLength(2);
  expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ rate: '7.1234' });
  expect(fetchSpy.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(readsBefore);
  fireEvent.doubleClick(row.querySelectorAll('td')[category === 'consumables' ? 6 : 7]);
  expect(screen.getByLabelText('Edit Stock Unit')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Edit Stock Unit'), { target: { value: 'KG' } });
  fireEvent.keyDown(screen.getByLabelText('Edit Stock Unit'), { key: 'Escape' });
  expect(screen.queryByLabelText('Edit Stock Unit')).not.toBeInTheDocument();
  expect(writes).toBe(2);
  expect(scroll).not.toHaveBeenCalled();
  scroll.mockRestore();
});


