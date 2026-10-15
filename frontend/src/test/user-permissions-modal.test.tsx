import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UserPermissionsModal, { MODULES } from '../features/admin/UserPermissionsModal';
import { usersApi } from '../api/users';

vi.mock('../api/users', () => ({
  usersApi: {
    createUser: vi.fn(),
    updateUser: vi.fn(),
  },
}));

describe('Modernized User Permissions Modal UI/UX', () => {
  it('Task 1: syncs module nomenclature to exactly match new sidebar routing', () => {
    render(
      <UserPermissionsModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
        editingUser={null}
      />
    );

    // Verify all 10 module nomenclature labels exist
    expect(screen.getAllByText(/Product Master/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Consumption Norms/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Production Mapping/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Requirement/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Plant Review/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Inventory/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Purchase/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Purchase Order/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Goods Receipts/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/REPORTS & ALERTS \(FINAL WORKFLOW ITEMS\)/i)).toBeInTheDocument();

    // Verify MODULES array keys and labels
    const moduleLabels = MODULES.map(m => m.label);
    expect(moduleLabels.some(l => l.includes('Product Master'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Consumption Norms'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Production Mapping'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Requirement'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Plant Review'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Inventory'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Purchase'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Purchase Order'))).toBe(true);
    expect(moduleLabels.some(l => l.includes('Goods Receipts'))).toBe(true);
  });

  it('Task 2: applies Plus Jakarta Sans font and styled modal container with section headers', () => {
    const { container } = render(
      <UserPermissionsModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
        editingUser={null}
      />
    );

    // Modal overlay and container styling
    const overlay = container.firstElementChild as HTMLElement;
    expect(overlay.className).toContain('font-[\'Plus_Jakarta_Sans\',sans-serif]');

    const modalBox = overlay.firstElementChild as HTMLElement;
    expect(modalBox.className).toContain('bg-white');
    expect(modalBox.className).toContain('rounded-2xl');
    expect(modalBox.className).toContain('shadow-2xl');
    expect(modalBox.className).toContain('border-erp-dark-vanilla/30');

    // Section headers: text-erp-chocolate, tracking-wide, text-sm, font-bold
    const headerDetails = screen.getByText('BASIC USER DETAILS & CREDENTIALS');
    expect(headerDetails.className).toContain('text-erp-chocolate');
    expect(headerDetails.className).toContain('tracking-wide');
    expect(headerDetails.className).toContain('text-sm');
    expect(headerDetails.className).toContain('font-bold');

    const headerCrud = screen.getByText(/CRUD PERMISSION MATRIX/i);
    expect(headerCrud.className).toContain('text-erp-chocolate');
    expect(headerCrud.className).toContain('tracking-wide');
    expect(headerCrud.className).toContain('text-sm');
    expect(headerCrud.className).toContain('font-bold');
  });

  it('Task 3: modernizes inputs, checkboxes, floating cards, status tags, and action buttons', async () => {
    const user = userEvent.setup();
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    (usersApi.createUser as any).mockResolvedValue({ id: 'new-u' });

    render(
      <UserPermissionsModal
        isOpen={true}
        onClose={handleClose}
        onSuccess={handleSuccess}
        editingUser={null}
      />
    );

    // Inputs: focus:ring-2 and focus:ring-erp-orange
    const usernameInput = screen.getByPlaceholderText('e.g. store_user');
    expect(usernameInput.className).toContain('focus:ring-erp-orange');
    expect(usernameInput.className).toContain('border-erp-dark-vanilla/40');

    // Checkboxes: accent-erp-orange
    const checkboxes = screen.getAllByRole('checkbox');
    checkboxes.forEach(cb => {
      expect(cb.className).toContain('accent-erp-orange');
    });

    // Alert subscription minimal status tags: bg-erp-tangerine/15 text-erp-topaz rounded-md px-2 py-0.5 text-xs
    const plantTag = screen.getByText('Plant/Mfg');
    expect(plantTag.className).toContain('bg-erp-tangerine/15');
    expect(plantTag.className).toContain('text-erp-topaz');
    expect(plantTag.className).toContain('rounded-md');
    expect(plantTag.className).toContain('text-xs');

    // Action button: bg-erp-orange hover:bg-erp-tenne text-white
    const saveButton = screen.getByRole('button', { name: /Save User & Matrix/i });
    expect(saveButton.className).toContain('bg-erp-orange');
    expect(saveButton.className).toContain('hover:bg-erp-tenne');
    expect(saveButton.className).toContain('text-white');

    // Fill form and submit
    await user.type(usernameInput, 'new_specialist');
    await user.type(screen.getByPlaceholderText('••••••••'), 'SecurePassword123');
    await user.click(saveButton);

    expect(usersApi.createUser).toHaveBeenCalled();
  });
});
