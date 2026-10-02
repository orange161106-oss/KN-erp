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
  return <div className="min-h-screen flex items-center justify-center px-4">
    <form onSubmit={submit} className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-8 shadow-sm space-y-5">
      <h1 className="text-2xl font-semibold text-brand-navy">KN Consumable ERP</h1>
      <p className="text-sm text-gray-600">Sign in with your ERP account.</p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <label className="block text-sm font-medium">Username<input autoComplete="username" required value={username} maxLength={128} onChange={e => setUsername(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
      <label className="block text-sm font-medium">Password<input type="password" autoComplete="current-password" required value={password} maxLength={1024} onChange={e => setPassword(e.target.value)} className="mt-1 w-full border rounded p-2" /></label>
      <button disabled={pending} className="w-full bg-brand-navy text-white rounded p-2 disabled:opacity-50">{pending ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </div>;
}
