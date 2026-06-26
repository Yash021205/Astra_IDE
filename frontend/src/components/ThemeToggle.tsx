'use client';
// Theme toggle with a "drop spread" — using the View Transitions API, the new
// theme is revealed by a circle expanding from the button (like ink in water).
// Falls back to an instant switch where the API is unavailable.

import { useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../lib/theme';
import Tooltip from './ui/Tooltip';

export default function ThemeToggle({ className = '' }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  const btnRef = useRef<HTMLButtonElement>(null);

  async function toggle() {
    const btn = btnRef.current;
    const doc = document as any;
    if (!doc.startViewTransition || !btn) { setTheme(next); return; }

    const r = btn.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const end = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));

    const transition = doc.startViewTransition(() => setTheme(next));
    try {
      await transition.ready;
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${end}px at ${x}px ${y}px)`] },
        { duration: 650, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' },
      );
    } catch { /* API may reject; theme already switched */ }
  }

  return (
    <Tooltip content={`Switch to ${next} mode`} side="bottom">
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        aria-label={`Switch to ${next} theme`}
        className={`relative btn-ghost p-2 ${className}`}
      >
        <AnimatePresence mode="wait" initial={false}>
          {theme === 'dark' ? (
            <motion.span key="sun"
              initial={{ rotate: -90, scale: 0, opacity: 0 }}
              animate={{ rotate: 0, scale: 1, opacity: 1 }}
              exit={{ rotate: 90, scale: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}>
              <Sun size={16} />
            </motion.span>
          ) : (
            <motion.span key="moon"
              initial={{ rotate: 90, scale: 0, opacity: 0 }}
              animate={{ rotate: 0, scale: 1, opacity: 1 }}
              exit={{ rotate: -90, scale: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}>
              <Moon size={16} />
            </motion.span>
          )}
        </AnimatePresence>
      </button>
    </Tooltip>
  );
}
