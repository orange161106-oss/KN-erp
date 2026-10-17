import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import AppShell from './components/AppShell';
import PageBoundary from './components/PageBoundary';
import AuthProvider from './features/auth/AuthProvider';
import { useAuth } from './features/auth/context';
const SystemStatus = lazy(() => import('./pages/SystemStatus'));
const Masters = lazy(() => import('./features/masters/Masters'));
const ProductionMappings = lazy(() => import('./features/mappings/ProductionMappings'));
const ConsumptionNorms = lazy(() => import('./features/rules/ConsumptionNorms'));
const Inventory = lazy(() => import('./features/inventory/Inventory'));
const StockStatementWorkspace = lazy(() => import('./features/inventory/StockStatementWorkspace'));
const StockManagementWorkspace = lazy(() => import('./features/inventory/StockManagementWorkspace'));
const AlertsCenter = lazy(() => import('./features/alerts/AlertsCenter'));
const PurchaseApprovals = lazy(() => import('./features/purchasing/PurchaseApprovals'));
const PurchaseOrders = lazy(() => import('./features/purchasing/PurchaseOrders'));
const GRNs = lazy(() => import('./features/purchasing/GRNs'));
const ExecutiveDashboard = lazy(() => import('./features/dashboard/ExecutiveDashboard'));
const PRDPlanning = lazy(() => import('./features/prd/PRDPlanning'));
const Requirements = lazy(() => import('./features/requirements/Requirements'));
const UserManagement = lazy(() => import('./features/admin/UserManagement'));
const Reports = lazy(() => import('./features/reports/Reports'));

import { canOpen, isSuperAdmin } from './core/rbac';

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
  const canInventory = canOpen(user, '/inventory');
  const canPurchase = canOpen(user, '/purchase');
  const canPurchaseOrders = canOpen(user, '/purchase-orders');
  const canGRNs = canOpen(user, '/grns');
  const canAlerts = canOpen(user, '/alerts');
  const canReports = canOpen(user, '/reports') || isSuperAdmin(user);
  const isAdmin = canOpen(user, '/admin');

  return (
    <BrowserRouter>
      <AppShell>
        <PageBoundary>
        <Suspense fallback={<p role="status" className="p-4">Loading page…</p>}>
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
          
          <Route path="/plant-workflow" element={<Navigate to="/requirements" replace />} />
          <Route path="/plant-workflow/*" element={<Navigate to="/requirements" replace />} />
          
          <Route path="/inventory" element={
            <ProtectedRoute isAllowed={canInventory}><Inventory /></ProtectedRoute>
          } />
          <Route path="/inventory/statement" element={
            <ProtectedRoute isAllowed={canInventory}><StockStatementWorkspace /></ProtectedRoute>
          } />
          <Route path="/inventory/management" element={
            <ProtectedRoute isAllowed={canInventory}><StockManagementWorkspace /></ProtectedRoute>
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
          
          <Route path="/reports" element={
            <ProtectedRoute isAllowed={canReports}><Reports /></ProtectedRoute>
          } />
          
          <Route path="/admin" element={
            <ProtectedRoute isAllowed={isAdmin}><UserManagement /></ProtectedRoute>
          } />
          
          <Route path="/status" element={
            <ProtectedRoute isAllowed={isAdmin}><SystemStatus /></ProtectedRoute>
          } />
          <Route path="/system-status" element={
            <ProtectedRoute isAllowed={isAdmin}><SystemStatus /></ProtectedRoute>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        </PageBoundary>
      </AppShell>
    </BrowserRouter>
  );
}

export default function App() {
  return <AuthProvider><Application /></AuthProvider>;
}
import { lazy, Suspense } from 'react';
