import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { apiClient, setAccessToken, setUnauthorizedHandler } from '../../api/client';
import { AuthContext } from './context';
import type { CurrentUser } from './context';
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const generation = useRef(0);
  const logout = useCallback(() => { generation.current += 1; setAccessToken(null); setUser(null); }, []);
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => { setUnauthorizedHandler(null); setAccessToken(null); };
  }, [logout]);
  async function login(username: string, password: string) {
    const attempt = ++generation.current;
    setAccessToken(null);
    try {
      const token = await apiClient.post<{ access_token: string }>('/api/v1/auth/login', { username, password });
      if (generation.current !== attempt) return;
      setAccessToken(token.access_token);
      const identity = await apiClient.get<CurrentUser>('/api/v1/auth/me');
      if (generation.current === attempt) setUser(identity);
    } catch (error) { if (generation.current === attempt) logout(); throw error; }
  }
  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}
