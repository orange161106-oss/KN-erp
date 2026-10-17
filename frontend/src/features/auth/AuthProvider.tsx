import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { apiClient, getAccessToken, setAccessToken, setUnauthorizedHandler } from '../../api/client';
import { AuthContext } from './context';
import type { CurrentUser } from './context';

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const generation = useRef(0);

  const logout = useCallback(async () => {
    generation.current += 1;
    const currentSession = sessionIdRef.current;
    if (getAccessToken()) {
      try {
        await apiClient.post('/api/v1/auth/logout', { session_id: currentSession });
      } catch {
        // Ignore network or logout errors during credential reset
      }
    }
    setAccessToken(null);
    setUser(null);
    sessionIdRef.current = null;
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => { setUnauthorizedHandler(null); setAccessToken(null); };
  }, [logout]);

  async function login(username: string, password: string) {
    const attempt = ++generation.current;
    setAccessToken(null);
    try {
      const response = await apiClient.post<{ access_token: string; user?: CurrentUser; session_id?: string }>('/api/v1/auth/login', { username, password });
      if (generation.current !== attempt) return;
      setAccessToken(response.access_token);
      if (response.session_id) {
        sessionIdRef.current = response.session_id;
      }
      let identity = response.user;
      if (!identity) {
        identity = await apiClient.get<CurrentUser>('/api/v1/auth/me');
      }
      if (generation.current === attempt) setUser(identity);
    } catch (error) { if (generation.current === attempt) logout(); throw error; }
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}
