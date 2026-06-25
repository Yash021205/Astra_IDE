'use client';
// Sandbox observability — a Grafana-style live dashboard of the runtime cost of
// each isolation tier (startup, CPU overhead, syscall latency, memory), streamed
// from /metrics/sandbox and charted with Recharts.

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity, Cpu, Gauge, MemoryStick, ShieldCheck, Timer,
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from 'recharts';

import AppShell from '../../components/AppShell';
import { getSandboxMetrics, type SandboxMetrics } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { cn } from '../../lib/utils';

const TIER_COLOR: Record<string, string> = {
  runc: '#7ec89a', gvisor: '#f0a8b8', firecracker: '#5eb8d4',
};
const POLL_MS = 2000;
const WINDOW = 30;          // samples kept on the rolling charts

interface Sample { t: string; runc: number; gvisor: number; firecracker: number; }

export default function ObservabilityPage() {
  const router = useRouter();
  const { token, hydrated } = useAuth();
  const [snap, setSnap] = useState<SandboxMetrics | null>(null);
  const [cpuSeries, setCpuSeries] = useState<Sample[]>([]);
  const [startSeries, setStartSeries] = useState<Sample[]>([]);
  const seq = useRef(0);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    let cancelled = false;

    async function poll() {
      try {
        const m = await getSandboxMetrics();
        if (cancelled) return;
        setSnap(m);
        const byTier = Object.fromEntries(m.tiers.map((t) => [t.tier, t]));
        const label = `${seq.current++}`;
        const cpu: Sample = { t: label,
          runc: byTier.runc?.cpu_overhead_pct ?? 0,
          gvisor: byTier.gvisor?.cpu_overhead_pct ?? 0,
          firecracker: byTier.firecracker?.cpu_overhead_pct ?? 0 };
        const start: Sample = { t: label,
          runc: byTier.runc?.startup_ms ?? 0,
          gvisor: byTier.gvisor?.startup_ms ?? 0,
          firecracker: byTier.firecracker?.startup_ms ?? 0 };
        setCpuSeries((s) => [...s, cpu].slice(-WINDOW));
        setStartSeries((s) => [...s, start].slice(-WINDOW));
      } catch { /* backend booting */ }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, hydrated]);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8 space-y-6">
        <div>
          <h1 className="t-h1 flex items-center gap-2.5">
            <Activity className="text-astra-600 dark:text-astra-300" size={26} aria-hidden="true" />
            Sandbox observability
          </h1>
          <p className="text-sm text-muted mt-1 max-w-2xl">
            Live runtime cost of each isolation tier — what the adaptive sandbox (B4) trades for
            stronger isolation. Streamed every {POLL_MS / 1000}s.
          </p>
        </div>

        {/* Tier KPI cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {snap?.tiers.map((t) => (
            <div key={t.tier} className="card p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: TIER_COLOR[t.tier] }} />
                <span className="font-semibold">{t.label}</span>
                <ShieldCheck size={14} className="ml-auto text-faint" />
              </div>
              <div className="grid grid-cols-2 gap-y-2 text-sm">
                <Metric icon={<Timer size={12} />} label="startup" value={`${t.startup_ms.toFixed(0)} ms`} />
                <Metric icon={<Cpu size={12} />} label="CPU ovh" value={`${t.cpu_overhead_pct.toFixed(1)}%`} />
                <Metric icon={<Gauge size={12} />} label="syscall" value={`${t.syscall_us.toFixed(1)} µs`} />
                <Metric icon={<MemoryStick size={12} />} label="memory" value={`${t.memory_mb.toFixed(0)} MB`} />
              </div>
              <p className="text-[11px] text-faint mt-2.5 pt-2.5 border-t border-edge">{t.isolation}</p>
            </div>
          ))}
        </div>

        {/* Realtime charts */}
        <div className="grid lg:grid-cols-2 gap-4">
          <ChartCard title="CPU overhead over time" subtitle="% vs bare runc · lower is cheaper">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={cpuSeries} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <defs>
                  {Object.entries(TIER_COLOR).map(([k, c]) => (
                    <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={c} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-edge))" />
                <XAxis dataKey="t" tick={false} stroke="rgb(var(--c-faint))" />
                <YAxis tick={{ fontSize: 11, fill: 'rgb(var(--c-faint))' }} stroke="rgb(var(--c-edge))" unit="%" />
                <RTooltip contentStyle={TOOLTIP} />
                <Area type="monotone" dataKey="runc" stroke={TIER_COLOR.runc} fill="url(#g-runc)" strokeWidth={2} isAnimationActive={false} />
                <Area type="monotone" dataKey="gvisor" stroke={TIER_COLOR.gvisor} fill="url(#g-gvisor)" strokeWidth={2} isAnimationActive={false} />
                <Area type="monotone" dataKey="firecracker" stroke={TIER_COLOR.firecracker} fill="url(#g-firecracker)" strokeWidth={2} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Cold-start latency over time" subtitle="ms to first byte · lower is faster">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={startSeries} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-edge))" />
                <XAxis dataKey="t" tick={false} stroke="rgb(var(--c-faint))" />
                <YAxis tick={{ fontSize: 11, fill: 'rgb(var(--c-faint))' }} stroke="rgb(var(--c-edge))" unit="ms" />
                <RTooltip contentStyle={TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="runc" stroke={TIER_COLOR.runc} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="gvisor" stroke={TIER_COLOR.gvisor} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="firecracker" stroke={TIER_COLOR.firecracker} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        {/* Current comparison bars */}
        <ChartCard title="Current footprint by tier" subtitle="snapshot">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={(snap?.tiers ?? []).map((t) => ({ name: t.label, 'CPU %': t.cpu_overhead_pct, 'Syscall µs': t.syscall_us, 'Mem (×10MB)': t.memory_mb / 10 }))}
                      margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-edge))" />
              <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'rgb(var(--c-muted))' }} stroke="rgb(var(--c-edge))" />
              <YAxis tick={{ fontSize: 11, fill: 'rgb(var(--c-faint))' }} stroke="rgb(var(--c-edge))" />
              <RTooltip contentStyle={TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="CPU %" fill="#618764" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="Syscall µs" fill="#e08e9b" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="Mem (×10MB)" fill="#2B5748" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {snap && <p className="text-xs text-faint">{snap.note}</p>}
      </section>
    </AppShell>
  );
}

const TOOLTIP = {
  background: 'rgb(var(--c-surface))', border: '1px solid rgb(var(--c-edge))',
  borderRadius: 10, fontSize: 12, color: 'rgb(var(--c-ink))',
} as const;

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-faint inline-flex items-center gap-1">{icon}{label}</div>
      <div className="font-mono text-ink">{value}</div>
    </div>
  );
}

function ChartCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-semibold text-sm">{title}</h3>
        <span className="text-[11px] text-faint">{subtitle}</span>
      </div>
      {children}
    </div>
  );
}
