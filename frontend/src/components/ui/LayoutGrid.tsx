'use client';
// Aceternity "Layout Grid" — a grid of cards that smoothly expand to the center
// of the screen (shared-layout animation) when clicked, revealing a richer
// explanation. Click the backdrop to close.

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface GridCard {
  id: string;
  title: string;
  /** short blurb shown on the collapsed card */
  blurb: string;
  /** plain-language explanation shown when expanded */
  what: string;
  /** step-by-step "how to use" lines shown when expanded */
  how: string[];
  icon: React.ReactNode;
  accent: string;        // tailwind color stem e.g. 'astra' | 'purple'
  span?: string;         // grid span classes
}

const ACCENT: Record<string, { ring: string; text: string; glow: string }> = {
  astra:   { ring: 'ring-astra-500/30',   text: 'text-astra-500',   glow: 'from-astra-400/50' },
  cyan:    { ring: 'ring-cyan-500/30',    text: 'text-cyan-500',    glow: 'from-cyan-400/50' },
  rose:    { ring: 'ring-rose-500/30',    text: 'text-rose-500',    glow: 'from-rose-400/50' },
  emerald: { ring: 'ring-emerald-500/30', text: 'text-emerald-500', glow: 'from-emerald-400/50' },
  amber:   { ring: 'ring-amber-500/30',   text: 'text-amber-500',   glow: 'from-amber-400/50' },
  purple:  { ring: 'ring-purple-500/30',  text: 'text-purple-500',  glow: 'from-purple-400/50' },
};

export default function LayoutGrid({ cards }: { cards: GridCard[] }) {
  const [active, setActive] = useState<GridCard | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 auto-rows-[minmax(180px,auto)]">
        {cards.map((card) => {
          const a = ACCENT[card.accent] ?? ACCENT.astra;
          return (
            <motion.button
              key={card.id}
              type="button"
              layoutId={`card-${card.id}`}
              onClick={() => setActive(card)}
              className={cn(
                'group relative text-left overflow-hidden rounded-2xl border border-edge bg-surface p-6',
                'shadow-card hover:shadow-pop transition-shadow ring-1 ring-transparent hover:' + a.ring,
                card.span,
              )}
            >
              <div className={cn('absolute -top-12 -right-12 h-44 w-44 rounded-full blur-2xl bg-gradient-to-br to-transparent opacity-90 dark:opacity-50', a.glow)} />
              <motion.div layoutId={`icon-${card.id}`} className={cn('relative mb-4', a.text)}>
                {card.icon}
              </motion.div>
              <motion.h3 layoutId={`title-${card.id}`} className="relative text-lg font-semibold">
                {card.title}
              </motion.h3>
              <p className="relative mt-1.5 text-sm text-muted leading-relaxed">{card.blurb}</p>
              <span className="relative mt-3 inline-flex items-center gap-1 text-xs font-medium text-faint group-hover:text-astra-500 transition-colors">
                Learn how it works &rarr;
              </span>
            </motion.button>
          );
        })}
      </div>

      <AnimatePresence>
        {active && (
          <div className="fixed inset-0 z-[70] grid place-items-center p-4 sm:p-8">
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setActive(null)}
              className="absolute inset-0 bg-black/60 backdrop-blur-md"
            />
            <motion.div
              layoutId={`card-${active.id}`}
              className="relative z-10 w-full max-w-2xl overflow-hidden rounded-3xl border border-edge bg-surface shadow-pop max-h-[88vh] overflow-y-auto"
            >
              <div className={cn('absolute -top-16 -right-16 h-48 w-48 rounded-full blur-3xl bg-gradient-to-br to-transparent opacity-70',
                (ACCENT[active.accent] ?? ACCENT.astra).glow)} />
              <button type="button" onClick={() => setActive(null)} aria-label="Close"
                      className="absolute right-4 top-4 z-20 btn-ghost p-2">
                <X size={18} />
              </button>

              <div className="relative p-7 sm:p-9">
                <motion.div layoutId={`icon-${active.id}`} className={cn('mb-4', (ACCENT[active.accent] ?? ACCENT.astra).text)}>
                  {active.icon}
                </motion.div>
                <motion.h3 layoutId={`title-${active.id}`} className="text-2xl font-bold">
                  {active.title}
                </motion.h3>

                <motion.div
                  initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                >
                  <div className="mt-5">
                    <p className="t-overline text-faint mb-1.5">What it does</p>
                    <p className="text-[15px] leading-relaxed text-ink/90">{active.what}</p>
                  </div>

                  <div className="mt-6">
                    <p className="t-overline text-faint mb-2.5">How to use it</p>
                    <ol className="space-y-2.5">
                      {active.how.map((step, i) => (
                        <li key={i} className="flex gap-3 text-sm text-muted leading-relaxed">
                          <span className={cn('shrink-0 grid place-items-center w-6 h-6 rounded-full text-xs font-semibold text-white',
                            'bg-gradient-to-br from-astra-500 to-blossom-400')}>
                            {i + 1}
                          </span>
                          <span className="pt-0.5">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </motion.div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
