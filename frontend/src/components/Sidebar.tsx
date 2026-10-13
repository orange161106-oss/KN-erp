import { useState, useEffect, useId } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';
import { canOpen } from '../core/rbac';
import {
  PanelLeft,
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
  FileSpreadsheet,
  History,
} from 'lucide-react';

export interface SidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface SidebarTooltip {
  label: string;
  trigger: HTMLElement;
  left: number;
  top: number;
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
  const tooltipId = useId();
  const [tooltip, setTooltip] = useState<SidebarTooltip | null>(null);

  useEffect(() => {
    const dismiss = () => setTooltip(null);
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', dismiss, true);
    return () => {
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('scroll', dismiss, true);
    };
  }, []);

  const tooltipProps = (label: string) => ({
    'data-sidebar-tooltip': isCollapsed ? label : undefined,
    'aria-describedby': isCollapsed && tooltip?.label === label ? tooltipId : undefined,
  });

  const showTooltip = (target: EventTarget | null) => {
    if (!isCollapsed || !(target instanceof Element)) return;
    const trigger = target.closest<HTMLElement>('[data-sidebar-tooltip]');
    const label = trigger?.dataset.sidebarTooltip;
    if (!trigger || !label) return;
    const rect = trigger.getBoundingClientRect();
    setTooltip(current => current?.trigger === trigger ? current : {
      label,
      trigger,
      left: rect.right + 12,
      top: Math.max(24, Math.min(rect.top + rect.height / 2, window.innerHeight - 24)),
    });
  };

  if (!user) return null;

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || location.pathname === '/dashboard';
    if (path === '/inventory') return location.pathname === '/inventory';
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

  const iconClass = (active: boolean, onLightBackground = false) =>
    `w-4 h-4 shrink-0 transition-transform duration-300 ease-out group-hover:scale-110 group-hover:-translate-y-0.5 ${
      active ? (onLightBackground ? 'text-erp-chocolate' : 'text-white') : 'text-erp-chocolate/70 group-hover:text-erp-chocolate'
    }`;

  // Authorization checks for each section
  const showDashboard = canOpen(user, '/');
  const showPrdPlanning = canOpen(user, '/prd');
  const showMasters = canOpen(user, '/masters');
  const showNorms = canOpen(user, '/rules');
  const showMappings = canOpen(user, '/mappings');
  const showRequirements = canOpen(user, '/requirements');
  const showPlantWorkflow = canOpen(user, '/plant-workflow');
  const showStockHistory = canOpen(user, '/inventory');
  const showStockStatement = canOpen(user, '/inventory/statement');
  const showStockManagement = canOpen(user, '/inventory/management');
  const showInventory = showStockHistory || showStockStatement || showStockManagement;
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

  const isInventoryActive = location.pathname.startsWith('/inventory');
  const [isInventoryOpen, setIsInventoryOpen] = useState(true);

  useEffect(() => {
    if (isInventoryActive) {
      setIsInventoryOpen(true);
    }
  }, [isInventoryActive]);

