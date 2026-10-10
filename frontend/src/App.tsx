import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
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
import PRDPlanning from './features/prd/PRDPlanning';
import Requirements from './features/requirements/Requirements';
import UserManagement from './features/admin/UserManagement';

import { canOpen } from './core/rbac';

interface ProtectedRouteProps {
  isAllowed: boolean;
  children: React.ReactElement;
  redirectTo?: string;
}

function ProtectedRoute({ isAllowed, children }: ProtectedRouteProps) {
  if (!isAllowed) {
    return <p role="alert">You do not have permission to view this page. Select an available page from the menu.</p>;
  }
  return children;
}

function getPageTitle(pathname: string): string {
  if (pathname === '/' || pathname === '/dashboard') return 'Dashboard';
  if (pathname.startsWith('/prd')) return 'Production for sale';
  if (pathname.startsWith('/masters')) return 'Product master';
  if (pathname.startsWith('/rules')) return 'Consumption norms';
  if (pathname.startsWith('/mappings')) return 'Production mapping';
  if (pathname.startsWith('/requirements')) return 'Requirement';
  if (pathname.startsWith('/plant-workflow')) return 'Plant review';
  if (pathname.startsWith('/inventory')) return 'Inventory';
  if (pathname.startsWith('/purchase-orders')) return 'Purchase order';
  if (pathname.startsWith('/purchase')) return 'Purchase';
  if (pathname.startsWith('/grns')) return 'Goods receipts';
  if (pathname.startsWith('/alerts')) return 'Alerts';
  if (pathname.startsWith('/admin')) return 'Administration';
  if (pathname.startsWith('/status')) return 'System Status';
  return 'KNL ERP Platform';
}

function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const pageTitle = getPageTitle(location.pathname);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-vanilla-bg text-ink-text">
      <Sidebar />
      
      <div className="min-w-0 flex-1 flex flex-col bg-vanilla-bg">
        <header className="h-16 bg-vanilla-surface border-b border-ink-text/10 flex items-center justify-between px-6 shadow-2xs">
          <h1 className="text-xl font-semibold text-ink-text">{pageTitle}</h1>
          <span className="text-xs text-ink-text/60 font-medium tracking-wide">KNL ERP Platform</span>
        </header>

        <main className="flex-1 p-6 overflow-auto bg-vanilla-bg text-ink-text">
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

  const canMasters = canOpen(user, '/masters');
  const canMappings = canOpen(user, '/mappings');
  const canNorms = canOpen(user, '/rules');
  const canPrd = canOpen(user, '/prd');
  const canRequirements = canOpen(user, '/requirements');
  const canPlantWorkflow = canOpen(user, '/plant-workflow');
  const canInventory = canOpen(user, '/inventory');
  const canPurchase = canOpen(user, '/purchase');
  const canPurchaseOrders = canOpen(user, '/purchase-orders');
  const canGRNs = canOpen(user, '/grns');
  const canAlerts = canOpen(user, '/alerts');
  const isAdmin = canOpen(user, '/admin');

  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={
            <ProtectedRoute isAllowed={canOpen(user, '/')}><ExecutiveDashboard /></ProtectedRoute>
          } />
          <Route path="/dashboard" element={
            <ProtectedRoute isAllowed={canOpen(user, '/dashboard')}><ExecutiveDashboard /></ProtectedRoute>
          } />
          
          <Route path="/masters/*" element={
            <ProtectedRoute isAllowed={canMasters}><Masters /></ProtectedRoute>
          } />
          
          <Route path="/mappings/*" element={
            <ProtectedRoute isAllowed={canMappings}><ProductionMappings /></ProtectedRoute>
          } />
          
          <Route path="/rules/*" element={
            <ProtectedRoute isAllowed={canNorms}><ConsumptionNorms /></ProtectedRoute>
          } />
          
          <Route path="/prd" element={
            <ProtectedRoute isAllowed={canPrd}><PRDPlanning /></ProtectedRoute>
          } />
          
          <Route path="/requirements" element={
            <ProtectedRoute isAllowed={canRequirements}><Requirements /></ProtectedRoute>
          } />
          
          <Route path="/plant-workflow/*" element={
            <ProtectedRoute isAllowed={canPlantWorkflow}><PlantWorkflow currentUserId={user.id} /></ProtectedRoute>
          } />
          
          <Route path="/inventory" element={
            <ProtectedRoute isAllowed={canInventory}><Inventory /></ProtectedRoute>
          } />
          
          <Route path="/purchase/*" element={
            <ProtectedRoute isAllowed={canPurchase}><PurchaseApprovals currentUserId={user.id} /></ProtectedRoute>
          } />
          
          <Route path="/purchase-orders" element={
            <ProtectedRoute isAllowed={canPurchaseOrders}><PurchaseOrders /></ProtectedRoute>
          } />
          
          <Route path="/grns" element={
            <ProtectedRoute isAllowed={canGRNs}><GRNs /></ProtectedRoute>
          } />
          
          <Route path="/alerts/*" element={
            <ProtectedRoute isAllowed={canAlerts}><AlertsCenter /></ProtectedRoute>
          } />
          
          <Route path="/admin" element={
            <ProtectedRoute isAllowed={isAdmin}><UserManagement /></ProtectedRoute>
          } />
          
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
