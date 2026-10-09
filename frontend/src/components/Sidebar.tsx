import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();

  if (!user) return null;

  const isAdmin = Boolean(user.is_super_admin || user.roles.includes('ADMIN'));

  const hasPlantAccess = Boolean(
    user.can_access_plant_1 ||
    user.can_access_plant_2 ||
    user.can_access_plant_3 ||
    user.can_access_plant_4 ||
    user.can_access_plant_5
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

  // 1-to-1 CRUD Read authorization checks for each section
  const showMasters = isAdmin || Boolean(user.masters_read);
  const showMappings = isAdmin || Boolean(user.production_mappings_read);
  const showNorms = isAdmin || Boolean(user.consumption_norms_read);
  const showPrdPlanning = isAdmin || Boolean(user.prd_planning_read);
  const showRequirements = isAdmin || Boolean(user.requirements_read);
  const showPlantWorkflow = isAdmin || Boolean(user.plant_workflow_read) || hasPlantAccess;
  const showInventory = isAdmin || Boolean(user.inventory_read);
  const showPurchase = isAdmin || Boolean(user.purchase_read);
  const showPurchaseOrders = isAdmin || Boolean(user.purchase_orders_read);
  const showGoodsReceipts = isAdmin || Boolean(user.goods_receipts_read);
  const showReports = isAdmin || Boolean(user.inventory_read || user.purchase_read || user.requirements_read);

  return (
    <aside className="w-64 bg-brand-navy text-white flex flex-col select-none">
      <div className="p-4 text-lg font-bold border-b border-brand-steel/60 tracking-tight">
        KNL Consumable ERP
      </div>

      <div className="px-4 py-2.5 bg-brand-steel/40 text-[11px] font-semibold uppercase tracking-wider text-gray-200 flex items-center justify-between">
        <span>{user.username}</span>
        <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded text-white font-bold">
          {user.is_super_admin ? 'SUPER ADMIN' : user.roles[0] || 'USER'}
        </span>
      </div>

      <nav className="flex-1 p-3 space-y-1 flex flex-col overflow-y-auto">
        {/* 1. Dashboard - Always Visible */}
        <Link to="/" className={navItemClass('/')}>
          Dashboard
        </Link>

        {/* 2. Masters */}
        {showMasters && (
          <Link to="/masters" className={navItemClass('/masters')}>
            Masters
          </Link>
        )}

        {/* 3. Production Mappings */}
        {showMappings && (
          <Link to="/mappings" className={navItemClass('/mappings')}>
            Production Mappings
          </Link>
        )}

        {/* 4. Consumption Norms */}
        {showNorms && (
          <Link to="/rules" className={navItemClass('/rules')}>
            Consumption Norms
          </Link>
        )}

        {/* 5. PRD / Planning */}
        {showPrdPlanning && (
          <Link to="/prd" className={navItemClass('/prd')}>
            PRD / Planning
          </Link>
        )}

        {/* 6. Requirements */}
        {showRequirements && (
          <Link to="/requirements" className={navItemClass('/requirements')}>
            Requirements
          </Link>
        )}

        {/* 7. Plant Workflow */}
        {showPlantWorkflow && (
          <Link to="/plant-workflow" className={navItemClass('/plant-workflow')}>
            Plant Workflow
          </Link>
        )}

        {/* 8. Inventory */}
        {showInventory && (
          <Link to="/inventory" className={navItemClass('/inventory')}>
            Inventory
          </Link>
        )}

        {/* 9. Purchase */}
        {showPurchase && (
          <Link to="/purchase" className={navItemClass('/purchase')}>
            Purchase
          </Link>
        )}

        {/* 10. Purchase Orders */}
        {showPurchaseOrders && (
          <Link to="/purchase-orders" className={navItemClass('/purchase-orders')}>
            Purchase orders
          </Link>
        )}

        {/* 11. Goods Receipts */}
        {showGoodsReceipts && (
          <Link to="/grns" className={navItemClass('/grns')}>
            Goods receipts
          </Link>
        )}

        {/* 12. Alerts */}
        {showReports && (
          <Link to="/alerts" className={navItemClass('/alerts')}>
            Alerts
          </Link>
        )}

        {/* 13. Reports */}
        {showReports && (
          <Link to="/reports" className={navItemClass('/reports')}>
            Reports
          </Link>
        )}

        {/* Bottom System & Admin Navigation */}
        <div className="mt-auto pt-3 border-t border-brand-steel/40 flex flex-col space-y-1">
          {isAdmin && (
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
