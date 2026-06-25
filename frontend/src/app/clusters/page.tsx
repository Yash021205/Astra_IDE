'use client';
// Clusters: a live operations console for the multi-cluster federation that
// ASTRA-IDE schedules across. Per-cluster cards show region + grid carbon;
// each node row shows live CPU / memory / network with utilization bars
// (polled every 4s from /metrics/nodes, the same telemetry the PPO scheduler
// consumes). The activity feed streams scheduler / eBPF / sandbox events.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Boxes, Cpu, Globe2, Layers, Leaf, MemoryStick, Network, Server, Wifi,
} from 'lucide-react';

import AppShell from '../../components/AppShell';
import ActivityFeed from '../../components/ActivityFeed';
import FederationTopology from '../../components/FederationTopology';
import {
  listWorkspaces, getNodeMetrics,
  type Workspace, type MetricsSnapshot, type NodeMetrics, type ClusterMetrics,
} from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { cn } from '../../lib/utils';

const METRICS_POLL_MS = 4000;

// Region metadata for the demo federation (4 Karmada members).
const CLUSTER_META: Record<string, { region: string; flagLabel: string }> = {
  'cluster-a': { region: 'Denmark (west)',  flagLabel: 'low-carbon grid' },
  'cluster-b': { region: 'India (north)',   flagLabel: 'fossil-heavy grid' },
  'cluster-c': { region: 'California (US)',  flagLabel: 'mixed grid' },
  'cluster-d': { region: 'Singapore',       flagLabel: 'mixed grid' },
};

export default function ClustersPage() {
  const router = useRouter();
  const { token, hydrated } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    listWorkspaces().then(setWorkspaces).catch(() => {});

    let cancelled = false;
    async function poll() {
      try {
        const snap = await getNodeMetrics();
        if (!cancelled) setMetrics(snap);
      } catch { /* backend may still be starting */ }
    }
    poll();
    const id = setInterval(poll, METRICS_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, hydrated]);

  const running = workspaces.filter((w) => w.status === 'RUNNING').length;
  const tiers = workspaces.reduce((acc, w) => {
    acc[w.sandbox_tier] = (acc[w.sandbox_tier] || 0) + 1; return acc;
  }, {} as Record<string, number>);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8 space-y-6">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="t-h1">Clusters</h1>
            <p className="text-sm text-muted mt-1">
              Live federation telemetry, the exact input the PPO scheduler learns from (refreshed every {METRICS_POLL_MS / 1000}s).
            </p>
          </div>
          <span className="chip py-1" title="Workloads are propagated across member clusters with Karmada">
            <Layers size={12} /> Karmada federation
          </span>
        </div>

        {/* Top stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat icon={<Boxes size={16} className="text-astra-600 dark:text-astra-400" />}
                label="Workspaces" value={workspaces.length} sub={`${running} running`} />
          <Stat icon={<Globe2 size={16} className="text-purple-600 dark:text-purple-400" />}
                label="Clusters" value={metrics?.clusters.length ?? 4} sub="federated regions" />
          <Stat icon={<Server size={16} className="text-emerald-600 dark:text-emerald-400" />}
                label="Nodes" value={metrics ? metrics.clusters.reduce((s, c) => s + c.nodes.length, 0) : '...'}
                sub="reporting telemetry" />
          <Stat icon={<Cpu size={16} className="text-amber-600 dark:text-amber-400" />}
                label="Sandbox mix"
                value={`${tiers.runc ?? 0} / ${tiers.gvisor ?? 0} / ${tiers.firecracker ?? 0}`}
                sub="runc / gVisor / Firecracker" />
        </div>

        {/* Federation topology */}
        {metrics && <FederationTopology clusters={metrics.clusters} />}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* Cluster cards */}
          <div className="lg:col-span-2 space-y-5">
            {!metrics && <ClusterSkeleton />}
            {metrics?.clusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c}
                           podsHere={workspaces.filter((w) => w.cluster_id === c.cluster_id).length} />
            ))}
            <p className="text-xs text-faint leading-relaxed px-1">
              Greener regions are preferred by the carbon-aware policy: deferrable workloads shift
              toward the cluster with the lower grid intensity. If a cluster fails, Karmada
              reschedules its workloads onto the survivors (verified live with a 2-cluster kill test).
            </p>
          </div>

          {/* Activity feed */}
          <ActivityFeed className="lg:col-span-1" />
        </div>
      </section>
    </AppShell>
  );
}

