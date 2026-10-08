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

interface ProtectedRouteProps {
  isAllowed: boolean;
  children: React.ReactElement;
  redirectTo?: string;
}

function ProtectedRoute({ isAllowed, children, redirectTo = '/dashboard' }: ProtectedRouteProps) {
  if (!isAllowed) {
    return <Navigate to={redirectTo} replace />;
  }
  return children;
}

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

  const isAdmin = Boolean(user.is_super_admin || user.roles.includes('ADMIN'));

  const hasPlantAccess = Boolean(
    user.can_access_plant_1 ||
    user.can_access_plant_2 ||
    user.can_access_plant_3 ||
    user.can_access_plant_4 ||
    user.can_access_plant_5
  );

  const canMasters = isAdmin || Boolean(user.can_access_masters);
  const canMappings = isAdmin || Boolean(user.can_access_production_mappings);
  const canNorms = isAdmin || Boolean(user.can_access_consumption_norms);
  const canPrd = isAdmin || Boolean(user.can_access_prd_planning);
  const canRequirements = isAdmin || Boolean(user.can_access_requirements);
  const canPlantWorkflow = isAdmin || Boolean(user.can_access_plant_workflow) || hasPlantAccess;
  const canInventory = isAdmin || Boolean(user.can_access_inventory);
  const canPurchase = isAdmin || Boolean(user.can_access_purchase);
  const canPurchaseOrders = isAdmin || Boolean(user.can_access_purchase_orders);
  const canGRNs = isAdmin || Boolean(user.can_access_goods_receipts);
  const canReports = isAdmin || Boolean(user.can_access_inventory || user.can_access_purchase || user.can_access_requirements);

  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<ExecutiveDashboard />} />
          <Route path="/dashboard" element={<ExecutiveDashboard />} />
          
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
            <ProtectedRoute isAllowed={canReports}><AlertsCenter /></ProtectedRoute>
          } />
          
          <Route path="/reports" element={
            <ProtectedRoute isAllowed={canReports}><InventoryPurchaseReports /></ProtectedRoute>
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