  return (
    <aside
      data-testid="sidebar-container"
      onMouseOver={event => showTooltip(event.target)}
      onMouseOut={event => {
        if (!(event.target instanceof Element)) return;
        const trigger = event.target.closest('[data-sidebar-tooltip]');
        if (trigger && event.relatedTarget instanceof Node && trigger.contains(event.relatedTarget)) return;
        setTooltip(null);
      }}
      onFocusCapture={event => showTooltip(event.target)}
      onBlurCapture={() => setTooltip(null)}
      onClickCapture={() => setTooltip(null)}
      onKeyDownCapture={event => {
        if (event.key === 'Escape') setTooltip(null);
      }}
      className={`${
        isCollapsed ? 'w-16' : 'w-64'
      } relative shrink-0 min-h-0 h-full overflow-hidden bg-white text-erp-chocolate border-r border-erp-dark-vanilla/30 flex flex-col select-none shadow-xs transition-all duration-300 ease-in-out`}
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
          onClick={() => {
            setTooltip(null);
            toggleCollapse();
          }}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          {...tooltipProps(isCollapsed ? 'Expand sidebar' : 'Collapse sidebar')}
          className="p-1.5 rounded-lg text-erp-chocolate/70 hover:text-erp-chocolate hover:bg-erp-vanilla/50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-erp-orange"
        >
          <PanelLeft className="w-5 h-5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
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

      <nav className="relative min-h-0 flex-1 p-3 space-y-1 flex flex-col overflow-y-auto">
        {/* 1. Dashboard */}
        {showDashboard && (
          <Link to="/" className={navItemClass('/')} {...tooltipProps('Dashboard')} aria-label="Dashboard">
            <LayoutDashboard className={iconClass(isActive('/'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Dashboard</span>
          </Link>
        )}

        {/* 2. Production for sale */}
        {showPrdPlanning && (
          <Link to="/prd" className={navItemClass('/prd')} {...tooltipProps('Production for sale')} aria-label="Production for sale">
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
              {...tooltipProps('Master data')}
              aria-label="Master data"
            >
              <div className={`flex items-center ${isCollapsed ? '' : 'space-x-3'}`}>
                <Database className={iconClass(isMasterDataActive, true)} />
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
                    {...tooltipProps('Product master')}
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
                    {...tooltipProps('Consumption norms')}
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
                    {...tooltipProps('Production mapping')}
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
            {...tooltipProps('Requirement')}
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
            {...tooltipProps('Plant review')}
            aria-label="Plant review"
          >
            <Building2 className={iconClass(isActive('/plant-workflow'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>Plant review</span>
          </Link>
        )}

        {/* 6. Inventory */}
        {showInventory && (
          <div className="flex flex-col space-y-0.5">
            <button
              type="button"
              onClick={() => setIsInventoryOpen(open => !open)}
              className={`group flex items-center ${
                isCollapsed ? 'justify-center px-2 py-2.5' : 'justify-between px-3 py-2'
              } rounded-lg text-xs font-medium transition-colors select-none w-full text-left ${
                isInventoryActive
                  ? 'bg-erp-vanilla/80 text-erp-chocolate font-semibold border-l-2 border-erp-orange'
                  : 'text-erp-chocolate/80 hover:text-erp-chocolate hover:bg-erp-vanilla/50'
              }`}
              {...tooltipProps('Inventory')}
              aria-label="Inventory"
            >
              <div className={`flex items-center ${isCollapsed ? '' : 'space-x-3'}`}>
                <Warehouse className={iconClass(isInventoryActive, true)} />
                <span className={isCollapsed ? 'sr-only' : 'truncate'}>Inventory</span>
              </div>
              {!isCollapsed && (
                isInventoryOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 text-erp-orange" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-erp-chocolate/40" />
                )
              )}
            </button>

            {isInventoryOpen && (
              <div
                className={`flex flex-col space-y-0.5 mt-0.5 ${
                  isCollapsed ? '' : 'pl-1 border-l border-erp-dark-vanilla/30 ml-2'
                }`}
              >
                {/* Stock history */}
                {showStockHistory && (
                  <Link
                    to="/inventory"
                    className={subNavItemClass('/inventory')}
                    {...tooltipProps('Stock history')}
                    aria-label="Stock history"
                  >
                    <History className={iconClass(isActive('/inventory'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Stock history</span>
                  </Link>
                )}

                {/* Stock statement */}
                {showStockStatement && (
                  <Link
                    to="/inventory/statement"
                    className={subNavItemClass('/inventory/statement')}
                    {...tooltipProps('Stock statement')}
                    aria-label="Stock statement"
                  >
                    <FileSpreadsheet className={iconClass(isActive('/inventory/statement'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Stock statement</span>
                  </Link>
                )}

                {/* Stock management */}
                {showStockManagement && (
                  <Link
                    to="/inventory/management"
                    className={subNavItemClass('/inventory/management')}
                    {...tooltipProps('Stock management')}
                    aria-label="Stock management"
                  >
                    <Sliders className={iconClass(isActive('/inventory/management'))} />
                    <span className={isCollapsed ? 'sr-only' : 'truncate'}>Stock management</span>
                  </Link>
                )}
              </div>
            )}
          </div>
        )}

        {/* 7. Purchase */}
        {showPurchase && (
          <Link
            to="/purchase"
            className={navItemClass('/purchase')}
            {...tooltipProps('Purchase')}
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
            {...tooltipProps('Purchase order')}
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
            {...tooltipProps('Goods receipts')}
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
            {...tooltipProps('Alerts')}
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
            {...tooltipProps('Reports')}
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
              {...tooltipProps('Administration')}
              aria-label="Administration"
            >
              <Shield className={iconClass(isActive('/admin'))} />
              <span className={isCollapsed ? 'sr-only' : 'truncate'}>Administration</span>
            </Link>
          )}
          <Link
            to="/status"
            className={navItemClass('/status')}
            {...tooltipProps('System Status')}
            aria-label="System Status"
          >
            <Activity className={iconClass(isActive('/status'))} />
            <span className={isCollapsed ? 'sr-only' : 'truncate'}>System Status</span>
          </Link>
          <button
            onClick={logout}
            {...tooltipProps('Logout')}
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
      {isCollapsed && tooltip && createPortal(
        <div
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none fixed z-[100] -translate-y-1/2 rounded-md bg-erp-chocolate px-3 py-2 text-xs font-medium text-white shadow-lg"
          style={{ left: tooltip.left, top: tooltip.top, maxWidth: Math.max(0, window.innerWidth - tooltip.left - 12) }}
        >
          {tooltip.label}
        </div>,
        document.body,
      )}
    </aside>
  );
}
