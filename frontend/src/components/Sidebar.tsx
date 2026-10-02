import { Link } from 'react-router-dom';
import { useAuth } from '../features/auth/context';

export default function Sidebar() {
  const { user, logout } = useAuth();
  if (!user) return null;
  const canSee = (allowedRoles: string[]) => user.roles.includes('ADMIN') || allowedRoles.some(role => user.roles.includes(role));
  const canReadMasters = ['units', 'consumables', 'suppliers'].some(resource => user.permissions.includes(`masters.${resource}.read`));

  return (
    <aside className="w-64 bg-brand-navy text-white flex flex-col">
      <div className="p-4 text-lg font-bold border-b border-brand-steel">
        KN Consumable ERP
      </div>
      
      <div className="p-3 bg-brand-steel text-xs font-semibold uppercase tracking-wider">
        {user.username}
      </div>

      <nav className="flex-1 p-4 space-y-2 flex flex-col overflow-y-auto">
        <Link to="/" className="block hover:text-brand-steel transition-colors">Dashboard</Link>
        
        {canReadMasters && (
          <Link to="/masters" className="block hover:text-brand-steel transition-colors">Masters</Link>
        )}

        {(canReadMasters || canSee(['PLANNER'])) && (
          <Link to="/mappings" className="block hover:text-brand-steel transition-colors">Production Mappings</Link>
        )}

        {(canReadMasters || canSee(['PLANNER'])) && (
          <Link to="/rules" className="block hover:text-brand-steel transition-colors">Consumption Norms</Link>
        )}
        
        {canSee(['PLANNER']) && (
          <Link to="/prd" className="block hover:text-brand-steel transition-colors">PRD / Planning</Link>
        )}
        
        {canSee(['PLANT_INCHARGE']) && (
          <Link to="/requirements" className="block hover:text-brand-steel transition-colors">Requirements</Link>
        )}
        
        {canSee(['PLANT_INCHARGE']) && (
          <Link to="/plant-workflow" className="block hover:text-brand-steel transition-colors">Plant Workflow</Link>
        )}
        
        {canSee(['STORE']) && (
          <Link to="/inventory" className="block hover:text-brand-steel transition-colors">Inventory</Link>
        )}
        
        {canSee(['PURCHASE']) && (
          <Link to="/purchase" className="block hover:text-brand-steel transition-colors">Purchase</Link>
        )}
        
        {canSee(['STORE', 'PLANT_INCHARGE']) && (
          <Link to="/alerts" className="block hover:text-brand-steel transition-colors">Alerts</Link>
        )}
        
        {canSee(['PLANNER']) && (
          <Link to="/reports" className="block hover:text-brand-steel transition-colors">Reports</Link>
        )}

        <div className="mt-auto pt-4 border-t border-brand-steel flex flex-col space-y-2">
          {user.roles.includes('ADMIN') && (
             <Link to="/admin" className="block hover:text-brand-steel transition-colors">Administration</Link>
          )}
          <Link to="/status" className="block hover:text-brand-steel transition-colors text-sm text-gray-300">System Status</Link>
          <button 
            onClick={logout}
            className="text-left text-red-400 hover:text-red-300 transition-colors text-sm mt-4 font-semibold"
          >
            Logout
          </button>
        </div>
      </nav>
    </aside>
  );
}
