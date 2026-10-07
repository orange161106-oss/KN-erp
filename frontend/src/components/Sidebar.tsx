import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();

  if (!user) return null;

  const canSee = (allowedRoles: string[]) =>
    user.roles.includes('ADMIN') || allowedRoles.some(role => user.roles.includes(role));

  const canReadMasters = ['units', 'consumables', 'suppliers'].some(resource =>
    user.permissions.includes(`masters.${resource}.read`)
  );

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

  const navItemClass = (path: string) =>
    `flex items-center px-3 py-2 rounded text-xs font-medium transition-colors select-none ${
      isActive(path)
        ? 'bg-brand-steel text-white font-semibold shadow-xs'
        : 'text-gray-200 hover:text-white hover:bg-white/10'
    }`;

  return (
    <aside className="w-64 bg-brand-navy text-white flex flex-col select-none">
      <div className="p-4 text-lg font-bold border-b border-brand-steel/60 tracking-tight">
        KNL Consumable ERP
      </div>

      <div className="px-4 py-2.5 bg-brand-steel/40 text-[11px] font-semibold uppercase tracking-wider text-gray-200 flex items-center justify-between">
        <span>{user.username}</span>
        <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded text-white font-bold">
          {user.roles[0] || 'USER'}
        </span>
      </div>

      <nav className="flex-1 p-3 space-y-1 flex flex-col overflow-y-auto">
        {user.permissions.includes('purchase.grns.read') && (
          <Link to="/grns" className={navItemClass('/grns')}>
            Goods receipts
          </Link>
        )}

        {user.permissions.includes('purchase.orders.read') && (
          <Link to="/purchase-orders" className={navItemClass('/purchase-orders')}>
            Purchase orders
          </Link>
        )}

        <Link to="/" className={navItemClass('/')}>
          Dashboard
        </Link>

        {canReadMasters && (
          <Link to="/masters" className={navItemClass('/masters')}>
            Masters
          </Link>
        )}

        {(canReadMasters || canSee(['PLANNER'])) && (
          <Link to="/mappings" className={navItemClass('/mappings')}>
            Production Mappings
          </Link>
        )}

        {(canReadMasters || canSee(['PLANNER'])) && (
          <Link to="/rules" className={navItemClass('/rules')}>
            Consumption Norms
          </Link>
        )}

        {(canSee(['PLANNER', 'ADMIN', 'PLANT_INCHARGE', 'PURCHASE', 'STORE', 'MANAGEMENT']) ||
          user.permissions.includes('prd.records.read')) && (
          <Link to="/prd" className={navItemClass('/prd')}>
            PRD / Planning
          </Link>
        )}

        {(canSee(['PLANT_INCHARGE', 'ADMIN', 'PLANNER', 'PURCHASE', 'STORE', 'MANAGEMENT']) ||
          user.permissions.includes('requirements.records.read')) && (
          <Link to="/requirements" className={navItemClass('/requirements')}>
            Requirements
          </Link>
        )}

        {canSee(['PLANT_INCHARGE']) && (
          <Link to="/plant-workflow" className={navItemClass('/plant-workflow')}>
            Plant Workflow
          </Link>
        )}

        {user.permissions.includes('inventory.stock.read') && (
          <Link to="/inventory" className={navItemClass('/inventory')}>
            Inventory
          </Link>
        )}

        {(canSee(['PURCHASE', 'APPROVER', 'MANAGEMENT']) || user.permissions.includes('purchasing:view')) && (
          <Link to="/purchase" className={navItemClass('/purchase')}>
            Purchase
          </Link>
        )}

        {(canSee(['STORE', 'PLANT_INCHARGE']) || user.permissions.includes('alerts:view')) && (
          <Link to="/alerts" className={navItemClass('/alerts')}>
            Alerts
          </Link>
        )}

        {(user.permissions.includes('reports.inventory.read') ||
          user.permissions.includes('reports.purchase.read')) && (
          <Link to="/reports" className={navItemClass('/reports')}>
            Reports
          </Link>
        )}

        <div className="mt-auto pt-3 border-t border-brand-steel/40 flex flex-col space-y-1">
          {(user.roles.includes('ADMIN') || user.is_super_admin) && (
            <Link to="/admin" className={navItemClass('/admin')}>
              Administration
            </Link>
          )}
          <Link to="/status" className={navItemClass('/status')}>
            System Status
          </Link>
          <button
            onClick={logout}
            className="text-left text-red-400 hover:text-red-300 hover:bg-red-500/10 px-3 py-1.5 rounded transition-colors text-xs mt-2 font-semibold select-none flex items-center gap-1.5"
          >
            Logout
          </button>
        </div>
      </nav>
    </aside>
  );
}
