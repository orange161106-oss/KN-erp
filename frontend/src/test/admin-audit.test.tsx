import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import UserManagement from '../features/admin/UserManagement';
import SystemStatus from '../features/system/SystemStatus';
import Sidebar from '../components/Sidebar';
import { AuthContext } from '../features/auth/context';
import { adminAuditApi } from '../api/adminAudit';
import { usersApi } from '../api/users';

vi.mock('../api/client', () => ({
  apiClient: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/health')) {
        return Promise.resolve({ status: 'healthy' });
      }
      return Promise.resolve({});
    }),
  },
  getAccessToken: vi.fn(),
  getApiBaseUrl: vi.fn().mockReturnValue('http://localhost:8000'),
}));

vi.mock('../api/users', () => ({
  usersApi: {
    getUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
  },
}));

vi.mock('../api/adminAudit', () => ({
  adminAuditApi: {
    getAuditLogs: vi.fn(),
    getActiveSessions: vi.fn(),
  },
}));

describe('UI Architecture & RBAC: Relocate Audit Logs to System Status', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    (usersApi.getUsers as any).mockResolvedValue([
      {
        id: 'user-1',
        username: 'john_doe',
        full_name: 'John Doe',
        employee_id: 'EMP100',
        roles: ['PLANNER'],
        is_active: true,
        is_super_admin: false,
      },
    ]);

    (adminAuditApi.getActiveSessions as any).mockResolvedValue({
      items: [
        {
          id: 'sess-1',
          user_id: 'user-1',
          username: 'john_doe',
          full_name: 'John Doe',
          employee_id: 'EMP100',
          role: 'PLANNER',
          ip_address: '192.168.1.10',
          login_at: '2026-10-12T04:30:00Z',
          logout_at: null,
          status: 'ACTIVE',
        },
      ],
      total: 1,
      limit: 25,
      offset: 0,
    });

    (adminAuditApi.getAuditLogs as any).mockResolvedValue({
      items: [
        {
          id: 'audit-1',
          user_id: 'user-1',
          username: 'john_doe',
          action: 'CREATE',
          module: 'Product Master - Consumables',
          record_id: 'CON-001',
          changes_summary: { summary: 'Created Grease CON-001' },
          timestamp: '2026-10-12T04:35:00Z',
        },
        {
          id: 'audit-2',
          user_id: 'user-1',
          username: 'john_doe',
          action: 'DELETE',
          module: 'Product Master - Consumables',
          record_id: 'CON-001',
          changes_summary: { is_active: false },
          timestamp: '2026-10-12T04:40:00Z',
        },
      ],
      total: 2,
      limit: 25,
      offset: 0,
    });
  });

  describe('Task 1: Administration Component Refactor', () => {
    it('renders solely Users & Permissions view and removes sessions and audit tabs', async () => {
      render(<UserManagement />);

      // Users & Permissions title and Add button are present
      expect(screen.getByText('Users & Permissions')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Add New User/i })).toBeInTheDocument();

      // Navigation tabs for sessions and audit trail must NOT be present in UserManagement
      expect(screen.queryByRole('button', { name: /Active Users & Sessions/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /System Audit Trail/i })).not.toBeInTheDocument();

      // Default users table is loaded directly
      await waitFor(() => {
        expect(screen.getByText('john_doe')).toBeInTheDocument();
      });
    });
  });

  describe('Task 2: System Status Component with Tabbed Views', () => {
    it('defaults to Live Sessions tab and renders session monitoring ledger', async () => {
      render(<SystemStatus />);

      expect(screen.getByText('System Status & Audit Hub')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Live Sessions/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Audit Ledger/i })).toBeInTheDocument();

      // Active tab styling should be applied to Live Sessions
      const liveSessionsTab = screen.getByRole('button', { name: /Live Sessions/i });
      expect(liveSessionsTab.className).toContain('bg-erp-orange');

      // Verify ActiveSessions API was called
      await waitFor(() => {
        expect(adminAuditApi.getActiveSessions).toHaveBeenCalled();
      });

      // Verify Session elements render
      expect(screen.getAllByText('Active Now').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('192.168.1.10')).toBeInTheDocument();
    });

    it('switches to Audit Ledger tab and renders audit records with action tags', async () => {
      const user = userEvent.setup();
      render(<SystemStatus />);

      const auditTab = screen.getByRole('button', { name: /Audit Ledger/i });
      await user.click(auditTab);

      // Active tab styling should now be applied to Audit Ledger
      expect(auditTab.className).toContain('bg-erp-orange');

      // Verify AuditLogs API was called
      await waitFor(() => {
        expect(adminAuditApi.getAuditLogs).toHaveBeenCalled();
      });

      // Check rendered ledger items
      expect(screen.getByText('Immutable Audit Activity Ledger')).toBeInTheDocument();
      expect(screen.getAllByText('CREATE').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('DELETE').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Product Master - Consumables').length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Task 3: Enforce RBAC on System Status in Sidebar', () => {
    it('hides System Status from standard users in Sidebar', () => {
      const standardUser = {
        id: 'std-user',
        username: 'planner_user',
        roles: ['PLANNER'],
        permissions: ['prd_planning_read'],
        is_super_admin: false,
      };

      render(
        <AuthContext.Provider value={{ user: standardUser, login: vi.fn(), logout: vi.fn() }}>
          <MemoryRouter initialEntries={['/']}>
            <Sidebar />
          </MemoryRouter>
        </AuthContext.Provider>
      );

      // System Status link should NOT be rendered for standard users
      expect(screen.queryByTitle('System Status')).not.toBeInTheDocument();
      expect(screen.queryByTitle('Administration')).not.toBeInTheDocument();
    });

    it('displays System Status and Administration for Super Admins in Sidebar', () => {
      const adminUser = {
        id: 'admin-user',
        username: 'super_admin',
        roles: ['ADMIN'],
        permissions: [],
        is_super_admin: true,
      };

      render(
        <AuthContext.Provider value={{ user: adminUser, login: vi.fn(), logout: vi.fn() }}>
          <MemoryRouter initialEntries={['/']}>
            <Sidebar />
          </MemoryRouter>
        </AuthContext.Provider>
      );

      // System Status and Administration links are visible
      expect(screen.getByTitle('System Status')).toBeInTheDocument();
      expect(screen.getByTitle('Administration')).toBeInTheDocument();
    });
  });
});
