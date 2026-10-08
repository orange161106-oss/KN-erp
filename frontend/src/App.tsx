import { canOpen } from './core/rbac';
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
import PurchaseOrders from './features/purchasing/PurchaseOrders';
import GRNs from './features/purchasing/GRNs';
import ExecutiveDashboard from './features/dashboard/ExecutiveDashboard';
import InventoryPurchaseReports from './features/reports/InventoryPurchaseReports';
import PRDPlanning from './features/prd/PRDPlanning';
import Requirements from './features/requirements/Requirements';
import UserManagement from './features/admin/UserManagement';

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

  const allowed = (path: string, page: React.ReactNode) => canOpen(user, path) ? page : <p role="alert">You do not have permission to view this page. Select an available page from the menu.</p>;

  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={allowed('/', <ExecutiveDashboard />)} />
          <Route path="/dashboard" element={allowed('/dashboard', <ExecutiveDashboard />)} />
          <Route path="/masters/*" element={allowed('/masters', <Masters />)} />
          <Route path="/mappings/*" element={allowed('/mappings', <ProductionMappings />)} />
          <Route path="/rules/*" element={allowed('/rules', <ConsumptionNorms />)} />
          <Route path="/prd" element={allowed('/prd', <PRDPlanning />)} />
          <Route path="/requirements" element={allowed('/requirements', <Requirements />)} />
          <Route
            path="/plant-workflow/*"
            element={allowed('/plant-workflow', <PlantWorkflow currentUserId={user.id} />)}
          />
          <Route path="/inventory" element={allowed('/inventory', <Inventory />)} />
          <Route path="/purchase/*" element={allowed('/purchase', <PurchaseApprovals currentUserId={user.id} />)} />
          <Route path="/purchase-orders" element={allowed('/purchase-orders', <PurchaseOrders />)} />
          <Route path="/grns" element={allowed('/grns', <GRNs />)} />
          <Route path="/alerts/*" element={allowed('/alerts', <AlertsCenter />)} />
          <Route path="/reports" element={allowed('/reports', <InventoryPurchaseReports />)} />
          <Route path="/admin" element={allowed('/admin', <UserManagement />)} />
          <Route path="/status" element={allowed('/status', <SystemStatus />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}

export default function App() {
  return <AuthProvider><Application /></AuthProvider>;
}
