'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { UserPlus, Loader2, AlertCircle } from 'lucide-react';

import { register as registerApi } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import BackgroundRippleEffect from '../../components/ui/BackgroundRippleEffect';
import CardSpotlight from '../../components/ui/CardSpotlight';

export default function RegisterPage() {
  const router = useRouter();
  const setSession = useAuth((s) => s.setSession);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await registerApi(email, username, password);
      setSession(res.access_token, res.user);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden">
      <BackgroundRippleEffect />

      <CardSpotlight className="relative z-10 w-full max-w-sm">
      <motion.form
        onSubmit={onSubmit}
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="w-full p-8"
      >
        <div className="flex flex-col items-center mb-6">
          <Link href="/" className="mb-3">
            <Image src="/logo.png" alt="ASTRA-IDE home" width={56} height={56} className="rounded-xl" priority />
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">Create your account</h1>
          <p className="text-sm text-muted mt-1">Free forever. No card required.</p>
        </div>

        {error && (
          <div role="alert"
               className="mb-4 px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30
                          text-rose-700 dark:text-rose-300 text-sm flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <label htmlFor="email" className="block text-xs font-medium text-muted mb-1">Email</label>
        <input
          id="email" type="email" required autoFocus autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="you@college.edu"
          className="input-base mb-4"
        />

        <label htmlFor="username" className="block text-xs font-medium text-muted mb-1">Username</label>
        <input
          id="username" type="text" required minLength={3} autoComplete="username"
          value={username} onChange={(e) => setUsername(e.target.value)}
          placeholder="jane.doe"
          className="input-base mb-4"
        />

        <label htmlFor="password" className="block text-xs font-medium text-muted mb-1">
          Password <span className="text-faint font-normal">(min 8 characters)</span>
        </label>
        <input
          id="password" type="password" required minLength={8} autoComplete="new-password"
          value={password} onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          className="input-base mb-6"
        />

        <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
          {loading
            ? <><Loader2 size={16} className="animate-spin" /> Creating account</>
            : <><UserPlus size={16} /> Sign up</>}
        </button>

        <p className="mt-6 text-sm text-muted text-center">
          Already have an account?{' '}
          <Link href="/login" className="text-astra-600 dark:text-astra-400 hover:underline">
            Log in
          </Link>
        </p>
      </motion.form>
      </CardSpotlight>
    </main>
  );
}
