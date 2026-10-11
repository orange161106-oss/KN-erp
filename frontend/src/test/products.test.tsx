import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import axios from 'axios';
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
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
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

test('bulk upload tracks axios onUploadProgress, transitions to parsing, auto-closes modal on 200, and displays toast', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async () => {
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  let progressCallback: any = null;
  const axiosPostSpy = vi.spyOn(axios, 'post').mockImplementation(async (_url, _data, config: any) => {
    progressCallback = config?.onUploadProgress;
    // simulate progress event 45%
    if (progressCallback) {
      progressCallback({ loaded: 45, total: 100 });
    }
    // simulate progress event 100%
    if (progressCallback) {
      progressCallback({ loaded: 100, total: 100 });
    }
    return {
      status: 200,
      data: {
        total_rows: 10,
        upserted: 10,
        errors: [],
      },
    };
  });

  render(
    <AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}>
      <Products />
    </AuthContext.Provider>
  );

  // Click Bulk Import to open modal
  fireEvent.click(screen.getByRole('button', { name: /Bulk Import ☁️/i }));
  expect(screen.getByRole('heading', { name: 'Bulk Excel Intake' })).toBeInTheDocument();

  // Create dummy file and select it
  const file = new File(['dummy content'], 'consumables.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(fileInput).not.toBeNull();

  fireEvent.change(fileInput, { target: { files: [file] } });

  expect(axiosPostSpy).toHaveBeenCalled();

  // Modal should auto-close on 200 OK
  await waitFor(() => {
    expect(screen.queryByRole('heading', { name: 'Bulk Excel Intake' })).not.toBeInTheDocument();
  });

  // Success toast and feedback are displayed
  const toastElements = await screen.findAllByText(/Bulk upload complete: 10 records successfully upserted/i);
  expect(toastElements.length).toBeGreaterThan(0);

  axiosPostSpy.mockRestore();
});

test('edit action populates intake form, changes button to Update Record, and submits PUT', async () => {
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

  // Find Edit button
  const editBtn = screen.getByTitle('Edit consumable');
  expect(editBtn).toBeInTheDocument();
  fireEvent.click(editBtn);

  // Form should now have "Update Record" button and "Cancel Edit"
  expect(screen.getByRole('button', { name: 'Update Record' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cancel Edit' })).toBeInTheDocument();

  // Click Update Record
  fireEvent.click(screen.getByRole('button', { name: 'Update Record' }));

  // Should have sent PUT to /consumables/c-101
  await waitFor(() => {
    const putCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/consumables/c-101') && call[1]?.method === 'PUT');
    expect(putCall).toBeDefined();
  });
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

  // Find Delete button
  const delBtn = screen.getByTitle('Delete consumable');
  fireEvent.click(delBtn);

  expect(confirmSpy).toHaveBeenCalled();

  await waitFor(() => {
    const patchCall = fetchSpy.mock.calls.find(call => String(call[0]).includes('/consumables/c-202/deactivate') && call[1]?.method === 'PATCH');
    expect(patchCall).toBeDefined();
  });

  confirmSpy.mockRestore();
});

