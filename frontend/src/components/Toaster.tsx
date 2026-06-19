'use client';
// Toaster — global stacked notification container. Mount once in the root
// layout; call `toast.success(...)` etc. from anywhere.
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react';
import { useToastStore } from '../lib/toast';
import { cn } from '../lib/utils';

const ICON_FOR = {
  success: CheckCircle2,
  error:   XCircle,
  info:    Info,
  warning: AlertTriangle,
} as const;

const STYLE_FOR = {
  success: 'border-emerald-700/60 bg-emerald-950/80 text-emerald-100',
  error:   'border-rose-700/60    bg-rose-950/80    text-rose-100',
  info:    'border-astra-700/60   bg-astra-950/80   text-astra-100',
  warning: 'border-amber-700/60   bg-amber-950/80   text-amber-100',
} as const;

const ACCENT_FOR = {
  success: 'text-emerald-400',
  error:   'text-rose-400',
  info:    'text-astra-400',
  warning: 'text-amber-400',
} as const;

export default function Toaster() {
  const items  = useToastStore((s) => s.items);
  const remove = useToastStore((s) => s.remove);

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence initial={false}>
        {items.map((t) => {
          const Icon = ICON_FOR[t.kind];
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 32, scale: 0.96 }}
              animate={{ opacity: 1, x: 0,  scale: 1 }}
              exit={{    opacity: 0, x: 32, scale: 0.96 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'pointer-events-auto flex gap-3 px-4 py-3 rounded-lg border shadow-2xl backdrop-blur',
                'w-80 max-w-[90vw]',
                STYLE_FOR[t.kind],
              )}
            >
              <Icon size={18} className={cn('mt-0.5 shrink-0', ACCENT_FOR[t.kind])} />
              <div className="flex-1 text-sm">
                <div className="font-semibold">{t.title}</div>
                {t.message && (
                  <div className="text-xs opacity-80 mt-0.5">{t.message}</div>
                )}
              </div>
              <button
                onClick={() => remove(t.id)} type="button" aria-label="Dismiss"
                className="text-slate-400 hover:text-white shrink-0"
              >
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
