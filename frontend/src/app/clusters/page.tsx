'use client';
// Cluster topology page — interactive magnetic visualization of the
// multi-cluster Kubernetes federation that ASTRA-IDE schedules across.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { Cpu, Network, Zap, Activity, Leaf } from 'lucide-react';

import ClusterCanvas, { type ClusterNode, type ClusterEdge } from '../../components/ui/ClusterCanvas';
import ThreeDCard from '../../components/ui/ThreeDCard';
import ActivityFeed from '../../components/ActivityFeed';
import {
  listWorkspaces, getNodeMetrics, type Workspace, type MetricsSnapshot,
} from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { cn } from '../../lib/utils';

const METRICS_POLL_MS = 4000;

export default function ClustersPage() {
  const router = useRouter();
  const { token, user, hydrated, clearSession } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [metrics, setMetrics]       = useState<MetricsSnapshot | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    listWorkspaces().then(setWorkspaces).catch(() => {});

    let cancelled = false;
    async function pollMetrics() {
      try {
        const snap = await getNodeMetrics();
        if (!cancelled) setMetrics(snap);
      } catch { /* ignore — backend may still be coming up */ }
    }
    pollMetrics();
    const id = setInterval(pollMetrics, METRICS_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, hydrated]);

  // Derive carbon from the live metrics snapshot (more accurate than hitting
  // the carbon API ourselves — the backend already refreshes it on a schedule)
  const carbonA = metrics?.clusters.find((c) => c.cluster_id === 'cluster-a')?.carbon_gco2 ?? null;
  const carbonB = metrics?.clusters.find((c) => c.cluster_id === 'cluster-b')?.carbon_gco2 ?? null;

  // Build the topology from the user's workspaces — each workspace
  // becomes a pod attached to one of the two clusters.
  const { nodes, edges } = buildTopology(workspaces);

  // Stats
  const sandboxCounts = workspaces.reduce((acc, w) => {
    acc[w.sandbox_tier] = (acc[w.sandbox_tier] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const runningCount = workspaces.filter((w) => w.status === 'RUNNING').length;

  return (
    <main className="min-h-screen relative">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(59,130,246,0.08),_transparent_50%)]" />

      <header className="relative border-b border-slate-800 px-6 py-3 flex items-center justify-between bg-slate-950/60 backdrop-blur">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/logo.png" alt="ASTRA-IDE" width={28} height={28} className="rounded" />
            <span className="text-base font-bold tracking-tight">ASTRA<span className="text-astra-500">-IDE</span></span>
          </Link>
          <nav className="hidden md:flex items-center gap-1 text-sm ml-2">
            <Link href="/dashboard"  className="px-3 py-1.5 rounded text-slate-300 hover:bg-slate-800/40">Workspaces</Link>
            <Link href="/clusters"   className="px-3 py-1.5 rounded text-astra-300 bg-slate-800/60">Clusters</Link>
            <Link href="/benchmarks" className="px-3 py-1.5 rounded text-slate-300 hover:bg-slate-800/40">Benchmarks</Link>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-400">@{user?.username}</span>
          <button onClick={() => { clearSession(); router.push('/'); }} type="button"
                  className="px-3 py-1.5 rounded border border-slate-700 hover:bg-slate-900">
            Log out
          </button>
        </div>
      </header>

      <section className="relative max-w-7xl mx-auto px-6 py-8 space-y-8">
        <div>
          <motion.h1
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="text-3xl font-bold"
          >
            Cluster topology
          </motion.h1>
          <p className="text-sm text-slate-400 mt-1">
            Hover over a node to inspect it. Nodes are magnetic — they're attracted to your cursor.
          </p>
        </div>

        <ClusterCanvas nodes={nodes} edges={edges} height={500} />

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<Cpu      size={20} className="text-astra-400"  />}
            label="Workspaces" value={workspaces.length}
            sub={`${runningCount} running`}
          />
          <StatCard
            icon={<Network  size={20} className="text-purple-400" />}
            label="Clusters" value={2}
            sub="cluster-a · cluster-b"
          />
          <StatCard
            icon={<Activity size={20} className="text-emerald-400" />}
            label="Sandbox mix"
            value={`${sandboxCounts.runc ?? 0}/${sandboxCounts.gvisor ?? 0}/${sandboxCounts.firecracker ?? 0}`}
            sub="runc / gvisor / fc"
          />
          <StatCard
            icon={<Leaf     size={20} className="text-lime-400"    />}
            label="Carbon (gCO₂/kWh)"
            value={carbonA !== null ? carbonA.toFixed(0) : '—'}
            sub={`cluster-b: ${carbonB !== null ? carbonB.toFixed(0) : '—'}`}
          />
        </div>

        {/* Live node metrics — CPU, memory, network — polled every 4s */}
        {metrics && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {metrics.clusters.flatMap((c) =>
              c.nodes.map((n) => (
                <NodeMetricCard key={`${c.cluster_id}/${n.node_name}`} node={n} />
              )),
            )}
          </div>
        )}

        {/* Per-cluster cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ClusterDetailCard
            name="cluster-a"
            location="DK-DK1 (Denmark West)"
            carbon={carbonA}
            podCount={workspaces.filter((w) => w.cluster_id === 'local' || w.cluster_id === 'cluster-a').length}
            accent="from-emerald-500/20"
          />
          <ClusterDetailCard
            name="cluster-b"
            location="IN-NO (India North)"
            carbon={carbonB}
            podCount={workspaces.filter((w) => w.cluster_id === 'cluster-b').length}
            accent="from-purple-500/20"
          />
        </div>

        {/* Live scheduler / sandbox / eBPF activity feed */}
        <ActivityFeed className="mt-2" />

        <p className="text-xs text-slate-500 italic text-center pt-4">
          Topology renders the workspaces visible to your account. eBPF telemetry &amp; PPO decisions
          will animate edges in real-time once the Phase 3 collector is wired up.
        </p>
      </section>
    </main>
  );
}

