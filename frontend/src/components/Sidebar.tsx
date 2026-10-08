import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/context';
import { canOpen } from '../core/rbac';

const links = [
  ['/', 'Dashboard'], ['/masters', 'Masters'], ['/mappings', 'Production Mappings'],
  ['/rules', 'Consumption Norms'], ['/prd', 'PRD / Planning'], ['/requirements', 'Requirements'],
  ['/plant-workflow', 'Plant Workflow'], ['/inventory', 'Inventory'], ['/purchase', 'Purchase'],
  ['/purchase-orders', 'Purchase orders'], ['/grns', 'Goods receipts'], ['/alerts', 'Alerts'],
  ['/reports', 'Reports'], ['/admin', 'Administration'], ['/status', 'System Status'],
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  if (!user) return null;
  return <aside className="w-64 bg-brand-navy text-white flex flex-col select-none">
    <div className="p-4 text-lg font-bold border-b border-brand-steel/60">KNL Consumable ERP</div>
    <div className="px-4 py-2.5 bg-brand-steel/40 text-xs">
      <span>{user.username}</span> · <span>{user.is_super_admin ? 'SUPER ADMIN' : user.roles.join(', ') || 'USER'}</span>
    </div>
    <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
      {links.filter(([path]) => canOpen(user, path)).map(([path, label]) => <Link key={path} to={path}
        className={`block px-3 py-2 rounded text-xs font-medium ${location.pathname === path ? 'bg-brand-steel text-white' : 'text-gray-200 hover:bg-white/10'}`}>
        {label}
      </Link>)}
      <button onClick={logout} className="block px-3 py-2 text-xs text-red-400">Logout</button>
    </nav>
  </aside>;
}
