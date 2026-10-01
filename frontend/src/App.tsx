import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import SystemStatus from './pages/SystemStatus';
import Login from './pages/Login';
import type { Role } from './pages/Login';
import Sidebar from './components/Sidebar';

function AppShell({ children, role, onLogout }: { children: React.ReactNode, role: Role, onLogout: () => void }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar role={role} onLogout={onLogout} />
      
      <div className="flex-1 flex flex-col">
        <header className="h-16 bg-white border-b border-gray-200 flex items-center px-6 shadow-sm">
          <h1 className="text-xl font-semibold text-brand-charcoal">KN ERP Platform</h1>
        </header>

        <main className="flex-1 p-6 overflow-auto bg-brand-offwhite">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [role, setRole] = useState<Role>(null);

  if (!role) {
    return <Login onLogin={setRole} />;
  }

  return (
    <BrowserRouter>
      <AppShell role={role} onLogout={() => setRole(null)}>
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}