'use client';
// Live activity feed — polls /api/v1/events every 3s, replacing the old
// synthesized stream. The backend's telemetry_loop continuously pushes
// scheduler / eBPF / sandbox events into the SchedulerEvent table.

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Brain, Cpu, Network, Leaf, Shield, Settings } from 'lucide-react';
import { listEvents, type SchedulerEvent } from '../lib/api';
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
  scheduler: 'text-astra-400  bg-astra-500/10  border-astra-500/30',
  sandbox:   'text-rose-400   bg-rose-500/10   border-rose-500/30',
  carbon:    'text-lime-400   bg-lime-500/10   border-lime-500/30',
  ebpf:      'text-cyan-400   bg-cyan-500/10   border-cyan-500/30',
  prewarm:   'text-amber-400  bg-amber-500/10  border-amber-500/30',
  collab:    'text-purple-400 bg-purple-500/10 border-purple-500/30',
  system:    'text-slate-400  bg-slate-500/10  border-slate-500/30',
};

const POLL_MS = 3000;

interface Props {
  className?: string;
  /** Optional filter shown as chips — clicking toggles the kind filter. */
  filterable?: boolean;
}

const FILTER_KINDS: SchedulerEvent['kind'][] = [
  'scheduler', 'sandbox', 'ebpf', 'carbon', 'prewarm', 'collab',
];

export default function ActivityFeed({ className, filterable = true }: Props) {
  const [events, setEvents]   = useState<SchedulerEvent[]>([]);
  const [filter, setFilter]   = useState<SchedulerEvent['kind'] | null>(null);
  const [error,  setError]    = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const items = await listEvents({ limit: 50, kind: filter ?? undefined });
        if (!cancelled) {
          setEvents(items);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.response?.data?.detail || 'Failed to load events');
      }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [filter]);

  return (
    <div className={cn('rounded-xl border border-slate-800 bg-slate-900/40 backdrop-blur', className)}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-astra-500" />
          <h3 className="font-semibold text-sm">Live activity</h3>
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            scheduler · sandbox · eBPF · carbon
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-emerald-400">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>live · {POLL_MS / 1000}s poll</span>
        </div>
      </div>

      {filterable && (
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-slate-800/50 text-[11px]">
          <button
            type="button"
            onClick={() => setFilter(null)}
            className={cn(
              'px-2 py-0.5 rounded border',
              filter === null
                ? 'border-astra-500 bg-astra-500/15 text-white'
                : 'border-slate-700 text-slate-400 hover:border-slate-500',
            )}
          >
            All
          </button>
          {FILTER_KINDS.map((k) => (
            <button
              key={k} type="button"
              onClick={() => setFilter(filter === k ? null : k)}
              className={cn(
                'px-2 py-0.5 rounded border capitalize',
                filter === k
                  ? 'border-astra-500 bg-astra-500/15 text-white'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500',
              )}
            >
              {k}
            </button>
          ))}
        </div>
      )}

      <div className="max-h-[420px] overflow-y-auto">
        {error && (
          <p className="p-4 text-sm text-rose-400">{error}</p>
        )}
        {!error && events.length === 0 && (
          <p className="p-4 text-sm text-slate-500 italic">
            Waiting for events… (backend telemetry loop emits one every few seconds)
          </p>
        )}
        <ul className="divide-y divide-slate-800/50">
          {events.map((it) => (
            <motion.li
              key={it.id}
              layout
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-start gap-3 px-4 py-2.5"
            >
              <div className={cn(
                'shrink-0 w-7 h-7 rounded-lg border flex items-center justify-center',
                COLOR_FOR[it.kind],
              )}>
                {ICON_FOR[it.kind]}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-slate-200">{it.title}</div>
                {it.detail && (
                  <div className="text-xs text-slate-500 mt-0.5 font-mono break-words">
                    {it.detail}
                  </div>
                )}
              </div>
              <div className="shrink-0 text-[10px] text-slate-500 font-mono whitespace-nowrap">
                {formatRel(it.timestamp)}
              </div>
            </motion.li>
          ))}
        </ul>
      </div>

      <div className="px-4 py-2 border-t border-slate-800 text-[10px] text-slate-500">
        Sourced from <code className="text-astra-400">/api/v1/events</code>. Backend emits eBPF /
        scheduler / sandbox events from the telemetry loop.
      </div>
    </div>
  );
}

function formatRel(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (diff < 0)         return 'now';
  if (diff < 60_000)    return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(iso).toLocaleString();
}
