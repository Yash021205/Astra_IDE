'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { LogIn, Loader2, AlertCircle } from 'lucide-react';

import AuroraBackground from '../../components/ui/AuroraBackground';
import Spotlight        from '../../components/ui/Spotlight';
import { login }        from '../../lib/api';
import { useAuth }      from '../../lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const setSession = useAuth((s) => s.setSession);
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(usernameOrEmail, password);
      setSession(res.access_token, res.user);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuroraBackground className="relative min-h-screen flex items-center justify-center px-4">
      <Spotlight className="left-0 top-0" fill="rgba(59,130,246,0.6)" />

      <motion.form
        onSubmit={onSubmit}
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-sm p-8 rounded-2xl border border-slate-800 bg-slate-900/70 backdrop-blur-xl shadow-2xl"
      >
        <div className="flex flex-col items-center mb-6">
          <Link href="/" className="mb-3">
            <Image src="/logo.png" alt="ASTRA-IDE" width={56} height={56} className="rounded-xl" priority />
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">Welcome back</h1>
          <p className="text-sm text-slate-400 mt-1">Log in to your ASTRA-IDE account.</p>
        </div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="mb-4 px-3 py-2 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-sm flex items-start gap-2"
          >
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </motion.div>
        )}

        <label htmlFor="username" className="block text-xs text-slate-400 mb-1">
          Username or email
        </label>
        <input
          id="username" type="text" required autoFocus
          value={usernameOrEmail}
          onChange={(e) => setUsernameOrEmail(e.target.value)}
          placeholder="jane.doe"
          className="w-full mb-4 px-3 py-2 rounded-lg bg-slate-800/80 border border-slate-700 focus:border-astra-500 focus:ring-2 focus:ring-astra-500/30 outline-none text-sm"
        />

        <label htmlFor="password" className="block text-xs text-slate-400 mb-1">Password</label>
        <input
          id="password" type="password" required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className="w-full mb-6 px-3 py-2 rounded-lg bg-slate-800/80 border border-slate-700 focus:border-astra-500 focus:ring-2 focus:ring-astra-500/30 outline-none text-sm"
        />

        <motion.button
          whileTap={{ scale: 0.97 }}
          type="submit" disabled={loading}
          className="w-full py-2.5 rounded-lg bg-gradient-to-r from-astra-600 to-astra-500 hover:from-astra-500 hover:to-astra-400 disabled:opacity-50 font-medium flex items-center justify-center gap-2 text-sm shadow-lg shadow-astra-600/30"
        >
          {loading
            ? <><Loader2 size={16} className="animate-spin" /> Logging in…</>
            : <><LogIn size={16} /> Log in</>}
        </motion.button>

        <p className="mt-6 text-sm text-slate-400 text-center">
          New here?{' '}
          <Link href="/register" className="text-astra-400 hover:text-astra-300 hover:underline">
            Create an account
          </Link>
        </p>
      </motion.form>
    </AuroraBackground>
  );
}
