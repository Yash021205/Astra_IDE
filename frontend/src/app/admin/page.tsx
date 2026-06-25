'use client';
// Admin overview — all users, their assigned resources, and which of the seven
// breakthroughs each has exercised. Admin-only (redirects others).

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Users, Boxes, Activity, BarChart3, ChevronDown, Cpu, MemoryStick } from 'lucide-react';

import AppShell from '../../components/AppShell';
import { Avatar } from '../../components/AvatarInline';
import { getAdminUsers, type AdminOverview, type AdminUser } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatRel } from '../../lib/time';
import { cn } from '../../lib/utils';

const TIER_TONE: Record<string, string> = {
  runc: 'text-emerald-600 dark:text-emerald-400',
  gvisor: 'text-amber-600 dark:text-amber-400',
  firecracker: 'text-rose-600 dark:text-rose-400',
};

export default function AdminPage() {
  const router = useRouter();
  const { token, user, hydrated } = useAuth();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    if (user && !user.is_admin) { router.push('/dashboard'); return; }
    getAdminUsers().then(setData).catch((e) =>
      setError(e?.response?.data?.detail || 'Failed to load admin data'));
  }, [token, hydrated, user]);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8 space-y-6">
        <div>
          <h1 className="t-h1 flex items-center gap-2.5">
            <Shield className="text-amber-600 dark:text-amber-400" size={26} aria-hidden="true" />
            Admin
          </h1>
          <p className="text-sm text-muted mt-1">
            Every user, their assigned resources, and the breakthroughs they have exercised.
          </p>
        </div>

        {error && <div className="card p-4 text-sm text-rose-600 dark:text-rose-400">{error}</div>}

        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Stat icon={<Users size={16} />} label="Users" value={data.total_users} />
              <Stat icon={<Boxes size={16} />} label="Workspaces" value={data.total_workspaces} />
              <Stat icon={<Activity size={16} />} label="Running" value={data.running_workspaces} />
              <Stat icon={<Activity size={16} />} label="Edits logged" value={data.total_edits} />
              <Stat icon={<BarChart3 size={16} />} label="Benchmark runs" value={data.total_benchmark_runs} />
            </div>

            <div className="space-y-3">
              {data.users.map((u) => <UserRow key={u.id} u={u} />)}
            </div>
          </>
        )}
        {!data && !error && <p className="text-faint text-sm">Loading…</p>}
      </section>
    </AppShell>
  );
}

function UserRow({ u }: { u: AdminUser }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-raised/50 transition-colors">
        <Avatar user={u} size={36} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">{u.username}</span>
            {u.is_admin && <span className="chip border-amber-500/40 text-amber-600 dark:text-amber-300">admin</span>}
          </div>
          <div className="text-xs text-faint truncate">{u.email} · joined {formatRel(u.created_at)}</div>
        </div>
        <div className="hidden sm:flex items-center gap-4 text-xs text-muted">
          <span title="Workspaces"><Boxes size={12} className="inline mr-1" />{u.workspace_count}</span>
          <span title="Requested CPU cores"><Cpu size={12} className="inline mr-1" />{u.total_cpu}</span>
          <span title="Requested memory"><MemoryStick size={12} className="inline mr-1" />{u.total_mem_mb} MB</span>
          <span title="Trust score" className="font-mono">trust {u.trust_score.toFixed(2)}</span>
        </div>
        <ChevronDown size={16} className={cn('text-faint transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-edge pt-3 space-y-3">
          {/* Features */}
          <div>
            <p className="t-overline text-faint mb-1.5">Breakthroughs exercised</p>
            <div className="flex flex-wrap gap-1.5">
              {u.features.length === 0 && <span className="text-xs text-faint">None yet.</span>}
              {u.features.map((f) => (
                <span key={f} className="chip border-astra-500/40 text-astra-700 dark:text-astra-300">{f}</span>
              ))}
            </div>
          </div>

          {/* Resource summary */}
          <div className="flex flex-wrap gap-4 text-xs text-muted">
            <span>Tiers: <b className={TIER_TONE.runc}>{u.tiers.runc ?? 0} runc</b> · <b className={TIER_TONE.gvisor}>{u.tiers.gvisor ?? 0} gVisor</b> · <b className={TIER_TONE.firecracker}>{u.tiers.firecracker ?? 0} FC</b></span>
            <span>Edits: <b className="text-ink">{u.edits}</b></span>
            <span>Shares: <b className="text-ink">{u.shares}</b></span>
            <span>Benchmark runs: <b className="text-ink">{u.benchmark_runs}</b></span>
          </div>

          {/* Workspaces */}
          {u.workspaces.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-faint">
                  <tr>
                    <th className="text-left py-1.5 pr-4">Workspace</th>
                    <th className="text-left py-1.5 pr-4">Lang</th>
                    <th className="text-left py-1.5 pr-4">Tier</th>
                    <th className="text-left py-1.5 pr-4">Status</th>
                    <th className="text-right py-1.5 pr-4">CPU</th>
                    <th className="text-right py-1.5 pr-4">Mem</th>
                    <th className="text-left py-1.5">Cluster</th>
                  </tr>
                </thead>
                <tbody>
                  {u.workspaces.map((w) => (
                    <tr key={w.id} className="border-t border-edge">
                      <td className="py-1.5 pr-4 truncate max-w-[10rem]">{w.name}</td>
                      <td className="py-1.5 pr-4 text-muted">{w.language}</td>
                      <td className={cn('py-1.5 pr-4 font-medium', TIER_TONE[w.sandbox_tier])}>{w.sandbox_tier}</td>
                      <td className="py-1.5 pr-4 text-muted">{w.status.toLowerCase()}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{w.cpu_cores ?? '—'}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{w.memory_mb ?? '—'}</td>
                      <td className="py-1.5 text-faint font-mono">{w.cluster_id ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] uppercase tracking-wider text-faint">{label}</span>
        <span className="text-muted">{icon}</span>
      </div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}
