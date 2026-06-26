'use client';
import { useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { Camera, ChevronDown, Loader2, LogOut, User } from 'lucide-react';

import { useAuth } from '../lib/auth';
import { uploadToImgbb, updateProfile } from '../lib/api';
import { toast } from '../lib/toast';
import ThemeToggle from './ThemeToggle';
import { Avatar } from './AvatarInline';
import Tooltip from './ui/Tooltip';
import { cn } from '../lib/utils';

const NAV = [
  { href: '/dashboard',  label: 'Dashboard' },
  { href: '/clusters',   label: 'Clusters' },
  { href: '/benchmarks', label: 'Benchmarks' },
  { href: '/platform',   label: 'Platform' },
];

export default function Navbar({ variant = 'default' }: { variant?: 'default' | 'hero' }) {
  const pathname = usePathname();
  const { token, user, hydrated, setUser, clearSession } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const loggedIn = hydrated && !!token && !!user;

  const isHero = variant === 'hero';

  async function onAvatarPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('Image too large', 'Max 5 MB'); return; }
    setUploading(true);
    try {
      const url = await uploadToImgbb(file);
      const updated = await updateProfile(url);
      setUser(updated);
      toast.success('Profile photo updated');
    } catch (err: any) {
      toast.error('Upload failed', err?.message || 'Try a different image');
    } finally { setUploading(false); }
  }

  return (
    <nav className={cn(
      isHero ? 'fixed top-0 inset-x-0 z-50 px-4 sm:px-6 py-3' : 'sticky top-0 z-40 w-full border-b border-edge',
    )}>
      <div className={cn(
        'flex items-center gap-4',
        isHero
          ? 'mx-auto max-w-7xl rounded-2xl border border-amber-200/70 dark:border-white/10 bg-amber-50/75 dark:bg-slate-900/45 backdrop-blur-xl px-5 py-2.5 shadow-lg shadow-amber-900/5'
          : 'mx-auto max-w-6xl px-4 sm:px-6 h-14 bg-surface/80 backdrop-blur',
      )}>
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <Image src="/logo.png" alt="ASTRA-IDE" width={30} height={30} priority className="rounded-lg ring-1 ring-edge" />
          <span className="text-[15px] font-bold tracking-tight text-ink">
            ASTRA-<span className="text-astra-700 dark:text-astra-300">IDE</span>
          </span>
        </Link>

        {loggedIn && (
          <div className="hidden md:flex items-center gap-1 ml-2" role="navigation" aria-label="Primary">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href}
                    aria-current={pathname?.startsWith(n.href) ? 'page' : undefined}
                    className={cn(
                      isHero
                        ? (pathname?.startsWith(n.href)
                            ? 'px-3 py-1.5 rounded-lg text-sm font-medium text-ink bg-ink/10 dark:text-white dark:bg-white/10'
                            : 'px-3 py-1.5 rounded-lg text-sm text-muted hover:text-ink hover:bg-ink/5 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10')
                        : (pathname?.startsWith(n.href)
                            ? 'nav-pill-active'
                            : 'nav-pill'),
                    )}>
                {n.label}
              </Link>
            ))}
          </div>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle className={isHero ? '!text-muted hover:!text-ink hover:!bg-ink/5 dark:!text-white/70 dark:hover:!text-white dark:hover:!bg-white/10' : ''} />

          {!loggedIn ? (
            <>
              <Link href="/login"
                    className={cn('px-3 py-1.5 text-sm rounded-lg transition-colors',
                      isHero ? 'text-muted hover:text-ink hover:bg-ink/5 dark:text-white/80 dark:hover:text-white dark:hover:bg-white/10' : 'nav-pill')}>
                Log in
              </Link>
              <Link href="/register"
                    className="px-4 py-1.5 text-sm rounded-lg bg-astra-700 dark:bg-astra-500 text-white dark:text-astra-900 font-medium hover:bg-astra-800 dark:hover:bg-astra-400 transition-colors">
                Sign up
              </Link>
            </>
          ) : (
            <div className="relative">
              <input ref={fileRef} type="file" accept="image/*" className="hidden"
                     aria-label="Upload profile photo" onChange={onAvatarPick} />
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                aria-haspopup="menu" aria-expanded={menuOpen}
                className={cn('flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-sm transition-colors',
                  isHero ? 'text-muted hover:text-ink hover:bg-ink/5 dark:text-white/80 dark:hover:text-white dark:hover:bg-white/10' : 'btn-ghost pl-2 pr-1.5')}>
                <Avatar user={user} size={24} />
                <span className="hidden sm:inline max-w-[8rem] truncate">{user?.username}</span>
                <ChevronDown size={14} />
              </button>

              {menuOpen && (
                <>
                  <button type="button" tabIndex={-1} aria-label="Close menu"
                          className="fixed inset-0 z-40 cursor-default"
                          onClick={() => setMenuOpen(false)} />
                  <div role="menu"
                       className="absolute right-0 top-full mt-1.5 z-50 w-56 p-1.5 shadow-pop card">
                    <div className="px-2.5 py-2 border-b border-edge mb-1 flex items-center gap-2.5">
                      <Avatar user={user} size={36} />
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{user?.username}</div>
                        <div className="text-xs text-faint truncate">{user?.email}</div>
                      </div>
                    </div>
                    <button type="button" role="menuitem" disabled={uploading}
                            onClick={() => fileRef.current?.click()}
                            className="w-full flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm disabled:opacity-50 hover:bg-raised">
                      {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
                      {uploading ? 'Uploading...' : (user?.avatar_url ? 'Change photo' : 'Add profile photo')}
                    </button>
                    <div className="px-2.5 py-1.5 flex items-center justify-between text-xs text-muted">
                      <span className="inline-flex items-center gap-1.5"><User size={12} /> Trust score</span>
                      <span className="font-mono">{user?.trust_score?.toFixed(2)}</span>
                    </div>
                    {/* GitHub connection status */}
                    {user?.github_login ? (
                      <div className="px-2.5 py-1.5 flex items-center justify-between text-xs">
                        <span className="inline-flex items-center gap-1.5 text-muted">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                          </svg>
                          GitHub
                        </span>
                        <span className="font-medium text-emerald-600 dark:text-emerald-400 truncate max-w-[100px]">
                          {user.github_login}
                        </span>
                      </div>
                    ) : (
                      <a href="/api/auth/github/login"
                        className="w-full flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-raised transition-colors">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                        </svg>
                        Connect GitHub
                      </a>
                    )}
                    <button
                      type="button" role="menuitem"
                      onClick={() => { clearSession(); window.location.assign('/'); }}
                      className="w-full mt-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm
                                 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10"
                    >
                      <LogOut size={14} /> Log out
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {loggedIn && (
        <div className={cn('md:hidden flex items-center gap-1 overflow-x-auto',
          isHero ? 'mx-auto max-w-7xl px-5 py-1.5' : 'mx-auto max-w-6xl px-4 pb-2')}>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
                  className={cn('whitespace-nowrap text-sm px-3 py-1.5 rounded-lg',
                    isHero
                      ? (pathname?.startsWith(n.href) ? 'text-ink bg-ink/10 font-medium dark:text-white dark:bg-white/10' : 'text-muted dark:text-white/70')
                      : (pathname?.startsWith(n.href) ? 'nav-pill-active' : 'nav-pill'))}>
              {n.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}
