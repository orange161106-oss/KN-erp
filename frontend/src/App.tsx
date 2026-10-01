import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import SystemStatus from './pages/SystemStatus';

function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-brand-navy text-white flex flex-col">
        <div className="p-4 text-lg font-bold border-b border-brand-steel">
          KN Consumable ERP
        </div>
        <nav className="flex-1 p-4 space-y-2 flex flex-col">
          <Link to="/" className="block hover:text-brand-steel transition-colors">Dashboard</Link>
          <Link to="/masters" className="block hover:text-brand-steel transition-colors">Masters</Link>
          <Link to="/prd" className="block hover:text-brand-steel transition-colors">PRD / Planning</Link>
          <Link to="/requirements" className="block hover:text-brand-steel transition-colors">Requirements</Link>
          <Link to="/inventory" className="block hover:text-brand-steel transition-colors">Inventory</Link>
          <Link to="/purchase" className="block hover:text-brand-steel transition-colors">Purchase</Link>
          <Link to="/alerts" className="block hover:text-brand-steel transition-colors">Alerts</Link>
          <Link to="/reports" className="block hover:text-brand-steel transition-colors">Reports</Link>
          <div className="mt-auto pt-4 border-t border-brand-steel flex flex-col space-y-2">
            <Link to="/admin" className="block hover:text-brand-steel transition-colors">Administration</Link>
            <Link to="/status" className="block hover:text-brand-steel transition-colors text-sm text-gray-300">System Status</Link>
          </div>
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center px-6 shadow-sm">
          <h1 className="text-xl font-semibold text-brand-charcoal">KN ERP Platform</h1>
        </header>

        {/* Content Routing */}
        <main className="flex-1 p-6 overflow-auto bg-brand-offwhite">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<div>Dashboard Placeholder</div>} />
          <Route path="/masters" element={<div>Masters Placeholder</div>} />
          <Route path="/prd" element={<div>PRD / Planning Placeholder</div>} />
          <Route path="/requirements" element={<div>Requirements Placeholder</div>} />
          <Route path="/inventory" element={<div>Inventory Placeholder</div>} />
          <Route path="/purchase" element={<div>Purchase Placeholder</div>} />
          <Route path="/alerts" element={<div>Alerts Placeholder</div>} />
          <Route path="/reports" element={<div>Reports Placeholder</div>} />
          <Route path="/admin" element={<div>Administration Placeholder</div>} />
          <Route path="/status" element={<SystemStatus />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}