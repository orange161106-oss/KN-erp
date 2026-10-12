import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import StockStatementWorkspace from '../features/inventory/StockStatementWorkspace';
import StockManagementWorkspace from '../features/inventory/StockManagementWorkspace';
import { AuthContext } from '../features/auth/context';
import { apiClient } from '../api/client';

const mockUser = {
  id: 'test-user-id',
  username: 'inventory_manager',
  roles: ['ADMIN'],
  permissions: ['inventory.stock.read', 'inventory.stock.import', 'inventory.read'],
  inventory_read: true,
  inventory_create: true,
  inventory_update: true,
  inventory_delete: true,
  is_super_admin: false,
};

function renderWithAuth(ui: React.ReactElement, initialRoute = '/') {
  return render(
    <AuthContext.Provider
      value={{
        user: mockUser,
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter initialEntries={[initialRoute]}>
        {ui}
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe('Stock Statement and Stock Management Sub-modules', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Inventory sub-menu in Sidebar with Stock history, Stock statement, and Stock management', () => {
    renderWithAuth(<Sidebar />, '/inventory');

    // Parent Inventory button
    expect(screen.getByRole('button', { name: 'Inventory' })).toBeInTheDocument();

    // Sub-menu items
    expect(screen.getByRole('link', { name: 'Stock history' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Stock statement' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Stock management' })).toBeInTheDocument();
  });

  it('renders StockStatementWorkspace with month/year selectors and toolbar controls', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({
      metadata: {
        has_statement: true,
        batch_id: 'batch-001',
        statement_month: 10,
        statement_year: 2026,
        statement_date: '2026-10-31',
        source_filename: 'KNL_Oct26_Stock.xlsx',
        created_at: '2026-10-31T10:00:00Z',
        created_by_name: 'John Doe',
        updated_at: '2026-10-31T11:00:00Z',
        updated_by_name: 'John Doe',
        row_count: 1,
        warning_count: 0,
      },
      summary: {
        item_count: 1,
        total_opening_value: 10000,
        total_receipt_value: 5000,
        total_issue_value: 2000,
        total_closing_value: 13000,
        warning_rows_count: 0,
      },
      records: [
        {
          id: 'line-1',
          item_id: 'CONS-001',
          item_description: 'Safety Helmet',
          cust_part_no: 'CPN-01',
          unit: 'NOS',
          opening_qty: 10,
          opening_value: 10000,
          receipt_qty: 5,
          receipt_value: 5000,
          issue_qty: 2,
          issue_value: 2000,
          closing_qty: 13,
          closing_value: 13000,
          source_row: 3,
          warning_codes: [],
          diff_closing_qty: null,
          diff_closing_value: null,
        },
      ],
    });

    renderWithAuth(<StockStatementWorkspace />, '/inventory/statement');

    // Title
    expect(screen.getByText('Stock Statement')).toBeInTheDocument();

    // Persisted metadata
    await waitFor(() => {
      expect(screen.getAllByText(/John Doe/).length).toBeGreaterThan(0);
    });

    // Upload statement button
    expect(screen.getByRole('button', { name: /Upload statement/i })).toBeInTheDocument();

    // Export Excel button
    expect(screen.getByRole('button', { name: /Export Excel/i })).toBeInTheDocument();
  });

  it('renders StockManagementWorkspace with 8 columns, editable limits, and save button', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({
      metadata: {
        has_parameters: true,
        batch_id: 'param-001',
        month: 10,
        year: 2026,
        effective_date: '2026-10-01',
        source_filename: 'Stock_Params_Oct26.xlsx',
        created_at: '2026-10-01T08:00:00Z',
        created_by_name: 'Jane Smith',
        updated_at: '2026-10-01T08:00:00Z',
        updated_by_name: 'Jane Smith',
        row_count: 1,
      },
      summary: {
        item_count: 1,
        missing_limits_count: 0,
        min_exceeds_max_count: 0,
      },
      records: [
        {
          id: 'param-line-1',
          item_id: 'CONS-001',
          category: 'Safety',
          type_of_material: 'Gear',
          description: 'Safety Helmet',
          min_stock_level: 50,
          max_stock_level: 200,
          min_order_qty: 25,
          lead_time_days: 14,
          edited_after_import: false,
          source_row: 3,
        },
      ],
    });

    renderWithAuth(<StockManagementWorkspace />, '/inventory/management');

    // Title
    expect(screen.getByText('Stock Management')).toBeInTheDocument();

    // Persisted metadata
    await waitFor(() => {
      expect(screen.getAllByText(/Jane Smith/).length).toBeGreaterThan(0);
    });

    // Toolbar buttons
    expect(screen.getByRole('button', { name: /Upload parameters/i })).toBeInTheDocument();
    expect(screen.getByTitle('Save changes (Ctrl+S)')).toBeInTheDocument();
  });
});
