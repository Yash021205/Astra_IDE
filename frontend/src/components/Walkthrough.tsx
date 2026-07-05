'use client';
// Skippable product tour. Dims the page and spotlights one element at a time with
// a short explanation, so a new user understands the product in under a minute.
// Auto-opens once (remembered in localStorage); re-open by dispatching
// window.dispatchEvent(new Event('astra:open-tour')). Zero external dependencies.

import { useCallback, useEffect, useLayoutEffect, useState } from 'react';

interface Step {
  title: string;
  body: string;
  selector?: string;   // element to spotlight; centered card if absent/not found
}

const STEPS: Step[] = [
  {
    title: 'Welcome to ASTRA-IDE',
    body: 'A cloud IDE whose control plane is research: the scheduling, isolation, and placement of your workspaces are learned or adaptive. Here is a 30-second tour.',
  },
  {
    title: 'Your workspaces',
    body: 'Create an isolated, server-side workspace here. Each one is risk-scored and given the cheapest safe sandbox tier (plain container, gVisor, or micro-VM), then placed by a reinforcement-learning scheduler.',
    selector: 'a[href="/dashboard"]',
  },
  {
    title: 'Benchmarks',
    body: 'See the scheduler and the other contributions measured against baselines on real datasets, plus a live in-browser simulator you can rerun.',
    selector: 'a[href="/benchmarks"]',
  },
  {
    title: 'Research and sources',
    body: 'Every headline number traces to the paper it implements and the official dataset it was measured on. Nothing here is hand-waved.',
    selector: 'a[href="/research"]',
  },
  {
    title: 'That is the tour',
    body: 'Open a workspace to start coding, or explore the dashboards to see the scheduling, isolation, and carbon decisions in action.',
  },
];

const DONE_KEY = 'astra-tour-v1-done';
const PAD = 8;

interface Rect { top: number; left: number; width: number; height: number; }

export default function Walkthrough() {
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);

  // Auto-open once; allow re-open via a global event.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!localStorage.getItem(DONE_KEY)) {
      const t = setTimeout(() => setOpen(true), 700);
      return () => clearTimeout(t);
    }
  }, []);
  useEffect(() => {
    const onOpen = () => { setI(0); setOpen(true); };
    window.addEventListener('astra:open-tour', onOpen);
    return () => window.removeEventListener('astra:open-tour', onOpen);
  }, []);

  // Locate the spotlight target for the current step.
  useLayoutEffect(() => {
    if (!open) return;
    const sel = STEPS[i]?.selector;
    if (!sel) { setRect(null); return; }
    const el = document.querySelector(sel) as HTMLElement | null;
    if (!el) { setRect(null); return; }
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const r = el.getBoundingClientRect();
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 });
  }, [open, i]);

  const finish = useCallback(() => {
    localStorage.setItem(DONE_KEY, '1');
    setOpen(false);
  }, []);

  if (!open) return null;
  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  // Card placement: below the spotlight if there is room, else centered.
  const cardStyle: React.CSSProperties = rect
    ? { position: 'fixed', top: Math.min(rect.top + rect.height + 12, window.innerHeight - 220),
        left: Math.min(Math.max(rect.left, 12), window.innerWidth - 372) }
    : { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };

  return (
    <div className="fixed inset-0 z-[100]" role="dialog" aria-modal="true" aria-label="Product tour">
      {/* Dim + spotlight cutout (box-shadow trick) or full dim when centered */}
      {rect ? (
        <div
          className="fixed rounded-xl ring-2 ring-astra-400 transition-all duration-300 pointer-events-none"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height,
                   boxShadow: '0 0 0 9999px rgba(2, 12, 8, 0.72)' }}
          aria-hidden="true"
        />
      ) : (
        <div className="fixed inset-0" style={{ background: 'rgba(2, 12, 8, 0.72)' }} aria-hidden="true" />
      )}

      {/* Step card */}
      <div style={cardStyle}
           className="w-[min(360px,calc(100vw-24px))] card p-4 shadow-pop border border-edge-strong">
        <div className="flex items-center gap-1.5 mb-2" aria-hidden="true">
          {STEPS.map((_, s) => (
            <span key={s} className={`h-1.5 rounded-full transition-all ${s === i ? 'w-5 bg-astra-500' : 'w-1.5 bg-edge-strong'}`} />
          ))}
        </div>
        <h3 className="text-base font-semibold text-ink">{step.title}</h3>
        <p className="mt-1.5 text-sm text-muted">{step.body}</p>
        <div className="mt-4 flex items-center justify-between">
          <button type="button" onClick={finish} className="text-xs text-faint hover:text-muted">
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {i > 0 && (
              <button type="button" onClick={() => setI((v) => v - 1)}
                      className="px-2.5 py-1.5 text-sm rounded-lg text-muted hover:bg-raised">
                Back
              </button>
            )}
            <button type="button" onClick={() => (last ? finish() : setI((v) => v + 1))}
                    className="px-3.5 py-1.5 text-sm rounded-lg bg-astra-600 text-white font-medium hover:bg-astra-700">
              {last ? 'Done' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
