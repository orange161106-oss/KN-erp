import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import SystemStatus from './pages/SystemStatus';
import Login from './pages/Login';
import Sidebar from './components/Sidebar';
import AuthProvider from './features/auth/AuthProvider';
import { useAuth } from './features/auth/context';
import Masters from './features/masters/Masters';
import ProductionMappings from './features/mappings/ProductionMappings';
import ConsumptionNorms from './features/rules/ConsumptionNorms';
import PlantWorkflow from './features/plant_workflow/PlantWorkflow';
import Inventory from './features/inventory/Inventory';
import AlertsCenter from './features/alerts/AlertsCenter';
import PurchaseApprovals from './features/purchasing/PurchaseApprovals';

function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      
      <div className="min-w-0 flex-1 flex flex-col">
        <header className="h-16 bg-white border-b border-gray-200 flex items-center px-6 shadow-sm">
          <h1 className="text-xl font-semibold text-brand-charcoal">KNL ERP Platform</h1>
        </header>

        <main className="flex-1 p-6 overflow-auto bg-brand-offwhite">
          {children}
        </main>
      </div>
    </div>
  );
}

function Application() {
  const { user } = useAuth();

  if (!user) {
    return <Login />;
  }

  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<div>Dashboard Placeholder</div>} />
          <Route path="/masters/*" element={<Masters />} />
          <Route path="/mappings/*" element={<ProductionMappings />} />
          <Route path="/rules/*" element={<ConsumptionNorms />} />
          <Route path="/prd" element={<div>PRD / Planning Placeholder</div>} />
          <Route path="/requirements" element={<div>Requirements Placeholder</div>} />
          <Route
            path="/plant-workflow/*"
            element={<PlantWorkflow currentUserId={user.id} />}
          />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/purchase/*" element={<PurchaseApprovals currentUserId={user.id} />} />
          <Route path="/alerts/*" element={<AlertsCenter />} />
          <Route path="/reports" element={<div>Reports Placeholder</div>} />
          <Route path="/admin" element={<div>Administration Placeholder</div>} />
          <Route path="/status" element={<SystemStatus />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}

export default function App() {
  return <AuthProvider><Application /></AuthProvider>;
}
