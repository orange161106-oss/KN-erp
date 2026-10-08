import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '../auth/context';
import MasterPage from './MasterPage';
import { titles } from './types';
import type { Resource } from './types';
export default function Masters() {
  const { user } = useAuth();
  const canView = Boolean(user?.is_super_admin || user?.roles.includes('ADMIN') || user?.can_access_masters);
  const resources: Resource[] = ['units', 'consumables', 'suppliers'];
  const allowed = canView ? resources : [];
  const forbidden = <p role="alert">You do not have permission to view these master records.</p>;
  return <div className="space-y-6">
    <h1 className="text-2xl font-semibold text-brand-navy">Master data</h1>
    <nav aria-label="Master navigation" className="flex gap-5 border-b pb-3">{allowed.map(resource => <Link key={resource} to={`/masters/${resource}`} className="text-brand-navy underline">{titles[resource]}</Link>)}</nav>
    <Routes><Route index element={allowed.length ? <Navigate to={allowed[0]} replace /> : forbidden} />
      {resources.map(resource => <Route key={resource} path={resource} element={allowed.includes(resource) ? <MasterPage key={resource} resource={resource} /> : forbidden} />)}
      <Route path="*" element={forbidden} />
    </Routes>
  </div>;
}
