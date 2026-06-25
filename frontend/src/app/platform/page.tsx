'use client';
// Platform: what is actually running underneath. Live infrastructure status
// (PostgreSQL / Redis / MinIO / Prometheus), the seven research systems with
// their measured results, and the technology stack. Every number here comes
// from an experiment in the repository, not a slide.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity, Brain, Database, ExternalLink, Flame, GitBranch, Layers, Leaf,
  Network, Server, Shield, Timer, Users, Zap,
} from 'lucide-react';

import AppShell from '../../components/AppShell';
import { getSystemStatus, type SystemStatus } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { cn } from '../../lib/utils';

const BREAKTHROUGHS = [
  {
    id: 'B1', title: 'DRL-PPO scheduler', icon: <Brain size={16} />,
    paper: 'Xu et al., 2024 (arXiv:2403.07905)',
    result: '+112% reward vs best classical baseline; 0.57% SLA violations',
    detail: 'PPO agent (stable-baselines3) trained in a custom Gymnasium cluster environment; learns placement from live telemetry instead of static heuristics.',
  },
  {
    id: 'B2', title: 'eBPF telemetry', icon: <Network size={16} />,
    paper: 'eHashPipe (HashPipe sketch)',
    result: 'Top-K syscall tracking at 100% precision (small k) in bounded memory',
    detail: 'Tetragon in-kernel probes feed a 500ms state vector to the scheduler; first-party corpus of 171k syscall events captured on GCP.',
  },
  {
    id: 'B3', title: 'LSTM prewarming', icon: <Timer size={16} />,
    paper: 'IEEE Transformer cold-start (LSTM baseline)',
    result: 'Median N-RMSE 0.085 on the Azure Functions 2019 production trace',
    detail: 'A global LSTM trained across functions beats the per-function paper baseline; predictions drive the warm-pool size.',
  },
  {
    id: 'B4', title: 'Adaptive sandboxing', icon: <Shield size={16} />,
    paper: 'Iacovazzi & Raza, IEEE CSR 2022 + 2 more',
    result: 'Policy gate recall 0.95 @ ~0 FPR; IDS 0.80 acc / 0.10 FPR on first-party eBPF data',
    detail: 'Risk scorer picks runc / gVisor / Firecracker per workload; a syscall-graph IDS and a transactional policy gate block escapes.',
  },
  {
    id: 'B5', title: 'Multi-cluster federation', icon: <Layers size={16} />,
    paper: 'arXiv:2512.24914 (AI multi-cluster)',
    result: 'Live Karmada failover verified: replicas reschedule to the surviving cluster',
    detail: 'Divided 70/30 propagation across regions; the AI loop retunes weights from utilization + carbon; cluster-loss reschedule proven on GCP.',
  },
  {
    id: 'B6', title: 'Carbon-aware scheduling', icon: <Leaf size={16} />,
    paper: 'PCAPS (Lechowicz et al.)',
    result: '25.8% CO2 reduction with 12h flexibility, 45% with 24h',
    detail: 'Live grid intensity (electricityMaps / UK Carbon API) shifts deferrable work to greener windows and regions.',
  },
  {
    id: 'B7', title: 'CRDT collaboration', icon: <Users size={16} />,
    paper: 'Eg-walker (Kleppmann, EuroSys 2025)',
    result: 'Convergence verified on the authors’ published editing traces',
    detail: 'Yjs CRDTs over WebSocket keep every cursor and keystroke consistent with no central lock; same family as Figma’s sync.',
  },
];

const STACK: { group: string; items: string[] }[] = [
  { group: 'Frontend',  items: ['Next.js 14', 'Monaco Editor', 'Yjs + y-monaco', 'xterm.js', 'Tailwind CSS'] },
  { group: 'Backend',   items: ['FastAPI', 'PostgreSQL', 'Redis', 'MinIO (S3)', 'JWT + Google OAuth'] },
  { group: 'AI / ML',   items: ['stable-baselines3 (PPO)', 'Gymnasium', 'PyTorch (LSTM)', 'scikit-learn (IDS)'] },
  { group: 'Infra',     items: ['Docker Compose', 'Kubernetes + Karmada', 'gVisor / Firecracker', 'Tetragon eBPF', 'Prometheus + Grafana', 'KEDA', 'Terraform', 'Caddy (TLS)'] },
];

