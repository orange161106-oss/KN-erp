import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';

function getPageTitle(pathname: string): string {
  if (pathname === '/' || pathname === '/dashboard') return 'Dashboard';
  if (pathname.startsWith('/prd')) return 'Production for sale';
  if (pathname.startsWith('/masters')) return 'Product master';
  if (pathname.startsWith('/rules')) return 'Consumption norms';
  if (pathname.startsWith('/mappings')) return 'Production mapping';
  if (pathname.startsWith('/requirements')) return 'Requirement';
  if (pathname.startsWith('/plant-workflow')) return 'Plant review';
  if (pathname.startsWith('/inventory/statement')) return 'Stock statement';
  if (pathname.startsWith('/inventory/management')) return 'Stock management';
  if (pathname.startsWith('/inventory')) return 'Stock history';
  if (pathname.startsWith('/purchase-orders')) return 'Purchase order';
  if (pathname.startsWith('/purchase')) return 'Purchase';
  if (pathname.startsWith('/grns')) return 'Goods receipts';
  if (pathname.startsWith('/alerts')) return 'Alerts';
  if (pathname.startsWith('/reports')) return 'Reports';
  if (pathname.startsWith('/admin')) return 'Administration';
  if (pathname.startsWith('/status')) return 'System Status';
  return 'KNL ERP Platform';
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const pageTitle = getPageTitle(location.pathname);

  return (
    <div className="app-shell flex h-dvh w-full min-h-0 min-w-0 overflow-hidden bg-erp-vanilla text-erp-chocolate">
      <Sidebar isCollapsed={isCollapsed} onToggleCollapse={() => setIsCollapsed(prev => !prev)} />
      
      <div className="app-shell-content min-h-0 min-w-0 flex-1 flex flex-col overflow-hidden bg-erp-vanilla">
        <header className="h-16 shrink-0 bg-vanilla-surface border-b border-ink-text/10 flex items-center justify-between px-6 shadow-2xs">
          <h1 className="text-xl font-semibold text-erp-chocolate">{pageTitle}</h1>
          <span className="text-xs text-erp-chocolate/60 font-medium tracking-wide">KNL ERP Platform</span>
        </header>

        <main className="min-h-0 min-w-0 flex-1 p-6 overflow-auto bg-erp-vanilla text-erp-chocolate">
          {children}
        </main>
      </div>
    </div>
  );
}

