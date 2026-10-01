import { Link } from 'react-router-dom';
import type { Role } from '../pages/Login';

interface SidebarProps {
  role: Role;
  onLogout: () => void;
}

export default function Sidebar({ role, onLogout }: SidebarProps) {
  const canSee = (allowedRoles: Role[]) => role === 'ADMIN' || allowedRoles.includes(role);

  return (
    <aside className="w-64 bg-brand-navy text-white flex flex-col">
      <div className="p-4 text-lg font-bold border-b border-brand-steel">
        KN Consumable ERP
      </div>
      
      <div className="p-3 bg-brand-steel text-xs font-semibold uppercase tracking-wider">
        Active Role: {role?.replace('_', ' ')}
      </div>

      <nav className="flex-1 p-4 space-y-2 flex flex-col overflow-y-auto">
        <Link to="/" className="block hover:text-brand-steel transition-colors">Dashboard</Link>
        
        {canSee(['PURCHASE']) && (
          <Link to="/masters" className="block hover:text-brand-steel transition-colors">Masters</Link>
        )}
        
        {canSee(['PLANNER']) && (
          <Link to="/prd" className="block hover:text-brand-steel transition-colors">PRD / Planning</Link>
        )}
        
        {canSee(['PLANT_INCHARGE']) && (
          <Link to="/requirements" className="block hover:text-brand-steel transition-colors">Requirements</Link>
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
          {role === 'ADMIN' && (
             <Link to="/admin" className="block hover:text-brand-steel transition-colors">Administration</Link>
          )}
          <Link to="/status" className="block hover:text-brand-steel transition-colors text-sm text-gray-300">System Status</Link>
          <button 
            onClick={onLogout}
            className="text-left text-red-400 hover:text-red-300 transition-colors text-sm mt-4 font-semibold"
          >
            Logout
          </button>
        </div>
      </nav>
    </aside>
  );
}