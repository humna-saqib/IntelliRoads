import React, { useState } from 'react';
import { loginApi } from '../services/api';
import Logo from '../components/ui/Logo';
import ThemeToggle from '../components/ui/ThemeToggle';

interface LoginPageProps {
  onLoginSuccess: (token: string) => void;
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await loginApi(username, password);
      localStorage.setItem('intelliroads_token', res.access_token);
      onLoginSuccess(res.access_token);
    } catch (err: unknown) {
      setError(err instanceof Error && err.message ? err.message : 'Sign-in failed. Check your username and password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-page p-4 text-ink">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-[360px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo size={28} />
          <h1 className="mt-4 text-xl font-medium tracking-tight">Sign in to IntelliRoads</h1>
          <p className="mt-1 text-[13px] text-muted">Adaptive traffic signal control</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-line bg-surface p-5">
          {error && (
            <p role="alert" className="rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">
              {error}
            </p>
          )}

          <div>
            <label htmlFor="username" className="field-label">Username</label>
            <input id="username" type="text" required autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} className="input h-9" />
          </div>

          <div>
            <label htmlFor="password" className="field-label">Password</label>
            <input id="password" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="input h-9" />
          </div>

          <button type="submit" disabled={isSubmitting} className="btn btn-primary h-9 w-full">
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-faint">Final year project demo</p>
      </div>
    </div>
  );
}
