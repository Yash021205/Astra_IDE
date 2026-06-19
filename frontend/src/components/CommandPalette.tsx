'use client';
// VS Code-style command palette. Opens on Ctrl/Cmd + Shift + P from anywhere.
//
// Commands can come from:
//   - Static actions registered below (navigation, theme, help)
//   - Dynamic actions passed via the `extraCommands` prop (e.g. the editor
//     can register "Run code", "Download file", etc. when mounted)

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Command, Search, ChevronRight, LayoutDashboard, Network, LogOut,
  Keyboard, Github,
} from 'lucide-react';

import { cn } from '../lib/utils';
import { useAuth } from '../lib/auth';

export interface PaletteCommand {
  id:        string;
  label:     string;
  hint?:     string;
  group:     string;
  icon?:     React.ReactNode;
  shortcut?: string;
  run:       () => void;
}

interface Props {
  extraCommands?: PaletteCommand[];
}

export default function CommandPalette({ extraCommands = [] }: Props) {
  const [open, setOpen]   = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router   = useRouter();
  const { clearSession } = useAuth();

  // Static commands available everywhere
  const staticCommands: PaletteCommand[] = useMemo(() => [
    {
      id: 'nav-dashboard', label: 'Go to: Workspaces',
      group: 'Navigation', icon: <LayoutDashboard size={14} />,
      run: () => router.push('/dashboard'),
    },
    {
      id: 'nav-clusters', label: 'Go to: Clusters',
      group: 'Navigation', icon: <Network size={14} />,
      run: () => router.push('/clusters'),
    },
    {
      id: 'logout', label: 'Log out',
      group: 'Account', icon: <LogOut size={14} />,
      run: () => { clearSession(); router.push('/'); },
    },
    {
      id: 'open-help', label: 'Show keyboard shortcuts',
      group: 'Help', icon: <Keyboard size={14} />, shortcut: 'Ctrl+K',
      run: () => {
        // Editor has its own help — dispatch a custom event so any open
        // editor instance can pick it up.
        window.dispatchEvent(new CustomEvent('astra:open-help'));
      },
    },
    {
      id: 'open-github', label: 'View on GitHub',
      group: 'Help', icon: <Github size={14} />,
      run: () => window.open('https://github.com/PrasannaMishra001/astra-ide', '_blank'),
    },
  ], [router, clearSession]);

  const allCommands = useMemo(
    () => [...extraCommands, ...staticCommands],
    [extraCommands, staticCommands],
  );

  // Fuzzy-ish filter: keep ones where every char of query appears in order
  const filtered = useMemo(() => {
    if (!query) return allCommands;
    const q = query.toLowerCase();
    return allCommands.filter((c) => {
      const haystack = (c.label + ' ' + (c.hint ?? '') + ' ' + c.group).toLowerCase();
      let qi = 0;
      for (const ch of haystack) {
        if (ch === q[qi]) qi += 1;
        if (qi >= q.length) return true;
      }
      return false;
    });
  }, [allCommands, query]);

  // Global toggle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 30);
      setQuery('');
      setActive(0);
    }
  }, [open]);

  // Keep active index in range
  useEffect(() => {
    setActive(0);
  }, [query]);

  const runCommand = (cmd: PaletteCommand) => {
    setOpen(false);
    setTimeout(cmd.run, 50);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[60] flex items-start justify-center pt-24 px-4"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0, y: -8 }}
            animate={{ scale: 1,    opacity: 1, y: 0 }}
            exit={{    scale: 0.96, opacity: 0, y: -8 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
              <Command size={18} className="text-astra-500 shrink-0" />
              <Search   size={14} className="text-slate-500" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setActive((i) => Math.min(filtered.length - 1, i + 1));
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setActive((i) => Math.max(0, i - 1));
                  } else if (e.key === 'Enter') {
                    e.preventDefault();
                    const cmd = filtered[active];
                    if (cmd) runCommand(cmd);
                  }
                }}
                placeholder="Type a command or search…"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-slate-500"
              />
              <span className="text-[10px] text-slate-500 font-mono px-1.5 py-0.5 rounded bg-slate-800">
                Esc
              </span>
            </div>

            <div className="max-h-[60vh] overflow-y-auto py-2">
              {filtered.length === 0 && (
                <p className="px-4 py-6 text-sm text-slate-500 text-center">
                  No commands match.
                </p>
              )}
              {filtered.map((cmd, idx) => (
                <button
                  key={cmd.id}
                  type="button"
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => runCommand(cmd)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors',
                    idx === active
                      ? 'bg-astra-600/20 text-white'
                      : 'hover:bg-slate-800/60 text-slate-200',
                  )}
                >
                  <span className="text-slate-400 shrink-0">{cmd.icon ?? <ChevronRight size={14} />}</span>
                  <span className="flex-1">
                    <span className="block">{cmd.label}</span>
                    {cmd.hint && (
                      <span className="block text-xs text-slate-500">{cmd.hint}</span>
                    )}
                  </span>
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                    {cmd.group}
                  </span>
                  {cmd.shortcut && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-astra-300">
                      {cmd.shortcut}
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div className="px-4 py-2 border-t border-slate-800 text-[10px] text-slate-500 flex items-center justify-between">
              <span>↑↓ navigate · ↵ run · Esc close</span>
              <span className="font-mono">Ctrl+Shift+P</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
