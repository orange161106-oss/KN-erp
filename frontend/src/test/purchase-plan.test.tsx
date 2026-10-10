import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PurchasePlanWorkspace from '../features/purchasing/PurchasePlanWorkspace';
import { AuthContext } from '../features/auth/context';
import { BrowserRouter } from 'react-router-dom';

const mockUser = {
  id: 'usr-admin-01',
  username: 'admin',
  roles: ['ADMIN', 'PURCHASE'],
  permissions: ['purchasing:view', 'purchase.read', 'purchase.write'],
  is_super_admin: true,
  purchase_read: true,
  purchase_update: true,
};

function renderWithAuth(ui: React.ReactElement) {
  return render(
    <AuthContext.Provider value={{ user: mockUser as any, login: vi.fn(), logout: vi.fn() }}>
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

describe('Purchase Plan Workspace', () => {
  it('renders View switcher with Normal View and MD View options', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    expect(screen.getByText(/Normal View \(23 cols\)/i)).toBeInTheDocument();
    expect(screen.getByText(/MD View \(76 cols\)/i)).toBeInTheDocument();
  });

  it('renders Month and Year selector controls', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    expect(screen.getByText('Month:')).toBeInTheDocument();
    expect(screen.getByText('Year:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Load Plan/i })).toBeInTheDocument();
  });

  it('renders Action Toolbar buttons', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    expect(screen.getByText(/Upload Excel Template/i)).toBeInTheDocument();
    expect(screen.getByText(/Recalculate Gap & Orders/i)).toBeInTheDocument();
    expect(screen.getByText(/Send to Approval Queue/i)).toBeInTheDocument();
    expect(screen.getByText(/Export Normal View/i)).toBeInTheDocument();
  });

  it('switches to MD View and preserves period and controls', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    const mdViewBtn = screen.getByText(/MD View \(76 cols\)/i);
    fireEvent.click(mdViewBtn);

    // Export button should now say Export MD View
    expect(screen.getByText(/Export MD View/i)).toBeInTheDocument();

    // Check MD View specific column bands and headers
    expect(screen.getByText(/ITEM \/ SUPPLIER/i)).toBeInTheDocument();
    expect(screen.getByText(/PART \/ PROCESS \(USAGE\)/i)).toBeInTheDocument();
  });

  it('displays plan parameters banner', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    expect(screen.getByText(/No. of MSL Days for Gas:/i)).toBeInTheDocument();
    expect(screen.getByText(/No. of MSL Days:/i)).toBeInTheDocument();
    expect(screen.getByText(/Month Days:/i)).toBeInTheDocument();
  });

  it('opens Excel upload modal on button click', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    const uploadBtn = screen.getByText(/Upload Excel Template/i);
    fireEvent.click(uploadBtn);

    expect(screen.getByText(/Import Purchase Plan Template/i)).toBeInTheDocument();
    expect(screen.getByText(/Choose Excel Workbook \(\.xlsx\)/i)).toBeInTheDocument();
  });

  it('column headers stay visible in both Normal View and MD View', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    // In Normal View
    expect(screen.getByText('Item Id')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Order Qty.')).toBeInTheDocument();

    // Switch to MD View
    fireEvent.click(screen.getByText(/MD View \(76 cols\)/i));
    expect(screen.getByText('Supplier ID')).toBeInTheDocument();
    expect(screen.getByText('Supplier name')).toBeInTheDocument();
  });

  it('renders Excel formula bar and status bar', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    expect(screen.getByText('fx')).toBeInTheDocument();
    expect(screen.getByLabelText(/Formula bar/i)).toBeInTheDocument();
    expect(screen.getByText(/Sheet 1:/i)).toBeInTheDocument();
  });

  it('allows managing column visibility to hide and unhide columns', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    // Open Columns menu
    const colBtn = screen.getByText(/Columns \(Hide\/Show\)/i);
    fireEvent.click(colBtn);

    expect(screen.getByText('Manage Column Visibility')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Filter columns…/i)).toBeInTheDocument();

    // Find checkbox for MOQ. and click it to hide
    const moqCheckbox = screen.getAllByRole('checkbox').find(cb => {
      const parent = cb.closest('label');
      return parent && parent.textContent?.includes('MOQ.');
    });

    if (moqCheckbox) {
      fireEvent.click(moqCheckbox);
      // Banner appears indicating hidden column
      expect(screen.getByText(/columns are currently hidden/i)).toBeInTheDocument();

      // Click Unhide All Columns
      const unhideBtn = screen.getByText(/Unhide All Columns/i);
      fireEvent.click(unhideBtn);
      expect(screen.queryByText(/columns are currently hidden/i)).not.toBeInTheDocument();
    }
  });

  it('allows toggling Freeze ID panes and edit mode', async () => {
    renderWithAuth(<PurchasePlanWorkspace currentUserId="usr-admin-01" />);

    const freezeBtn = screen.getByText(/Freeze ID: ON/i);
    expect(freezeBtn).toBeInTheDocument();
    fireEvent.click(freezeBtn);
    expect(screen.getByText(/Freeze ID: OFF/i)).toBeInTheDocument();

    const modeBtn = screen.getByText(/Mode: Excel Cell Mode/i);
    expect(modeBtn).toBeInTheDocument();
    fireEvent.click(modeBtn);
    expect(screen.getByText(/Mode: Direct Inputs/i)).toBeInTheDocument();
  });
});

