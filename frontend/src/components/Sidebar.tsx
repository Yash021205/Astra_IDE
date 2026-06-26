'use client';
// Collapsible left sidebar for authenticated pages. Collapsed = icon rail (64px);
// expanded = 240px with labels. Width animates; labels fade in. State persists in
// localStorage. Theme toggle + account menu live at the bottom.

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LayoutDashboard, Boxes, BarChart3, LayoutGrid as PlatformIcon, Activity, Container,
  PanelLeftClose, PanelLeftOpen, Camera, LogOut, User, Loader2, Shield, Github,
} from 'lucide-react';

import { useAuth } from '../lib/auth';
import { uploadToImgbb, updateProfile } from '../lib/api';
import { toast } from '../lib/toast';
import ThemeToggle from './ThemeToggle';
import Tooltip from './ui/Tooltip';
import { Avatar } from './AvatarInline';
import { cn } from '../lib/utils';
import GitHubPanel from './GitHubPanel';

const NAV = [
  { href: '/dashboard',     label: 'Dashboard',     icon: LayoutDashboard },
  { href: '/pods',          label: 'Containers',    icon: Container },
  { href: '/clusters',      label: 'Clusters',      icon: Boxes },
  { href: '/benchmarks',    label: 'Benchmarks',    icon: BarChart3 },
  { href: '/observability', label: 'Observability', icon: Activity },
  { href: '/platform',      label: 'Platform',      icon: PlatformIcon },
];

const STORAGE_KEY = 'astra-sidebar-open';