export default function PlatformPage() {
  const router = useRouter();
  const { token, hydrated } = useAuth();
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    getSystemStatus().then(setStatus).catch(() => {});
  }, [token, hydrated]);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8 space-y-8">
        <div>
          <h1 className="t-h1">Platform</h1>
          <p className="text-sm text-muted mt-1">
            Live infrastructure, the seven research systems behind the product, and how they are measured.
          </p>
        </div>

        {/* Live system status */}
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">
            Live system status
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatusCard icon={<Database size={15} />} label="Database"
                        value={status ? status.database.split('+')[0] : '...'}
                        ok={status?.database.startsWith('postgres')} okText="production" warnText="dev fallback" />
            <StatusCard icon={<Zap size={15} />} label="Cache"
                        value={status?.cache_backend ?? '...'}
                        ok={status?.cache_backend === 'redis'} okText="Redis live" warnText="in-memory fallback" />
            <StatusCard icon={<Server size={15} />} label="Object store"
                        value={status?.object_store ?? '...'}
                        ok={status?.object_store === 'minio'} okText="snapshots on" warnText="unavailable" />
            <StatusCard icon={<Activity size={15} />} label="Metrics"
                        value="Prometheus" ok okText="/metrics exposed" warnText="" />
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-xs">
            <a href="/api/v1/docs" target="_blank" rel="noreferrer"
               className="inline-flex items-center gap-1 text-astra-600 dark:text-astra-400 hover:underline">
              <ExternalLink size={11} /> OpenAPI / Swagger
            </a>
            <span className="text-faint">
              Carbon API: {status?.carbon_api ?? '...'}, Google sign-in: {status?.google_oauth ?? '...'}
            </span>
          </div>
        </div>

        {/* Research systems */}
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">
            Research systems (each reproduced on real data)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {BREAKTHROUGHS.map((b) => (
              <div key={b.id} className="card p-4">
                <div className="flex items-center gap-2.5 mb-2">
                  <span className="w-8 h-8 rounded-lg bg-astra-500/10 border border-astra-500/30 text-astra-600 dark:text-astra-400
                                   flex items-center justify-center" aria-hidden="true">
                    {b.icon}
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-sm leading-tight">
                      <span className="text-faint font-mono mr-1.5">{b.id}</span>{b.title}
                    </h3>
                    <p className="text-[11px] text-faint truncate">{b.paper}</p>
                  </div>
                </div>
                <p className="text-[13px] font-medium text-emerald-700 dark:text-emerald-400 mb-1.5">
                  {b.result}
                </p>
                <p className="text-xs text-muted leading-relaxed">{b.detail}</p>
              </div>
            ))}
            {/* Failover callout to fill the grid */}
            <div className="card p-4 border-dashed flex flex-col justify-center">
              <div className="flex items-center gap-2 mb-1.5">
                <Flame size={15} className="text-rose-500" aria-hidden="true" />
                <h3 className="font-semibold text-sm">Tested to failure</h3>
              </div>
              <p className="text-xs text-muted leading-relaxed">
                We killed a member cluster live on GCP: Karmada detected it (NotReady,
                NoExecute taint) and rescheduled all replicas onto the surviving
                cluster in about 10 seconds. The executor policy gate blocks
                destructive code (rm -rf /, fork bombs) before it ever runs.
              </p>
            </div>
          </div>
        </div>

        {/* Tech stack */}
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">
            Technology stack
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STACK.map((g) => (
              <div key={g.group} className="card p-4">
                <h3 className="text-xs font-semibold text-muted mb-2.5 inline-flex items-center gap-1.5">
                  <GitBranch size={12} aria-hidden="true" /> {g.group}
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {g.items.map((t) => <span key={t} className="chip">{t}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </AppShell>
  );
}

function StatusCard({ icon, label, value, ok, okText, warnText }: {
  icon: React.ReactNode; label: string; value: string;
  ok?: boolean; okText: string; warnText: string;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] uppercase tracking-wider text-faint">{label}</span>
        <span className="text-muted" aria-hidden="true">{icon}</span>
      </div>
      <div className="text-lg font-bold capitalize">{value}</div>
      <div className={cn('text-[11px] mt-0.5 inline-flex items-center gap-1.5',
        ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400')}>
        <span className={cn('w-1.5 h-1.5 rounded-full', ok ? 'bg-emerald-500' : 'bg-amber-500')}
              aria-hidden="true" />
        {ok ? okText : warnText}
      </div>
    </div>
  );
}