function StatCard({ icon, label, value, sub }:
  { icon: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <ThreeDCard intensity={5}>
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur hover:border-astra-600/40 transition-colors">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs uppercase tracking-wider text-slate-500">{label}</span>
          {icon}
        </div>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
      </div>
    </ThreeDCard>
  );
}

function NodeMetricCard({ node }: { node: NodeMetricsT }) {
  return (
    <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/40 backdrop-blur">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-mono text-slate-300">{node.node_name}</span>
        <span className="text-[10px] text-slate-500">{node.cluster_id}</span>
      </div>
      <Bar label="CPU"      value={node.cpu_util}    color="bg-astra-500" />
      <Bar label="Memory"   value={node.memory_util} color="bg-purple-500" />
      <div className="flex justify-between text-[10px] text-slate-400 mt-2 font-mono">
        <span>runq {node.run_queue_len.toFixed(1)}</span>
        <span>net {node.network_kbps.toFixed(0)}KiB/s</span>
        <span>pods {node.active_pods}</span>
      </div>
    </div>
  );
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="mb-1.5">
      <div className="flex justify-between text-[10px] text-slate-400 mb-0.5">
        <span>{label}</span>
        <span className="font-mono">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={cn('h-full transition-all duration-500', color)}
             style={{ width: `${Math.min(100, value * 100)}%` }} />
      </div>
    </div>
  );
}

// Type alias to satisfy TS — same shape as api.NodeMetrics
type NodeMetricsT = {
  cluster_id:    string;
  node_name:     string;
  cpu_util:      number;
  memory_util:   number;
  network_kbps:  number;
  run_queue_len: number;
  active_pods:   number;
};

