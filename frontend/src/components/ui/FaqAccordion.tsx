'use client';
// Netflix-style FAQ accordion over a giant translucent wordmark background
// (same treatment as the site footer). Each item expands smoothly.

import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Plus } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface FaqItem { q: string; a: React.ReactNode; }

export default function FaqAccordion({
  items, watermark = 'ASTRA-IDE', title = 'How the numbers work',
}: {
  items: FaqItem[]; watermark?: string; title?: string;
}) {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section className="relative overflow-hidden rounded-2xl border border-edge bg-bg">
      {/* Giant translucent wordmark behind the FAQ */}
      <div className="pointer-events-none select-none absolute inset-x-0 -bottom-[0.16em] flex justify-center">
        <span className="font-extrabold tracking-tighter leading-none text-transparent bg-clip-text
                         bg-gradient-to-b from-ink/[0.06] to-ink/[0.01] text-[24vw] lg:text-[14rem]">
          {watermark}
        </span>
      </div>

      <div className="relative z-10 p-5 sm:p-7">
        <h3 className="t-h2 mb-5">{title}</h3>
        <div className="space-y-2.5 max-w-3xl">
          {items.map((it, i) => {
            const isOpen = open === i;
            return (
              <div key={i} className="rounded-xl border border-edge bg-surface/80 backdrop-blur overflow-hidden">
                <button type="button" onClick={() => setOpen(isOpen ? null : i)}
                        aria-expanded={isOpen}
                        className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-raised/50 transition-colors">
                  <span className="flex-1 font-medium text-[15px]">{it.q}</span>
                  <Plus size={18} className={cn('shrink-0 text-faint transition-transform duration-300',
                    isOpen && 'rotate-45 text-astra-500')} />
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25, ease: 'easeOut' }}>
                      <div className="px-4 pb-4 text-sm text-muted leading-relaxed">{it.a}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
