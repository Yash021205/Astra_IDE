'use client';
import { Suspense, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { fetchMeWithToken } from '../../../lib/api';
import { useAuth } from '../../../lib/auth';

/**
 * Landing page for the Google OAuth round-trip. The backend redirects here with
 * ?token=<jwt> after a successful sign-in; we load the user with that token,
 * persist the session, and continue to the dashboard.
 */
function OAuthCallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useAuth((s) => s.setSession);
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const token = params.get('token');
    if (!token) {
      router.replace('/login?error=oauth_failed');
      return;
    }
    fetchMeWithToken(token)
      .then((user) => {
        setSession(token, user);
        router.replace('/dashboard');
      })
      .catch(() => router.replace('/login?error=oauth_failed'));
  }, [params, router, setSession]);

  return (
    <main className="min-h-screen flex items-center justify-center text-slate-400 gap-2">
      <Loader2 size={18} className="animate-spin" /> Signing you in…
    </main>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={<main className="min-h-screen flex items-center justify-center text-slate-400">Signing you in…</main>}>
      <OAuthCallbackInner />
    </Suspense>
  );
}
