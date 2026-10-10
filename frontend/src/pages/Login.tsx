import { useState } from 'react';
import { useAuth } from '../features/auth/context';
export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setPending(true); setError('');
    try { await login(username, password); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Sign-in failed.'); }
    finally { setPassword(''); setPending(false); }
  }
  return <div className="min-h-screen flex items-center justify-center px-4 bg-vanilla-bg">
    <form onSubmit={submit} className="w-full max-w-md rounded-xl border border-ink-text/10 bg-white p-8 shadow-md space-y-5">
      <h1 className="text-2xl font-bold text-ink-text flex items-center gap-2">
        <span className="w-3 h-3 rounded-full bg-burnt-orange inline-block" />
        KNL Consumable ERP
      </h1>
      <p className="text-sm text-ink-text/70">Sign in with your ERP account.</p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <label className="block text-sm font-medium text-ink-text">Username<input autoComplete="username" required value={username} maxLength={128} onChange={e => setUsername(e.target.value)} className="mt-1 w-full border border-ink-text/15 rounded p-2 focus:ring-1 focus:ring-burnt-orange focus:outline-none" /></label>
      <label className="block text-sm font-medium text-ink-text">Password<input type="password" autoComplete="current-password" required value={password} maxLength={1024} onChange={e => setPassword(e.target.value)} className="mt-1 w-full border border-ink-text/15 rounded p-2 focus:ring-1 focus:ring-burnt-orange focus:outline-none" /></label>
      <button disabled={pending} className="w-full bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded p-2.5 font-medium shadow-xs disabled:opacity-50 transition-colors">{pending ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </div>;
}
