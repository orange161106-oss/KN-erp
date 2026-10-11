import { Route, Routes } from 'react-router-dom';
import { useAuth } from '../auth/context';
import MasterPage from './MasterPage';
import Products from './Products';
import type { Resource } from './types';

export default function Masters() {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canReadMasters = Boolean(isSuperAdmin || user?.masters_read);
  const resources: Resource[] = ['units', 'consumables', 'suppliers'];
  const allowed = resources.filter(resource => canReadMasters || user?.permissions?.includes(`masters.${resource}.read`));
  const forbidden = <p role="alert">You do not have permission to view these master records.</p>;
  const canReadProducts = Boolean(
    canReadMasters ||
    user?.permissions?.includes('masters.read') ||
    user?.permissions?.some((p: string) => p.startsWith('masters.'))
  );

  return (
    <Routes>
      <Route index element={canReadProducts ? <Products /> : forbidden} />
      <Route path="products" element={canReadProducts ? <Products /> : forbidden} />
      {resources.map(resource => (
        <Route
          key={resource}
          path={resource}
          element={allowed.includes(resource) ? <MasterPage key={resource} resource={resource} /> : forbidden}
        />
      ))}
      <Route path="*" element={forbidden} />
    </Routes>
  );
}
