'use client';
// Containers — a Docker-Desktop-style view of every workspace as a running
// pod/container: live CPU/memory, runtime class, uptime, node, logs, and
// start/stop/restart actions.

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Boxes, Cpu, MemoryStick, Play, Square, RotateCw, ScrollText, ExternalLink,
  ShieldCheck, Server, Container, Loader2,
} from 'lucide-react';

import AppShell from '../../components/AppShell';
import {
  getPods, getPodLogs, startWorkspace, stopWorkspace,
  type PodInfo,
} from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { toast } from '../../lib/toast';
import { cn } from '../../lib/utils';

const POLL_MS = 3000;

const STATUS = {
  RUNNING:   { dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400', label: 'running' },
  PREWARMED: { dot: 'bg-astra-500',   text: 'text-astra-600 dark:text-astra-300', label: 'prewarmed' },
  PENDING:   { dot: 'bg-amber-500',   text: 'text-amber-600 dark:text-amber-400', label: 'pending' },
  STOPPED:   { dot: 'bg-faint',       text: 'text-faint', label: 'stopped' },
  FAILED:    { dot: 'bg-rose-500',    text: 'text-rose-600 dark:text-rose-400', label: 'failed' },
  ARCHIVED:  { dot: 'bg-faint',       text: 'text-faint', label: 'archived' },
} as Record<string, { dot: string; text: string; label: string }>;

const TIER_TONE: Record<string, string> = {
  runc: 'text-emerald-600 dark:text-emerald-400',
  gvisor: 'text-amber-600 dark:text-amber-400',
  firecracker: 'text-rose-600 dark:text-rose-400',
};

function fmtUptime(s: number): string {
  if (s <= 0) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`;
}

export default function PodsPage() {
  const router = useRouter();
  const { token, hydrated } = useAuth();
  const [pods, setPods] = useState<PodInfo[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [openLogs, setOpenLogs] = useState<number | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const loaded = useRef(false);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    let cancelled = false;
    async function poll() {
      try { const p = await getPods(); if (!cancelled) { setPods(p); loaded.current = true; } } catch { /* */ }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, hydrated]);

  useEffect(() => {
    if (openLogs == null) return;
    getPodLogs(openLogs).then((r) => setLogs(r.lines)).catch(() => setLogs(['(no logs)']));
    const id = setInterval(() => getPodLogs(openLogs).then((r) => setLogs(r.lines)).catch(() => {}), POLL_MS);
    return () => clearInterval(id);
  }, [openLogs]);

  async function action(p: PodInfo, kind: 'start' | 'stop' | 'restart') {
    setBusy(p.id);
    try {
      if (kind === 'stop') await stopWorkspace(p.id);
      else if (kind === 'start') await startWorkspace(p.id);
      else { await stopWorkspace(p.id); await startWorkspace(p.id); }
      setPods(await getPods());
      toast.success(`Container ${kind}ed`, p.name);
    } catch (e: any) { toast.error(`Could not ${kind}`, e?.response?.data?.detail || 'Error'); }
    setBusy(null);
  }

  const running = pods.filter((p) => p.status === 'RUNNING').length;
  const totalCpu = pods.reduce((s, p) => s + p.cpu_pct, 0);
  const totalMem = pods.reduce((s, p) => s + p.mem_mb, 0);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8 space-y-6">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="t-h1 flex items-center gap-2.5">
              <Container className="text-astra-600 dark:text-astra-300" size={26} aria-hidden="true" />
              Containers
            </h1>
            <p className="text-sm text-muted mt-1">
              Every workspace as a running pod — live resources, runtime isolation, logs and lifecycle.
            </p>
          </div>
          <div className="flex gap-3 text-xs">
            <Kpi label="Running" value={`${running}/${pods.length}`} />
            <Kpi label="CPU" value={`${totalCpu.toFixed(0)}%`} />
            <Kpi label="Memory" value={`${totalMem.toFixed(0)} MB`} />
          </div>
        </div>

        {loaded.current && pods.length === 0 && (
          <div className="card p-8 text-center text-faint text-sm">
            No containers yet. Create a workspace from the dashboard.
          </div>
        )}

        <div className="space-y-3">
          {pods.map((p) => {
            const st = STATUS[p.status] ?? STATUS.STOPPED;
            const run = p.status === 'RUNNING';
            return (
              <div key={p.id} className="card overflow-hidden">
                <div className="px-4 py-3 flex items-center gap-4 flex-wrap">
                  {/* identity */}
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <span className={cn('w-2.5 h-2.5 rounded-full shrink-0', st.dot, run && 'animate-pulse')} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate">{p.name}</span>
                        <span className="font-mono text-[11px] text-faint truncate">{p.pod_name}</span>
                      </div>
                      <div className="text-[11px] text-faint flex items-center gap-2 flex-wrap">
                        <span className="font-mono">{p.image}</span>
                        <span className="inline-flex items-center gap-1"><ShieldCheck size={10} className={TIER_TONE[p.sandbox_tier]} />{p.runtime_class}</span>
                        <span className="inline-flex items-center gap-1"><Server size={10} />{p.node_name} · {p.cluster_id}</span>
                      </div>
                    </div>
                  </div>

                  {/* live meters */}
                  <div className="flex items-center gap-4 shrink-0">
                    <Meter icon={<Cpu size={11} />} label="CPU" pct={p.cpu_pct} display={`${p.cpu_pct.toFixed(0)}%`} />
                    <Meter icon={<MemoryStick size={11} />} label="MEM" pct={p.mem_pct} display={`${p.mem_mb.toFixed(0)}MB`} />
                    <div className="text-right w-16">
                      <div className={cn('text-[11px] font-medium', st.text)}>{st.label}</div>
                      <div className="text-[10px] text-faint">up {fmtUptime(p.uptime_s)}</div>
                    </div>
                  </div>

                  {/* actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    {run ? (
                      <IconAction title="Stop" onClick={() => action(p, 'stop')} busy={busy === p.id}><Square size={14} /></IconAction>
                    ) : (
                      <IconAction title="Start" onClick={() => action(p, 'start')} busy={busy === p.id}><Play size={14} /></IconAction>
                    )}
                    <IconAction title="Restart" onClick={() => action(p, 'restart')} busy={busy === p.id}><RotateCw size={14} /></IconAction>
                    <IconAction title="Logs" onClick={() => setOpenLogs(openLogs === p.id ? null : p.id)}><ScrollText size={14} /></IconAction>
                    <Link href={`/workspaces/${p.id}`} title="Open" className="btn-ghost p-1.5"><ExternalLink size={14} /></Link>
                  </div>
                </div>

                {openLogs === p.id && (
                  <div className="border-t border-edge bg-[#16211d]/90 dark:bg-black/40 px-4 py-3 font-mono text-[11px] text-slate-300 max-h-56 overflow-auto">
                    {logs.map((l, i) => <div key={i} className="whitespace-pre-wrap leading-relaxed">{l}</div>)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </AppShell>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="card px-3 py-2 text-center">
      <div className="text-base font-bold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
    </div>
  );
}

function Meter({ icon, label, pct, display }: { icon: React.ReactNode; label: string; pct: number; display: string }) {
  const p = Math.max(0, Math.min(100, pct));
  const tone = p > 85 ? 'bg-rose-500' : p > 60 ? 'bg-amber-500' : 'bg-astra-500';
  return (
    <div className="w-20">
      <div className="flex items-center justify-between text-[10px] text-faint mb-1">
        <span className="inline-flex items-center gap-1">{icon}{label}</span>
        <span className="font-mono">{display}</span>
      </div>
      <div className="h-1.5 rounded-full bg-raised overflow-hidden">
        <div className={cn('h-full rounded-full transition-[width] duration-700', tone)} style={{ width: `${p}%` }} />
      </div>
    </div>
  );
}

function IconAction({ title, onClick, busy, children }:
  { title: string; onClick: () => void; busy?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" title={title} aria-label={title} onClick={onClick} disabled={busy}
            className="btn-ghost p-1.5 disabled:opacity-50">
      {busy ? <Loader2 size={14} className="animate-spin" /> : children}
    </button>
  );
}
