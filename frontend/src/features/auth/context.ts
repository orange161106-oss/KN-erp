import { createContext, useContext } from 'react';
export interface CurrentUser { id: string; username: string; roles: string[]; permissions: string[]; is_super_admin?: boolean; }
interface AuthState { user: CurrentUser | null; login: (username: string, password: string) => Promise<void>; logout: () => void; }
export const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('Authentication provider is missing');
  return context;
}
