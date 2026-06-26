'use client';
// Live activity feed: polls /api/v1/events every 3s. The backend telemetry
// loop pushes scheduler / eBPF / sandbox / carbon events continuously.

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Brain, Cpu, Network, Leaf, Shield, Settings } from 'lucide-react';
import { listEvents, type SchedulerEvent } from '../lib/api';
import { formatRel } from '../lib/time';
import { cn } from '../lib/utils';

const ICON_FOR: Record<SchedulerEvent['kind'], React.ReactNode> = {
  scheduler: <Brain    size={14} />,
  sandbox:   <Shield   size={14} />,
  carbon:    <Leaf     size={14} />,
  ebpf:      <Network  size={14} />,
  prewarm:   <Cpu      size={14} />,
  collab:    <Activity size={14} />,
  system:    <Settings size={14} />,
};

const COLOR_FOR: Record<SchedulerEvent['kind'], string> = {
  scheduler: 'text-astra-600 dark:text-astra-400 bg-astra-500/10 border-astra-500/30',
  sandbox:   'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/30',
  carbon:    'text-lime-600 dark:text-lime-400 bg-lime-500/10 border-lime-500/30',
  ebpf:      'text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  prewarm:   'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/30',
  collab:    'text-purple-600 dark:text-purple-400 bg-purple-500/10 border-purple-500/30',
  system:    'text-muted bg-raised border-edge',
};

const POLL_MS = 3000;

interface Props {
  className?: string;
  filterable?: boolean;
}

const FILTER_KINDS: SchedulerEvent['kind'][] = [
  'scheduler', 'sandbox', 'ebpf', 'carbon', 'prewarm', 'collab',
];

export default function ActivityFeed({ className, filterable = true }: Props) {
  const [events, setEvents] = useState<SchedulerEvent[]>([]);
  const [filter, setFilter] = useState<SchedulerEvent['kind'] | null>(null);
  const [error,  setError]  = useState<string | null>(null);
  // Re-render every few seconds so relative times ("12s ago") stay live even
  // when the event list itself has not changed.
  const [, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const items = await listEvents({ limit: 50, kind: filter ?? undefined });
        if (!cancelled) { setEvents(items); setError(null); }
      } catch (e: any) {
        if (!cancelled) setError(e?.response?.data?.detail || 'Failed to load events');
      }
    }
    poll();
    const id = setInterval(() => { poll(); setTick((t) => t + 1); }, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [filter]);

  return (
    <div className={cn('card overflow-hidden', className)}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-edge flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
          <h3 className="font-semibold text-sm">Live activity</h3>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-emerald-600 dark:text-emerald-400">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
          <span>live, refreshes every {POLL_MS / 1000}s</span>
        </div>
      </div>

      {filterable && (
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-edge text-[11px]"
             role="group" aria-label="Filter events by kind">
          <button type="button" onClick={() => setFilter(null)}
                  className={cn('px-2 py-1 rounded-md border transition-colors',
                    filter === null
                      ? 'border-astra-500 bg-astra-500/10 text-ink font-medium'
                      : 'border-edge text-muted hover:border-edge-strong')}>
            All
          </button>
          {FILTER_KINDS.map((k) => (
            <button key={k} type="button" onClick={() => setFilter(filter === k ? null : k)}
                    className={cn('px-2 py-1 rounded-md border capitalize transition-colors',
                      filter === k
                        ? 'border-astra-500 bg-astra-500/10 text-ink font-medium'
                        : 'border-edge text-muted hover:border-edge-strong')}>
              {k}
            </button>
          ))}
        </div>
      )}

      <div className="max-h-[420px] overflow-y-auto" role="log" aria-label="Live platform events">
        {error && <p className="p-4 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        {!error && events.length === 0 && (
          <p className="p-4 text-sm text-faint">Waiting for events from the telemetry loop.</p>
        )}
        <ul className="divide-y divide-edge">
          {events.map((it) => (
            <motion.li key={it.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                       className="flex items-start gap-3 px-4 py-2.5">
              <div className={cn('shrink-0 w-7 h-7 rounded-lg border flex items-center justify-center',
                                  COLOR_FOR[it.kind])} aria-hidden="true">
                {ICON_FOR[it.kind]}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-ink">{it.title}</div>
                {it.detail && (
                  <div className="text-xs text-faint mt-0.5 font-mono break-words">{it.detail}</div>
                )}
              </div>
              <time className="shrink-0 text-[10px] text-faint font-mono whitespace-nowrap"
                    dateTime={it.timestamp}>
                {formatRel(it.timestamp)}
              </time>
            </motion.li>
          ))}
        </ul>
      </div>
    </div>
  );
}
