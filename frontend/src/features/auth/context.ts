import { createContext, useContext } from 'react';
import type { UserPermissionFlags } from '../../api/users';
export interface CurrentUser extends Partial<UserPermissionFlags> { plant_ids?: string[]; id: string; username: string; roles: string[]; permissions: string[]; is_super_admin?: boolean; }
interface AuthState { user: CurrentUser | null; login: (username: string, password: string) => Promise<void>; logout: () => void; }
export const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('Authentication provider is missing');
  return context;
}
