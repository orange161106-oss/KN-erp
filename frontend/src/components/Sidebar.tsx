import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';
import { canOpen } from '../core/rbac';
import {
  Menu,
  ChevronDown,
  ChevronRight,
  LayoutDashboard,
  Factory,
  Database,
  Package,
  Sliders,
  Workflow,
  ClipboardList,
  Building2,
  Warehouse,
  ShoppingCart,
  Receipt,
  Truck,
  Bell,
  BarChart3,
  Shield,
  Activity,
  LogOut,
} from 'lucide-react';

export interface SidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function Sidebar({
  isCollapsed: controlledCollapsed,
  onToggleCollapse,
}: SidebarProps = {}) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : internalCollapsed;
  const toggleCollapse = onToggleCollapse || (() => setInternalCollapsed(prev => !prev));

  if (!user) return null;

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

  const navItemClass = (path: string) =>
    `group relative flex items-center ${
      isCollapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2 space-x-3'
    } rounded-lg text-xs font-medium transition-colors select-none ${
      isActive(path)
        ? 'bg-erp-orange text-white font-semibold shadow-xs'
        : 'text-erp-chocolate/80 hover:text-erp-chocolate hover:bg-erp-vanilla/50'
    }`;

  const subNavItemClass = (path: string) =>
    `group relative flex items-center ${
      isCollapsed ? 'justify-center px-2 py-2' : 'pl-6 pr-3 py-1.5 space-x-2'
    } rounded-lg text-xs font-medium transition-colors select-none ${
      isActive(path)
        ? 'bg-erp-orange text-white font-semibold shadow-xs'
        : 'text-erp-chocolate/70 hover:text-erp-chocolate hover:bg-erp-vanilla/50'
    }`;

  const iconClass = (active: boolean) =>
    `w-4 h-4 shrink-0 transition-transform duration-300 ease-out group-hover:scale-110 group-hover:-translate-y-0.5 ${
      active ? 'text-white' : 'text-erp-chocolate/70 group-hover:text-erp-chocolate'
    }`;

  // Authorization checks for each section
  const showDashboard = canOpen(user, '/');
  const showPrdPlanning = canOpen(user, '/prd');
  const showMasters = canOpen(user, '/masters');
  const showNorms = canOpen(user, '/rules');
  const showMappings = canOpen(user, '/mappings');
  const showRequirements = canOpen(user, '/requirements');
  const showPlantWorkflow = canOpen(user, '/plant-workflow');
  const showInventory = canOpen(user, '/inventory');
  const showPurchase = canOpen(user, '/purchase');
  const showPurchaseOrders = canOpen(user, '/purchase-orders');
  const showGoodsReceipts = canOpen(user, '/grns');
  const showAlerts = canOpen(user, '/alerts');
  const showReports = canOpen(user, '/reports');
  const showAdmin = canOpen(user, '/admin');

  // Master data parent menu renders if user has _read access to EITHER Product master OR Consumption norms (or Production mapping)
  const showMasterData = showMasters || showNorms || showMappings;
  const isMasterDataActive =
    location.pathname.startsWith('/masters') ||
    location.pathname.startsWith('/rules') ||
    location.pathname.startsWith('/mappings');

  const [isMasterDataOpen, setIsMasterDataOpen] = useState(true);

  useEffect(() => {
    if (isMasterDataActive) {
      setIsMasterDataOpen(true);
    }
  }, [isMasterDataActive]);

  return (
    <aside
      data-testid="sidebar-container"
      className={`${
        isCollapsed ? 'w-16' : 'w-64'
      } shrink-0 h-full bg-white text-erp-chocolate border-r border-erp-dark-vanilla/30 flex flex-col select-none shadow-xs transition-all duration-300 ease-in-out`}
    >
      <div
        className={`p-4 border-b border-erp-dark-vanilla/20 tracking-tight text-erp-chocolate flex items-center ${
          isCollapsed ? 'justify-center' : 'justify-between'
        }`}
      >
        {!isCollapsed && (
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="w-2.5 h-2.5 rounded-full bg-erp-orange shrink-0 inline-block" />
            <span className="font-bold text-sm lg:text-base truncate">KNL Consumable ERP</span>
          </div>
        )}
        <button
          type="button"
          onClick={toggleCollapse}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-1.5 rounded-lg text-erp-chocolate/70 hover:text-erp-chocolate hover:bg-erp-vanilla/50 transition-colors focus:outline-none"
        >
          <Menu className="w-5 h-5 shrink-0" />
        </button>
      </div>

      {isCollapsed ? (
        <div
          className="py-2.5 bg-erp-vanilla/40 flex items-center justify-center border-b border-erp-dark-vanilla/20"
          title={`${user.username} (${user.is_super_admin || user.is_superuser ? 'SUPER ADMIN' : user.roles[0] || 'USER'})`}
        >
          <span className="w-7 h-7 rounded-full bg-erp-orange text-white text-[11px] font-bold flex items-center justify-center uppercase shadow-xs">
            {user.username ? user.username.charAt(0) : 'U'}
          </span>
        </div>
      ) : (
        <div className="px-4 py-2.5 bg-erp-vanilla/40 text-[11px] font-semibold uppercase tracking-wider text-erp-chocolate/80 flex items-center justify-between border-b border-erp-dark-vanilla/20">
          <span className="truncate">{user.username}</span>
          <span className="text-[10px] bg-erp-orange text-white px-2 py-0.5 rounded-full font-bold shrink-0">
            {user.is_super_admin || user.is_superuser ? 'SUPER ADMIN' : user.roles[0] || 'USER'}
          </span>
        </div>
      )}

      <nav className="flex-1 p-3 space-y-1 flex flex-col overflow-y-auto">
        {/* 1. Dashboard */}
        {showDashboard && (
          <Link to="/" className={navItemClass('/')} title="Dashboard" aria-label="Dashboard">
            <LayoutDashboard className={iconClass(isActive('/'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Dashboard</span>
          </Link>
        )}

        {/* 2. Production for sale */}
        {showPrdPlanning && (
          <Link to="/prd" className={navItemClass('/prd')} title="Production for sale" aria-label="Production for sale">
            <Factory className={iconClass(isActive('/prd'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Production for sale</span>
          </Link>
        )}

        {/* 3. Master data */}
        {showMasterData && (
          <div className="flex flex-col space-y-0.5">
            <button
              type="button"
              onClick={() => setIsMasterDataOpen(open => !open)}
              className={`group flex items-center ${
                isCollapsed ? 'justify-center px-2 py-2.5' : 'justify-between px-3 py-2'
              } rounded-lg text-xs font-medium transition-colors select-none w-full text-left ${
                isMasterDataActive
                  ? 'bg-erp-vanilla/80 text-erp-chocolate font-semibold border-l-2 border-erp-orange'
                  : 'text-erp-chocolate/80 hover:text-erp-chocolate hover:bg-erp-vanilla/50'
              }`}
              title="Master data"
              aria-label="Master data"
            >
              <div className={`flex items-center ${isCollapsed ? '' : 'space-x-3'}`}>
                <Database className={iconClass(isMasterDataActive)} />
                <span className={isCollapsed ? 'sr-only' : 'truncate'}>Master data</span>
              </div>
              {!isCollapsed && (
                isMasterDataOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 text-erp-orange" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-erp-chocolate/40" />
                )
              )}
            </button>

            {isMasterDataOpen && (
              <div
                className={`flex flex-col space-y-0.5 mt-0.5 ${
                  isCollapsed ? '' : 'pl-1 border-l border-erp-dark-vanilla/30 ml-2'
                }`}
              >
                {/* Product master */}
                {showMasters && (
                  <Link
                    to="/masters"
                    className={subNavItemClass('/masters')}
                    title="Product master"
                    aria-label="Product master"
                  >
                    <Package className={iconClass(isActive('/masters'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Product master</span>
                  </Link>
                )}

                {/* Consumption norms */}
                {showNorms && (
                  <Link
                    to="/rules"
                    className={subNavItemClass('/rules')}
                    title="Consumption norms"
                    aria-label="Consumption norms"
                  >
                    <Sliders className={iconClass(isActive('/rules'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Consumption norms</span>
                  </Link>
                )}

                {/* Production mapping */}
                {showMappings && (
                  <Link
                    to="/mappings"
                    className={subNavItemClass('/mappings')}
                    title="Production mapping"
                    aria-label="Production mapping"
                  >
                    <Workflow className={iconClass(isActive('/mappings'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Production mapping</span>
                  </Link>
                )}
              </div>
            )}
          </div>
        )}

        {/* 4. Requirement */}
        {showRequirements && (
          <Link
            to="/requirements"
            className={navItemClass('/requirements')}
            title="Requirement"
            aria-label="Requirement"
          >
            <ClipboardList className={iconClass(isActive('/requirements'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Requirement</span>
          </Link>
        )}

        {/* 5. Plant review */}
        {showPlantWorkflow && (
          <Link
            to="/plant-workflow"
            className={navItemClass('/plant-workflow')}
            title="Plant review"
            aria-label="Plant review"
          >
            <Building2 className={iconClass(isActive('/plant-workflow'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Plant review</span>
          </Link>
        )}

        {/* 6. Inventory */}
        {showInventory && (
          <Link
            to="/inventory"
            className={navItemClass('/inventory')}
            title="Inventory"
            aria-label="Inventory"
          >
            <Warehouse className={iconClass(isActive('/inventory'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Inventory</span>
          </Link>
        )}

        {/* 7. Purchase */}
        {showPurchase && (
          <Link
            to="/purchase"
            className={navItemClass('/purchase')}
            title="Purchase"
            aria-label="Purchase"
          >
            <ShoppingCart className={iconClass(isActive('/purchase'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Purchase</span>
          </Link>
        )}

        {/* 8. Purchase order */}
        {showPurchaseOrders && (
          <Link
            to="/purchase-orders"
            className={navItemClass('/purchase-orders')}
            title="Purchase order"
            aria-label="Purchase order"
          >
            <Receipt className={iconClass(isActive('/purchase-orders'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Purchase order</span>
          </Link>
        )}

        {/* 9. Goods receipts */}
        {showGoodsReceipts && (
          <Link
            to="/grns"
            className={navItemClass('/grns')}
            title="Goods receipts"
            aria-label="Goods receipts"
          >
            <Truck className={iconClass(isActive('/grns'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Goods receipts</span>
          </Link>
        )}

        {/* 10. Alerts */}
        {showAlerts && (
          <Link
            to="/alerts"
            className={navItemClass('/alerts')}
            title="Alerts"
            aria-label="Alerts"
          >
            <Bell className={iconClass(isActive('/alerts'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Alerts</span>
          </Link>
        )}

        {/* 11. Reports */}
        {showReports && (
          <Link
            to="/reports"
            className={navItemClass('/reports')}
            title="Reports"
            aria-label="Reports"
          >
            <BarChart3 className={iconClass(isActive('/reports'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Reports</span>
          </Link>
        )}

        {/* Bottom System & Admin Navigation */}
        <div className="mt-auto pt-3 border-t border-ink-text/10 flex flex-col space-y-1">
          {showAdmin && (
            <Link
              to="/admin"
              className={navItemClass('/admin')}
              title="Administration"
              aria-label="Administration"
            >
              <Shield className={iconClass(isActive('/admin'))} />
              <span className={isCollapsed ? 'sr-only' : 'truncate'}>Administration</span>
            </Link>
          )}
          <Link
            to="/status"
            className={navItemClass('/status')}
            title="System Status"
            aria-label="System Status"
          >
            <Activity className={iconClass(isActive('/status'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>System Status</span>
          </Link>
          <button
            onClick={logout}
            title="Logout"
            aria-label="Logout"
            className={`group ${
              isCollapsed ? 'justify-center px-2 py-2' : 'px-3 py-1.5'
            } text-left text-red-700 hover:text-red-800 hover:bg-red-500/10 rounded transition-colors text-xs mt-2 font-semibold select-none flex items-center gap-2 w-full`}
          >
            <LogOut className="w-4 h-4 shrink-0 transition-transform duration-300 ease-out group-hover:scale-110 group-hover:-translate-y-0.5 text-red-700" />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Logout</span>
          </button>
        </div>
      </nav>
    </aside>
  );
}