function ClusterDetailCard({
  name, location, carbon, podCount, accent,
}: {
  name:     string;
  location: string;
  carbon:   number | null;
  podCount: number;
  accent:   string;
}) {
  const carbonClass = (v: number | null) => {
    if (v === null) return 'text-slate-400';
    if (v < 100)    return 'text-emerald-400';
    if (v < 300)    return 'text-amber-400';
    return 'text-rose-400';
  };

  return (
    <div className={cn(
      'p-5 rounded-xl border border-slate-800 bg-gradient-to-br to-transparent backdrop-blur',
      accent,
    )}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h2 className="text-xl font-bold">{name}</h2>
          <p className="text-xs text-slate-400 mt-0.5">{location}</p>
        </div>
        <Zap className="text-astra-400" size={20} />
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-slate-500">Active pods</div>
          <div className="text-2xl font-bold tabular-nums">{podCount}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Carbon intensity</div>
          <div className={cn('text-2xl font-bold tabular-nums', carbonClass(carbon))}>
            {carbon !== null ? carbon.toFixed(0) : '—'}
            <span className="text-xs ml-1 text-slate-500">gCO₂/kWh</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Topology builder ─────────────────────────────────────────────────────────

function buildTopology(workspaces: Workspace[]): { nodes: ClusterNode[]; edges: ClusterEdge[] } {
  const nodes: ClusterNode[] = [];
  const edges: ClusterEdge[] = [];

  // Karmada control plane in the middle
  nodes.push({
    id: 'karmada', label: 'karmada', cluster: 'global',
    type: 'control', x: 0.5, y: 0.5,
  });

  // Cluster A on the left
  nodes.push({
    id: 'ctrl-a', label: 'cluster-a-control', cluster: 'cluster-a',
    type: 'control', x: 0.18, y: 0.5,
  });
  nodes.push({
    id: 'worker-a1', label: 'worker-a-1', cluster: 'cluster-a',
    type: 'worker', x: 0.10, y: 0.30,
  });
  nodes.push({
    id: 'worker-a2', label: 'worker-a-2', cluster: 'cluster-a',
    type: 'worker', x: 0.10, y: 0.70,
  });

  // Cluster B on the right
  nodes.push({
    id: 'ctrl-b', label: 'cluster-b-control', cluster: 'cluster-b',
    type: 'control', x: 0.82, y: 0.5,
  });
  nodes.push({
    id: 'worker-b1', label: 'worker-b-1', cluster: 'cluster-b',
    type: 'worker', x: 0.90, y: 0.30,
  });
  nodes.push({
    id: 'worker-b2', label: 'worker-b-2', cluster: 'cluster-b',
    type: 'worker', x: 0.90, y: 0.70,
  });

  // Inter-cluster edges
  edges.push({ from: 'karmada', to: 'ctrl-a', flow: 0.9, kind: 'control' });
  edges.push({ from: 'karmada', to: 'ctrl-b', flow: 0.9, kind: 'control' });
  edges.push({ from: 'ctrl-a', to: 'worker-a1', flow: 0.6, kind: 'control' });
  edges.push({ from: 'ctrl-a', to: 'worker-a2', flow: 0.6, kind: 'control' });
  edges.push({ from: 'ctrl-b', to: 'worker-b1', flow: 0.6, kind: 'control' });
  edges.push({ from: 'ctrl-b', to: 'worker-b2', flow: 0.6, kind: 'control' });

  // Pods — distribute workspaces across the 4 workers
  const workers = ['worker-a1', 'worker-a2', 'worker-b1', 'worker-b2'];
  const podPositions: Record<string, { x: number; y: number }> = {
    'worker-a1': { x: 0.04, y: 0.16 },
    'worker-a2': { x: 0.04, y: 0.84 },
    'worker-b1': { x: 0.96, y: 0.16 },
    'worker-b2': { x: 0.96, y: 0.84 },
  };

  workspaces.slice(0, 12).forEach((w, idx) => {
    const wn = workers[idx % workers.length];
    const base = podPositions[wn];
    const offset = (idx % 3) * 0.04 - 0.04;
    nodes.push({
      id: `pod-${w.id}`, label: w.name, cluster: w.cluster_id,
      type: 'pod', sandbox: w.sandbox_tier,
      x: base.x + (Math.random() - 0.5) * 0.04,
      y: base.y + offset,
    });
    edges.push({
      from: wn, to: `pod-${w.id}`, flow: 0.3, kind: 'telemetry',
    });
  });

  // If user has no workspaces yet, show 3 demo pods so the page isn't empty
  if (workspaces.length === 0) {
    const demo = [
      { id: 'demo-1', label: 'demo-runc',        sandbox: 'runc'        as const, x: 0.06, y: 0.20 },
      { id: 'demo-2', label: 'demo-gvisor',      sandbox: 'gvisor'      as const, x: 0.95, y: 0.20 },
      { id: 'demo-3', label: 'demo-firecracker', sandbox: 'firecracker' as const, x: 0.95, y: 0.80 },
    ];
    demo.forEach((d) => {
      nodes.push({
        id: d.id, label: d.label, cluster: 'demo',
        type: 'pod', sandbox: d.sandbox, x: d.x, y: d.y,
      });
    });
    edges.push({ from: 'worker-a1', to: 'demo-1', flow: 0.5, kind: 'telemetry' });
    edges.push({ from: 'worker-b1', to: 'demo-2', flow: 0.5, kind: 'telemetry' });
    edges.push({ from: 'worker-b2', to: 'demo-3', flow: 0.5, kind: 'telemetry' });
  }

  return { nodes, edges };
}
