'use client';
// Scheduler comparison: the eight selectable placement algorithms and how they
// compare on makespan (from benchmarks/b1_scheduler, lower is better). Honest by
// design - the classical heuristics lead on makespan, the RL policy is
// competitive and beats random. Bars animate in on scroll. No external assets.

import { useEffect, useRef, useState } from 'react';
import { cn } from '../../lib/utils';

// Real numbers from the makespan/energy evaluation (template workloads, 40 eps).
const MAKESPAN: { name: string; value: number; kind: 'rl' | 'heuristic' | 'naive' }[] = [
  { name: 'HEFT',            value: 29.7,  kind: 'heuristic' },
  { name: 'Greedy',         value: 30.6,  kind: 'heuristic' },
  { name: 'Min-Min',        value: 32.8,  kind: 'heuristic' },
  { name: 'PF-MPPO (RL)',   value: 106.3, kind: 'rl' },
  { name: 'Random',         value: 247.3, kind: 'naive' },
];
const MAX = 247.3;

const ALGOS = [
  'Multi-objective heuristic', 'PF-MPPO (deep RL)', 'HEFT', 'Min-Min',
  'Least loaded', 'Carbon-aware', 'Round robin', 'Random',
];

const BAR = {
  heuristic: 'bg-emerald-500',
  rl:        'bg-indigo-500',
  naive:     'bg-slate-400 dark:bg-slate-600',
} as const;

export default function SchedulerCompare() {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setShown(true),
      { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className="grid gap-8 lg:grid-cols-2 items-start">
      {/* selectable algorithms */}
      <div>
        <h3 className="text-lg font-semibold text-ink">Pick your scheduler</h3>
        <p className="text-muted text-sm mt-1 mb-4">
          The control plane ships eight placement strategies. Choose per deployment,
          or compare them live on any workload.
        </p>
        <div className="flex flex-wrap gap-2">
          {ALGOS.map((a, i) => (
            <span key={a}
              className={cn('px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                i === 1
                  ? 'border-indigo-500/40 bg-indigo-500/10 text-indigo-600 dark:text-indigo-300'
                  : 'border-edge bg-surface text-muted hover:border-emerald-500/40 hover:text-ink')}>
              {a}
            </span>
          ))}
        </div>
        <p className="text-xs text-faint mt-5 leading-relaxed">
          Honest result: on makespan the list-scheduling heuristics (HEFT, Min-Min) lead;
          the PF-MPPO deep-RL policy is competitive and clearly beats random, but does not
          dominate the strong heuristics. We expose the trade-off instead of hiding it.
        </p>
      </div>

      {/* makespan bars (lower is better) */}
      <div className="rounded-2xl border border-edge bg-surface p-5">
        <div className="flex items-baseline justify-between mb-4">
          <h3 className="text-sm font-semibold text-ink">Makespan by algorithm</h3>
          <span className="text-xs text-faint">lower is better</span>
        </div>
        <div className="space-y-3">
          {MAKESPAN.map((m) => (
            <div key={m.name}>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-ink">{m.name}</span>
                <span className="text-faint tabular-nums">{m.value.toFixed(1)}</span>
              </div>
              <div className="h-2.5 rounded-full bg-raised overflow-hidden">
                <div className={cn('h-full rounded-full transition-[width] duration-1000 ease-out', BAR[m.kind])}
                     style={{ width: shown ? `${(m.value / MAX) * 100}%` : '0%' }} />
              </div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-faint mt-4">
          benchmarks/b1_scheduler, template workloads. Evaluated vs the paper's HEFT and
          Min-Min baselines plus greedy and random.
        </p>
      </div>
    </div>
  );
}
