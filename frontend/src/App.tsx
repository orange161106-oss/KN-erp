import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import SystemStatus from './pages/SystemStatus';
import Login from './pages/Login';
import AppShell from './components/AppShell';
import AuthProvider from './features/auth/AuthProvider';
import { useAuth } from './features/auth/context';
import Masters from './features/masters/Masters';
import ProductionMappings from './features/mappings/ProductionMappings';
import ConsumptionNorms from './features/rules/ConsumptionNorms';
import PlantWorkflow from './features/plant_workflow/PlantWorkflow';
import Inventory from './features/inventory/Inventory';
import StockStatementWorkspace from './features/inventory/StockStatementWorkspace';
import StockManagementWorkspace from './features/inventory/StockManagementWorkspace';
import AlertsCenter from './features/alerts/AlertsCenter';
import PurchaseApprovals from './features/purchasing/PurchaseApprovals';
import PurchaseOrders from './features/purchasing/PurchaseOrders';
import GRNs from './features/purchasing/GRNs';
import ExecutiveDashboard from './features/dashboard/ExecutiveDashboard';
import PRDPlanning from './features/prd/PRDPlanning';
import Requirements from './features/requirements/Requirements';
import UserManagement from './features/admin/UserManagement';
import Reports from './features/reports/Reports';

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
  const canPlantWorkflow = canOpen(user, '/plant-workflow');
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
      </AppShell>
    </BrowserRouter>
  );
}

export default function App() {
  return <AuthProvider><Application /></AuthProvider>;
}
