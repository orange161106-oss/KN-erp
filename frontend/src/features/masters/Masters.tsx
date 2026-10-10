import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '../auth/context';
import MasterPage from './MasterPage';
import Products from './Products';
import { titles } from './types';
import type { Resource } from './types';
export default function Masters() {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canReadMasters = Boolean(isSuperAdmin || user?.masters_read);
  const resources: Resource[] = ['units', 'consumables', 'suppliers'];
  const allowed = resources.filter(resource => canReadMasters || user?.permissions?.includes(`masters.${resource}.read`));
  const forbidden = <p role="alert">You do not have permission to view these master records.</p>;
  const canReadProducts = Boolean(canReadMasters || user?.permissions?.includes('masters.read'));
  const tabClass = ({ isActive }: { isActive: boolean }) => `rounded-t px-4 py-2 ${isActive ? 'bg-brand-navy text-white font-semibold' : 'text-brand-navy border hover:bg-gray-100'}`;
  return <div className="space-y-6">
    <h1 className="text-2xl font-semibold text-brand-navy">Product master</h1>
    {canReadProducts && <p>Start with Products to review the Item IDs and Part Nos. from your PRD workbook. Upload planned quantities later in PRD / Planning.</p>}
    <nav aria-label="Master navigation" className="flex flex-wrap gap-3 border-b pb-3">{canReadProducts && <NavLink to="/masters/products" className={tabClass}>Products</NavLink>}{allowed.map(resource => <NavLink key={resource} to={`/masters/${resource}`} className={tabClass}>{titles[resource]}</NavLink>)}</nav>
    <Routes><Route index element={canReadProducts ? <Navigate to="products" replace /> : allowed.length ? <Navigate to={allowed[0]} replace /> : forbidden} />
      <Route path="products" element={canReadProducts ? <Products /> : forbidden} />
      {resources.map(resource => <Route key={resource} path={resource} element={allowed.includes(resource) ? <MasterPage key={resource} resource={resource} /> : forbidden} />)}
      <Route path="*" element={forbidden} />
    </Routes>
  </div>;
}
