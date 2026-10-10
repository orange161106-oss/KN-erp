import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';
import { canOpen } from '../core/rbac';
import { ChevronDown, ChevronRight } from 'lucide-react';

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  if (!user) return null;

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

  const navItemClass = (path: string) =>
    `flex items-center px-3 py-2 rounded text-xs font-medium transition-colors select-none ${
      isActive(path)
        ? 'bg-burnt-orange/10 text-burnt-orange font-semibold border-l-2 border-burnt-orange shadow-2xs'
        : 'text-ink-text/70 hover:text-ink-text hover:bg-ink-text/5'
    }`;

  const subNavItemClass = (path: string) =>
    `flex items-center pl-6 pr-3 py-1.5 rounded text-xs font-medium transition-colors select-none ${
      isActive(path)
        ? 'bg-burnt-orange/10 text-burnt-orange font-semibold border-l-2 border-burnt-orange'
        : 'text-ink-text/60 hover:text-ink-text hover:bg-ink-text/5'
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
  const showAdmin = canOpen(user, '/admin');

  // Master data parent menu renders if user has _read access to EITHER Product master OR Consumption norms (or Production mapping)
  const showMasterData = showMasters || showNorms || showMappings;
  const isMasterDataActive = location.pathname.startsWith('/masters') || location.pathname.startsWith('/rules') || location.pathname.startsWith('/mappings');

  const [isMasterDataOpen, setIsMasterDataOpen] = useState(true);

  useEffect(() => {
    if (isMasterDataActive) {
      setIsMasterDataOpen(true);
    }
  }, [isMasterDataActive]);

  return (
    <aside className="w-64 bg-vanilla-surface text-ink-text border-r border-ink-text/10 flex flex-col select-none">
      <div className="p-4 text-lg font-bold border-b border-ink-text/10 tracking-tight text-ink-text flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-burnt-orange inline-block" />
        <span>KNL Consumable ERP</span>
      </div>

      <div className="px-4 py-2.5 bg-ink-text/5 text-[11px] font-semibold uppercase tracking-wider text-ink-text/70 flex items-center justify-between border-b border-ink-text/10">
        <span>{user.username}</span>
        <span className="text-[10px] bg-burnt-orange/15 text-burnt-orange px-1.5 py-0.5 rounded font-bold">
          {(user.is_super_admin || user.is_superuser) ? 'SUPER ADMIN' : user.roles[0] || 'USER'}
        </span>
      </div>

      <nav className="flex-1 p-3 space-y-1 flex flex-col overflow-y-auto">
        {/* 1. Dashboard */}
        {showDashboard && (
          <Link to="/" className={navItemClass('/')}>
            Dashboard
          </Link>
        )}

        {/* 2. Production for sale (formerly PRD / Planning) */}
        {showPrdPlanning && (
          <Link to="/prd" className={navItemClass('/prd')}>
            Production for sale
          </Link>
        )}

        {/* 3. Master data (Dropdown / Accordion menu) */}
        {showMasterData && (
          <div className="flex flex-col space-y-0.5">
            <button
              type="button"
              onClick={() => setIsMasterDataOpen(open => !open)}
              className={`flex items-center justify-between px-3 py-2 rounded text-xs font-medium transition-colors select-none w-full text-left ${
                isMasterDataActive
                  ? 'bg-burnt-orange/10 text-burnt-orange font-semibold border-l-2 border-burnt-orange'
                  : 'text-ink-text/70 hover:text-ink-text hover:bg-ink-text/5'
              }`}
            >
              <span>Master data</span>
              {isMasterDataOpen ? (
                <ChevronDown className="w-3.5 h-3.5 text-burnt-orange" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-ink-text/40" />
              )}
            </button>

            {isMasterDataOpen && (
              <div className="flex flex-col space-y-0.5 mt-0.5 pl-1 border-l border-ink-text/15 ml-2">
                {/* Product master (formerly Masters) */}
                {showMasters && (
                  <Link to="/masters" className={subNavItemClass('/masters')} aria-label="Product master" title="Product master">
                    Product master
                  </Link>
                )}

                {/* Consumption norms */}
                {showNorms && (
                  <Link to="/rules" className={subNavItemClass('/rules')}>
                    Consumption norms
                  </Link>
                )}

                {/* Production mapping (formerly Production Mappings) */}
                {showMappings && (
                  <Link to="/mappings" className={subNavItemClass('/mappings')}>
                    Production mapping
                  </Link>
                )}
              </div>
            )}
          </div>
        )}

        {/* 4. Requirement (formerly Requirements) */}
        {showRequirements && (
          <Link to="/requirements" className={navItemClass('/requirements')}>
            Requirement
          </Link>
        )}

        {/* 5. Plant review (formerly Plant Workflow) */}
        {showPlantWorkflow && (
          <Link to="/plant-workflow" className={navItemClass('/plant-workflow')}>
            Plant review
          </Link>
        )}

        {/* 6. Inventory */}
        {showInventory && (
          <Link to="/inventory" className={navItemClass('/inventory')}>
            Inventory
          </Link>
        )}

        {/* 7. Purchase */}
        {showPurchase && (
          <Link to="/purchase" className={navItemClass('/purchase')}>
            Purchase
          </Link>
        )}

        {/* 8. Purchase order (formerly Purchase Orders) */}
        {showPurchaseOrders && (
          <Link to="/purchase-orders" className={navItemClass('/purchase-orders')}>
            Purchase order
          </Link>
        )}

        {/* 9. Goods receipts */}
        {showGoodsReceipts && (
          <Link to="/grns" className={navItemClass('/grns')}>
            Goods receipts
          </Link>
        )}

        {/* 10. Alerts */}
        {showAlerts && (
          <Link to="/alerts" className={navItemClass('/alerts')}>
            Alerts
          </Link>
        )}

        {/* Bottom System & Admin Navigation */}
        <div className="mt-auto pt-3 border-t border-ink-text/10 flex flex-col space-y-1">
          {showAdmin && (
            <Link to="/admin" className={navItemClass('/admin')}>
              Administration
            </Link>
          )}
          <Link to="/status" className={navItemClass('/status')}>
            System Status
          </Link>
          <button
            onClick={logout}
            className="text-left text-red-700 hover:text-red-800 hover:bg-red-500/10 px-3 py-1.5 rounded transition-colors text-xs mt-2 font-semibold select-none flex items-center gap-1.5"
          >
            Logout
          </button>
        </div>
      </nav>
    </aside>
  );
}
