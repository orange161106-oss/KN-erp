import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { AuthContext } from '../features/auth/context';

const mockUser = {
  id: 'test-user',
  username: 'admin_user',
  roles: ['ADMIN'],
  permissions: [
    'dashboard.read',
    'prd.read',
    'masters.read',
    'rules.read',
    'mappings.read',
    'requirements.read',
    'plant_workflow.read',
    'inventory.read',
    'purchase.read',
    'purchase_orders.read',
    'grns.read',
    'alerts.read',
    'reports.read',
    'admin.read',
  ],
  is_super_admin: true,
};

function renderSidebar(props = {}) {
  return render(
    <AuthContext.Provider
      value={{
        user: mockUser,
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter initialEntries={['/']}>
        <Sidebar {...props} />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe('Sidebar Component - Dynamic Sidebar & Premium Motion', () => {
  it('Task 1: toggles collapsed state and applies width transitions and text label hiding', async () => {
    const user = userEvent.setup();
    renderSidebar();

    const aside = screen.getByTestId('sidebar-container');
    // Initially expanded: w-64 and transition classes
    expect(aside.className).toContain('w-64');
    expect(aside.className).toContain('transition-all');
    expect(aside.className).toContain('duration-300');
    expect(aside.className).toContain('ease-in-out');

    // Title text visible
    expect(screen.getByText('KNL Consumable ERP')).toBeInTheDocument();

    // Click sidebar toggle to collapse the navigation
    const toggleButton = screen.getByRole('button', { name: /Collapse sidebar/i });
    expect(toggleButton).toBeInTheDocument();
    await user.click(toggleButton);

    // After collapsing: w-16
    expect(aside.className).toContain('w-16');

    // Text labels gracefully hidden using sr-only
    const dashboardLabel = screen.getByText('Dashboard');
    expect(dashboardLabel.className).toContain('sr-only');

    // Button label switched to expand
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument();
  });

  it('shows menu names on hover outside the collapsed scrolling sidebar', async () => {
    const user = userEvent.setup();
    renderSidebar({ isCollapsed: true });

    const reports = screen.getByRole('link', { name: 'Reports' });
    await user.hover(reports.querySelector('svg')!);
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('Reports');
    expect(reports).toHaveAttribute('aria-describedby', tooltip.id);
    expect(screen.getByTestId('sidebar-container')).not.toContainElement(tooltip);

    await user.unhover(reports.querySelector('svg')!);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    await user.hover(screen.getByRole('button', { name: 'Master data' }));
    expect(screen.getByRole('tooltip')).toHaveTextContent('Master data');
  });

  it('shows tooltips on keyboard focus and dismisses them on Escape and scrolling', () => {
    renderSidebar({ isCollapsed: true });
    const dashboard = screen.getByRole('link', { name: 'Dashboard' });

    fireEvent.focus(dashboard);
    expect(screen.getByRole('tooltip')).toHaveTextContent('Dashboard');
    fireEvent.keyDown(dashboard, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    fireEvent.focus(screen.getByRole('link', { name: 'Stock statement' }));
    expect(screen.getByRole('tooltip')).toHaveTextContent('Stock statement');
    fireEvent.scroll(screen.getByRole('navigation'));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('keeps the expanded menu free of hover tooltips and clears them when expanded', async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.hover(screen.getByRole('link', { name: 'Dashboard' }));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    await user.hover(screen.getByRole('link', { name: 'Dashboard' }));
    expect(screen.getByRole('tooltip')).toHaveTextContent('Dashboard');
    await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('Task 1: respects external isCollapsed prop when passed from layout', () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <AuthContext.Provider value={{ user: mockUser, login: vi.fn(), logout: vi.fn() }}>
        <MemoryRouter initialEntries={['/']}>
          <Sidebar isCollapsed={false} onToggleCollapse={onToggle} />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const aside = screen.getByTestId('sidebar-container');
    expect(aside.className).toContain('w-64');

    rerender(
      <AuthContext.Provider value={{ user: mockUser, login: vi.fn(), logout: vi.fn() }}>
        <MemoryRouter initialEntries={['/']}>
          <Sidebar isCollapsed={true} onToggleCollapse={onToggle} />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    expect(aside.className).toContain('w-16');
  });

  it('Task 2: contains NO raw system emojis and every navigation link uses modern SVG icons', () => {
    const { container } = renderSidebar();

    // Check no raw emojis in the sidebar text
    const emojiRegex = /[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/u;
    const textContent = container.textContent || '';
    expect(emojiRegex.test(textContent)).toBe(false);

    // Specifically verify Reports item has no 📊 emoji
    const reportsLink = screen.getByRole('link', { name: /Reports/i });
    expect(reportsLink.textContent).not.toContain('📊');

    // Verify all nav links have SVG icons
    const links = screen.getAllByRole('link');
    expect(links.length).toBeGreaterThan(5);
    links.forEach(link => {
      const svg = link.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });
  });

  it('Task 3: applies fluid hover micro-interaction motion classes to SVG icons', () => {
    renderSidebar();

    // Verify group class on nav items
    const reportsLink = screen.getByRole('link', { name: /Reports/i });
    expect(reportsLink.className).toContain('group');

    // Verify micro-interaction classes on the SVG icon
    const reportsSvg = reportsLink.querySelector('svg');
    expect(reportsSvg).toBeInTheDocument();
    expect(reportsSvg?.getAttribute('class')).toContain('transition-transform');
    expect(reportsSvg?.getAttribute('class')).toContain('duration-300');
    expect(reportsSvg?.getAttribute('class')).toContain('ease-out');
    expect(reportsSvg?.getAttribute('class')).toContain('group-hover:scale-110');
    expect(reportsSvg?.getAttribute('class')).toContain('group-hover:-translate-y-0.5');

    // Also check on Dashboard and Logout
    const dashboardSvg = screen.getByRole('link', { name: /Dashboard/i }).querySelector('svg');
    expect(dashboardSvg?.getAttribute('class')).toContain('group-hover:scale-110');
    expect(dashboardSvg?.getAttribute('class')).toContain('group-hover:-translate-y-0.5');

    const logoutBtn = screen.getByRole('button', { name: /Logout/i });
    const logoutSvg = logoutBtn.querySelector('svg');
    expect(logoutSvg?.getAttribute('class')).toContain('group-hover:scale-110');
    expect(logoutSvg?.getAttribute('class')).toContain('group-hover:-translate-y-0.5');
  });
});
