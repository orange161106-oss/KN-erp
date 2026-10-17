import { useState } from 'react';
import { useAuth } from '../features/auth/context';

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (isLoading) return;
    setIsLoading(true);
    setError('');

    try {
      await login(username, password);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Sign-in failed.');
      setPassword('');
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-erp-vanilla text-erp-chocolate">
      <form
        onSubmit={submit}
        aria-busy={isLoading}
        className="relative w-full max-w-md overflow-hidden rounded-xl border border-ink-text/10 bg-white p-8 shadow-md space-y-5"
      >
        {isLoading && (
          <div className="absolute top-0 left-0 right-0 h-1 bg-burnt-orange/20 overflow-hidden">
            <div className="h-full bg-burnt-orange animate-pulse w-full" />
          </div>
        )}

        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-ink-text flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-burnt-orange inline-block" />
            KNL Consumable ERP
          </h1>
          <p className="text-sm text-ink-text/70">Sign in with your ERP account.</p>
        </div>

        {error && (
          <div
            role="alert"
            className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2"
          >
            <span>{error}</span>
          </div>
        )}

        <label className="block text-sm font-medium text-ink-text">
          Username
          <input
            autoComplete="username"
            required
            disabled={isLoading}
            value={username}
            maxLength={128}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full border border-ink-text/15 rounded p-2 focus:ring-1 focus:ring-burnt-orange focus:outline-none disabled:bg-ink-text/5 disabled:cursor-not-allowed"
          />
        </label>

        <label className="block text-sm font-medium text-ink-text">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            disabled={isLoading}
            value={password}
            maxLength={1024}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full border border-ink-text/15 rounded p-2 focus:ring-1 focus:ring-burnt-orange focus:outline-none disabled:bg-ink-text/5 disabled:cursor-not-allowed"
          />
        </label>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full relative flex items-center justify-center gap-2 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded p-2.5 font-medium shadow-xs disabled:opacity-60 disabled:cursor-not-allowed transition-all"
        >
          {isLoading ? (
            <div className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin h-4 w-4 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Signing in…</span>
            </div>
          ) : (
            <span>Sign in</span>
          )}
        </button>
      </form>
    </div>
  );
}