function ClusterCard({ cluster, podsHere }: { cluster: ClusterMetrics; podsHere: number }) {
  const meta = CLUSTER_META[cluster.cluster_id] ?? { region: cluster.location, flagLabel: '' };
  const carbon = cluster.carbon_gco2;
  const carbonTone =
    carbon < 150 ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
    : carbon < 400 ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30'
    : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30';

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-edge flex items-center gap-3 flex-wrap">
        <span className="w-8 h-8 rounded-lg bg-astra-500/10 border border-astra-500/30
                         flex items-center justify-center" aria-hidden="true">
          <Server size={15} className="text-astra-600 dark:text-astra-400" />
        </span>
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-sm">{cluster.cluster_id}</h2>
          <p className="text-xs text-faint">{meta.region}</p>
        </div>
        <span className={cn('text-[11px] px-2 py-1 rounded-md border font-medium inline-flex items-center gap-1.5', carbonTone)}
              title={`Live grid carbon intensity (${meta.flagLabel})`}>
          <Leaf size={11} /> {carbon.toFixed(0)} gCO2/kWh
        </span>
        <span className="chip py-1" title="Workspaces currently placed on this cluster">
          {podsHere} workspaces, {cluster.total_pods} pods
        </span>
      </div>

      <ul className="divide-y divide-edge">
        {cluster.nodes.map((n) => <NodeRow key={n.node_name} node={n} />)}
      </ul>
    </div>
  );
}

function NodeRow({ node }: { node: NodeMetrics }) {
  return (
    <li className="px-4 py-3 grid grid-cols-1 sm:grid-cols-[10rem_1fr_1fr_1fr_5rem] gap-x-5 gap-y-2 items-center">
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('w-2 h-2 rounded-full shrink-0',
          node.cpu_util > 0.85 ? 'bg-rose-500' : 'bg-emerald-500')} aria-hidden="true" />
        <span className="text-sm font-mono truncate">{node.node_name}</span>
      </div>
      <Meter icon={<Cpu size={11} />} label="CPU" pct={node.cpu_util} />
      <Meter icon={<MemoryStick size={11} />} label="Memory" pct={node.memory_util} />
      <Meter icon={<Wifi size={11} />} label="Net" pct={Math.min(node.network_kbps / 1000, 1)}
             display={`${node.network_kbps.toFixed(0)} KiB/s`} />
      <span className="text-[11px] text-faint font-mono justify-self-start sm:justify-self-end"
            title="Active pods / run-queue length">
        {node.active_pods} pods
      </span>
    </li>
  );
}

function Meter({ icon, label, pct, display }:
  { icon: React.ReactNode; label: string; pct: number; display?: string }) {
  const p = Math.max(0, Math.min(1, pct));
  const tone = p > 0.85 ? 'bg-rose-500' : p > 0.6 ? 'bg-amber-500' : 'bg-astra-500';
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] text-faint mb-1">
        <span className="inline-flex items-center gap-1">{icon} {label}</span>
        <span className="font-mono">{display ?? `${(p * 100).toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 rounded-full bg-raised overflow-hidden"
           role="meter" aria-label={label} aria-valuenow={Math.round(p * 100)}
           aria-valuemin={0} aria-valuemax={100}>
        <div className={cn('h-full rounded-full transition-[width] duration-700 ease-out', tone)}
             style={{ width: `${p * 100}%` }} />
      </div>
    </div>
  );
}

function Stat({ icon, label, value, sub }:
  { icon: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] uppercase tracking-wider text-faint">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-faint mt-0.5">{sub}</div>}
    </div>
  );
}

function ClusterSkeleton() {
  return (
    <div className="card p-4 animate-pulse" aria-hidden="true">
      <div className="h-4 w-40 rounded bg-raised mb-4" />
      {[0, 1].map((i) => (
        <div key={i} className="h-3 w-full rounded bg-raised mb-3" />
      ))}
    </div>
  );
}