export default function Sidebar() {
  const pathname = usePathname();
  const { user, setUser, clearSession } = useAuth();
  const [open, setOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved !== null ? saved === '1' : true;
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [ghPanelOpen, setGhPanelOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  function toggle() {
    setOpen((v) => { localStorage.setItem(STORAGE_KEY, v ? '0' : '1'); return !v; });
  }

  const isAdmin = (user as any)?.is_admin;
  const isGhConnected = !!user?.github_login;

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
    <motion.aside
      initial={false}
      animate={{ width: open ? 240 : 68 }}
      transition={{ type: 'spring', stiffness: 320, damping: 34 }}
      className="glass sticky top-0 h-screen shrink-0 border-r border-edge
                 flex flex-col z-40 overflow-visible"
    >
      {/* Brand + collapse toggle */}
      <div className="h-14 flex items-center gap-2 px-3 border-b border-edge shrink-0">
        <Link href="/" className="flex items-center gap-2 min-w-0">
          <Image src="/logo.png" alt="ASTRA-IDE" width={30} height={30} priority className="rounded-lg shrink-0 ring-1 ring-edge" />
          <AnimatePresence>
            {open && (
              <motion.span
                initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -6 }}
                className="text-[15px] font-bold tracking-tight whitespace-nowrap">
                ASTRA-<span className="text-astra-600 dark:text-astra-400">IDE</span>
              </motion.span>
            )}
          </AnimatePresence>
        </Link>
        {open && (
          <Tooltip content="Collapse" side="right">
            <button type="button" onClick={toggle} aria-label="Collapse sidebar"
                    className="ml-auto btn-ghost p-1.5"><PanelLeftClose size={16} /></button>
          </Tooltip>
        )}
      </div>

      {/* Expand button when collapsed */}
      {!open && (
        <div className="px-3 py-2 border-b border-edge">
          <Tooltip content="Expand" side="right">
            <button type="button" onClick={toggle} aria-label="Expand sidebar"
                    className="btn-ghost p-2 w-full justify-center"><PanelLeftOpen size={16} /></button>
          </Tooltip>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2.5 py-3 space-y-1 overflow-y-auto" aria-label="Primary">
        {NAV.map((n) => {
          const active = pathname?.startsWith(n.href);
          const Icon = n.icon;
          const item = (
            <Link key={n.href} href={n.href}
                  aria-current={active ? 'page' : undefined}
                  className={cn('flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors relative',
                    active ? 'bg-astra-500/10 text-astra-600 dark:text-astra-300 font-medium'
                           : 'text-muted hover:bg-raised hover:text-ink',
                    !open && 'justify-center')}>
              {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-astra-500" aria-hidden="true" />}
              <Icon size={18} className="shrink-0" />
              {open && <span className="whitespace-nowrap">{n.label}</span>}
            </Link>
          );
          return open ? item : <Tooltip key={n.href} content={n.label} side="right">{item}</Tooltip>;
        })}

        {isAdmin && (() => {
          const active = pathname?.startsWith('/admin');
          const item = (
            <Link href="/admin"
                  className={cn('flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors',
                    active ? 'bg-amber-500/10 text-amber-600 dark:text-amber-300 font-medium'
                           : 'text-muted hover:bg-raised hover:text-ink',
                    !open && 'justify-center')}>
              <Shield size={18} className="shrink-0" />
              {open && <span className="whitespace-nowrap">Admin</span>}
            </Link>
          );
          return open ? item : <Tooltip content="Admin" side="right">{item}</Tooltip>;
        })()}

        {/* GitHub entry */}
        {(() => {
          const ghItem = (
            <button
              type="button"
              onClick={() => setGhPanelOpen((v) => !v)}
              className={cn(
                'relative w-full flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors',
                ghPanelOpen
                  ? 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-200 font-medium'
                  : 'text-muted hover:bg-raised hover:text-ink',
                !open && 'justify-center',
              )}
            >
              {ghPanelOpen && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-zinc-400" aria-hidden="true" />}
              <span className="relative shrink-0">
                <Github size={18} />
                {isGhConnected && (
                  <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 ring-1 ring-surface" />
                )}
              </span>
              {open && <span className="whitespace-nowrap">GitHub</span>}
            </button>
          );
          return open
            ? ghItem
            : <Tooltip content={`GitHub${isGhConnected ? ' (connected)' : ''}`} side="right">{ghItem}</Tooltip>;
        })()}
      </nav>

      {/* GitHub flyout panel */}
      <AnimatePresence>
        {ghPanelOpen && (
          <motion.div
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.18 }}
            className="fixed z-50 top-0 bottom-0 glass border-r border-edge shadow-pop overflow-hidden flex flex-col"
            style={{ left: open ? 240 : 68, width: 300 }}
          >
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-edge shrink-0">
              <span className="text-xs font-semibold">GitHub</span>
              <button type="button" onClick={() => setGhPanelOpen(false)}
                className="btn-ghost p-1 text-xs text-muted">✕</button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <GitHubPanel />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bottom: theme + account */}
      <div className="border-t border-edge p-2.5 space-y-1">
        <div className={cn('flex', open ? 'justify-start' : 'justify-center')}>
          <ThemeToggle />
        </div>

        <div className="relative">
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
                 aria-label="Upload profile photo" onChange={onAvatarPick} />
          <button type="button" onClick={() => setMenuOpen((v) => !v)}
                  aria-haspopup="menu" aria-expanded={menuOpen}
                  className={cn('w-full flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm hover:bg-raised transition-colors',
                    !open && 'justify-center')}>
            <Avatar user={user} size={26} />
            {open && (
              <span className="min-w-0 text-left flex-1">
                <span className="block text-sm font-medium truncate">{user?.username}</span>
                <span className="block text-[11px] text-faint truncate">{user?.email}</span>
              </span>
            )}
          </button>

          {menuOpen && (
            <>
              <button type="button" tabIndex={-1} aria-label="Close menu"
                      className="fixed inset-0 z-40 cursor-default" onClick={() => setMenuOpen(false)} />
              <div role="menu"
                   className="absolute bottom-full left-0 mb-1.5 z-50 w-56 card p-1.5 shadow-pop">
                <div className="px-2.5 py-2 border-b border-edge mb-1 flex items-center gap-2.5">
                  <Avatar user={user} size={36} />
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{user?.username}</div>
                    <div className="text-xs text-faint truncate">{user?.email}</div>
                  </div>
                </div>
                <button type="button" role="menuitem" disabled={uploading}
                        onClick={() => fileRef.current?.click()}
                        className="w-full flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-raised disabled:opacity-50">
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
                  {uploading ? 'Uploading...' : (user?.avatar_url ? 'Change photo' : 'Add profile photo')}
                </button>
                <div className="px-2.5 py-1.5 flex items-center justify-between text-xs text-muted">
                  <span className="inline-flex items-center gap-1.5"><User size={12} /> Trust score</span>
                  <span className="font-mono">{user?.trust_score?.toFixed(2)}</span>
                </div>
                <button type="button" role="menuitem"
                        onClick={() => { clearSession(); window.location.assign('/'); }}
                        className="w-full mt-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm
                                   text-rose-600 dark:text-rose-400 hover:bg-rose-500/10">
                  <LogOut size={14} /> Log out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </motion.aside>
  );
}
