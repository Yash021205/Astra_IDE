'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Box, Flame, GitFork, Play, Plus, Shield, Sparkles, Square, Trash2, Users, X, Zap,
} from 'lucide-react';
import {
  SiPython, SiCplusplus, SiJavascript, SiTypescript,
  SiGo, SiRust, SiOpenjdk, SiGnubash,
} from 'react-icons/si';

import {
  listWorkspaces, createWorkspace, deleteWorkspace, forkWorkspace,
  startWorkspace, stopWorkspace, type Workspace, type SandboxTier,
} from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { toast } from '../../lib/toast';
import AppShell from '../../components/AppShell';
import { cn } from '../../lib/utils';
import { templatesForLanguage, defaultTemplateFor } from '../../lib/templates';

// Official language marks (Simple Icons) with brand colors.
const LANGUAGES = [
  { id: 'python',     label: 'Python',     Icon: SiPython,     color: '#3776AB' },
  { id: 'cpp',        label: 'C++',        Icon: SiCplusplus,  color: '#00599C' },
  { id: 'javascript', label: 'JavaScript', Icon: SiJavascript, color: '#b89c00' },
  { id: 'typescript', label: 'TypeScript', Icon: SiTypescript, color: '#3178C6' },
  { id: 'go',         label: 'Go',         Icon: SiGo,         color: '#00ADD8' },
  { id: 'rust',       label: 'Rust',       Icon: SiRust,       color: '#f97316' },
  { id: 'java',       label: 'Java',       Icon: SiOpenjdk,    color: '#e76f51' },
  { id: 'bash',       label: 'Bash',       Icon: SiGnubash,    color: '#4EAA25' },
];

// Isolation modes shown upfront in the create dialog. "auto" is the adaptive
// research path (risk-scored); the rest pin a tier manually.
const TIERS: {
  id: 'auto' | SandboxTier;
  label: string; sub: string; perf: string; isolation: string;
  icon: React.ReactNode;
}[] = [
  { id: 'auto',        label: 'Auto',        sub: 'Adaptive: the risk scorer picks the lightest safe tier', perf: 'optimal', isolation: 'risk-matched', icon: <Sparkles size={15} /> },
  { id: 'runc',        label: 'runc',        sub: 'Standard container, shared kernel',                      perf: 'fastest (~60ms)', isolation: 'baseline',  icon: <Box size={15} /> },
  { id: 'gvisor',      label: 'gVisor',      sub: 'User-space kernel intercepts syscalls',                  perf: 'fast (~150ms)',   isolation: 'strong',    icon: <Shield size={15} /> },
  { id: 'firecracker', label: 'Firecracker', sub: 'Dedicated microVM per workspace',                        perf: '~125ms boot',     isolation: 'strongest', icon: <Flame size={15} /> },
];

const TIER_BADGE: Record<string, string> = {
  runc:        'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  gvisor:      'bg-amber-500/10  text-amber-700  dark:text-amber-300  border-amber-500/30',
  firecracker: 'bg-rose-500/10   text-rose-700   dark:text-rose-300   border-rose-500/30',
};
const TIER_TITLE: Record<string, string> = {
  runc:        'runc: standard container isolation (lowest risk workloads)',
  gvisor:      'gVisor: user-space kernel, syscalls intercepted (medium risk)',
  firecracker: 'Firecracker: dedicated microVM (highest risk workloads)',
};

export default function DashboardPage() {
  const router = useRouter();
  const { token, user, hydrated, clearSession } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  // Create-form state
  const [name, setName] = useState('');
  const [language, setLanguage] = useState('python');
  const [tier, setTier] = useState<'auto' | SandboxTier>('auto');
  const [networkAccess, setNetworkAccess] = useState(false);
  const [filesystemWrite, setFilesystemWrite] = useState(true);
  const [cpu, setCpu] = useState(0.5);
  const [memory, setMemory] = useState(512);
  const [templateId, setTemplateId] = useState<string>(defaultTemplateFor('python')?.id ?? '');

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    refresh();
  }, [token, hydrated]);

  async function refresh() {
    setLoading(true);
    try { setWorkspaces(await listWorkspaces()); }
    catch { clearSession(); router.push('/login'); }
    finally { setLoading(false); }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const template = templatesForLanguage(language).find((t) => t.id === templateId);
      const ws = await createWorkspace({
        name, language,
        network_access: networkAccess,
        filesystem_write: filesystemWrite,
        cpu_request: cpu,
        memory_request: memory,
        initial_code: template?.code ?? '',
        sandbox_override: tier === 'auto' ? null : tier,
      });
      setName(''); setShowCreate(false);
      toast.success('Workspace created',
        tier === 'auto'
          ? `Risk ${ws.risk_score.toFixed(2)}: adaptive policy chose ${ws.sandbox_tier}`
          : `Pinned to ${ws.sandbox_tier} (adaptive would score risk ${ws.risk_score.toFixed(2)})`);
      refresh();
    } catch (e: any) {
      toast.error('Could not create', e?.response?.data?.detail || 'Server error');
    }
  }

  const owned  = workspaces.filter((w) => w.owner_id === user?.id);
  const shared = workspaces.filter((w) => w.owner_id !== user?.id);

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 sm:px-6 py-8">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <div>
            <h1 className="t-h1">Workspaces</h1>
            <p className="text-sm text-muted mt-1">
              {owned.length} owned, {shared.length} shared with you
            </p>
          </div>
          <button type="button" onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus size={16} /> New workspace
          </button>
        </div>

        {workspaces.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            <Stat label="Total" value={workspaces.length} hint="across all clusters" />
            <Stat label="Running" accent="text-emerald-600 dark:text-emerald-400"
                  value={workspaces.filter((w) => w.status === 'RUNNING').length} hint="live now" />
            <Stat label="Sandbox mix"
                  value={`${workspaces.filter((w) => w.sandbox_tier === 'runc').length} / ${workspaces.filter((w) => w.sandbox_tier === 'gvisor').length} / ${workspaces.filter((w) => w.sandbox_tier === 'firecracker').length}`}
                  hint="runc / gVisor / Firecracker" />
            <Stat label="Avg risk" accent="text-amber-600 dark:text-amber-400"
                  value={(workspaces.reduce((s, w) => s + w.risk_score, 0) / workspaces.length).toFixed(2)}
                  hint="0.0 to 1.0 scale" />
          </div>
        )}

        {loading && <CardGridSkeleton />}

        {!loading && workspaces.length === 0 && (
          <div className="card p-16 text-center border-dashed">
            <p className="text-muted mb-1">No workspaces yet.</p>
            <p className="text-sm text-faint">Create your first one to get a risk-scored, sandboxed environment.</p>
          </div>
        )}

        {owned.length > 0 && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">Owned</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
              {owned.map((ws) => <WorkspaceCard key={ws.id} ws={ws} onChange={refresh} isOwner />)}
            </div>
          </>
        )}
        {shared.length > 0 && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-faint mb-3">Shared with you</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {shared.map((ws) => <WorkspaceCard key={ws.id} ws={ws} onChange={refresh} isOwner={false} />)}
            </div>
          </>
        )}
      </section>

      {/* Create dialog */}
      {showCreate && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-start sm:items-center justify-center px-4 py-6 overflow-y-auto"
          onClick={() => setShowCreate(false)}
          role="dialog" aria-modal="true" aria-label="Create workspace"
        >
          <motion.form
            initial={{ scale: 0.97, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            onSubmit={onCreate} onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg card p-6 shadow-pop my-auto"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold">Create workspace</h2>
                <p className="text-sm text-faint">Every option below feeds the risk scorer and scheduler.</p>
              </div>
              <button type="button" onClick={() => setShowCreate(false)} title="Close" aria-label="Close"
                      className="btn-ghost p-1.5"><X size={16} /></button>
            </div>

            <label htmlFor="ws-name" className="block text-xs font-medium text-muted mb-1">Name</label>
            <input id="ws-name" value={name} onChange={(e) => setName(e.target.value)}
                   required minLength={1} placeholder="my-project" className="input-base mb-4" />

            <span className="block text-xs font-medium text-muted mb-1.5">Language</span>
            <div className="grid grid-cols-4 gap-1.5 mb-4" role="radiogroup" aria-label="Language">
              {LANGUAGES.map((l) => (
                <button key={l.id} type="button" role="radio"
                        aria-checked={language === l.id ? 'true' : 'false'}
                        onClick={() => { setLanguage(l.id); setTemplateId(defaultTemplateFor(l.id)?.id ?? ''); }}
                        className={cn(
                          'flex flex-col items-center gap-1.5 px-2 py-2.5 rounded-lg text-xs border transition-colors',
                          language === l.id
                            ? 'border-astra-500 bg-astra-500/10 text-ink'
                            : 'border-edge bg-raised/60 text-muted hover:border-edge-strong',
                        )}>
                  <l.Icon size={17} style={{ color: language === l.id ? l.color : undefined }} />
                  <span>{l.label}</span>
                </button>
              ))}
            </div>

            <span className="block text-xs font-medium text-muted mb-1.5">
              Isolation <span className="text-faint font-normal">(runc / gVisor / Firecracker, or let the risk scorer decide)</span>
            </span>
            <div className="grid grid-cols-2 gap-1.5 mb-4" role="radiogroup" aria-label="Sandbox tier">
              {TIERS.map((t) => (
                <button key={t.id} type="button" role="radio"
                        aria-checked={tier === t.id ? 'true' : 'false'}
                        onClick={() => setTier(t.id)}
                        className={cn(
                          'text-left p-2.5 rounded-lg border transition-colors',
                          tier === t.id
                            ? 'border-astra-500 bg-astra-500/10'
                            : 'border-edge bg-raised/60 hover:border-edge-strong',
                        )}>
                  <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
                    {t.icon} {t.label}
                    {t.id === 'auto' && <span className="chip border-astra-500/40 text-astra-600 dark:text-astra-300">recommended</span>}
                  </span>
                  <span className="block text-[11px] text-faint mt-0.5 leading-snug">{t.sub}</span>
                  <span className="block text-[10px] text-muted mt-1 font-mono">{t.perf} | isolation: {t.isolation}</span>
                </button>
              ))}
            </div>

            {templatesForLanguage(language).length > 0 && (
              <>
                <span className="block text-xs font-medium text-muted mb-1.5">Starter template</span>
                <div className="space-y-1.5 mb-4">
                  {[...templatesForLanguage(language), null].map((t) => (
                    <label key={t?.id ?? 'empty'}
                           className={cn(
                             'flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer text-sm transition-colors',
                             (t ? templateId === t.id : templateId === '')
                               ? 'border-astra-500 bg-astra-500/10'
                               : 'border-edge bg-raised/60 hover:border-edge-strong',
                           )}>
                      <input type="radio" name="template" className="mt-1 accent-blue-600"
                             checked={t ? templateId === t.id : templateId === ''}
                             onChange={() => setTemplateId(t?.id ?? '')} />
                      <span>
                        <span className="block font-medium text-ink">{t?.label ?? 'Empty'}</span>
                        <span className="block text-xs text-faint">{t?.description ?? 'Start from scratch'}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </>
            )}

            <details className="mb-4 group">
              <summary className="cursor-pointer text-xs font-medium text-muted select-none py-1">
                Advanced: resources and permissions
              </summary>
              <div className="mt-2 space-y-3 pl-1">
                <div className="grid grid-cols-2 gap-3">
                  <span className="block">
                    <label htmlFor="ws-cpu" className="block text-xs text-muted mb-1">CPU (cores)</label>
                    <select id="ws-cpu" value={cpu} onChange={(e) => setCpu(parseFloat(e.target.value))}
                            className="input-base">
                      {[0.25, 0.5, 1, 2, 4].map((v) => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </span>
                  <span className="block">
                    <label htmlFor="ws-mem" className="block text-xs text-muted mb-1">Memory (MiB)</label>
                    <select id="ws-mem" value={memory} onChange={(e) => setMemory(parseInt(e.target.value, 10))}
                            className="input-base">
                      {[256, 512, 1024, 2048, 4096].map((v) => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </span>
                </div>
                <label className="flex items-center gap-2.5 text-sm text-ink">
                  <input type="checkbox" checked={networkAccess} className="accent-blue-600 w-4 h-4"
                         onChange={(e) => setNetworkAccess(e.target.checked)} />
                  <span>
                    Network access
                    <span className="block text-xs text-faint">Raises the risk score; Auto may select gVisor or Firecracker</span>
                  </span>
                </label>
                <label className="flex items-center gap-2.5 text-sm text-ink">
                  <input type="checkbox" checked={filesystemWrite} className="accent-blue-600 w-4 h-4"
                         onChange={(e) => setFilesystemWrite(e.target.checked)} />
                  <span>
                    Filesystem write access
                    <span className="block text-xs text-faint">Needed for file creation and package installs</span>
                  </span>
                </label>
              </div>
            </details>

            <div className="flex gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="btn-outline flex-1">Cancel</button>
              <button type="submit" className="btn-primary flex-1">Create workspace</button>
            </div>
          </motion.form>
        </motion.div>
      )}
    </AppShell>
  );
}

function WorkspaceCard({ ws, onChange, isOwner }:
  { ws: Workspace; onChange: () => void; isOwner: boolean }) {
  const statusDot: Record<string, string> = {
    PENDING: 'bg-faint', PREWARMED: 'bg-astra-500', RUNNING: 'bg-emerald-500',
    STOPPED: 'bg-faint', FAILED: 'bg-rose-500', ARCHIVED: 'bg-faint',
  };
  const lang = LANGUAGES.find((l) => l.id === ws.language);

  return (
    <div className="card p-4 flex flex-col hover:border-astra-500/50 transition-colors">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <Link href={`/workspaces/${ws.id}`}
              className="font-semibold text-ink hover:text-astra-600 dark:hover:text-astra-400 flex-1 truncate">
          {ws.name}
        </Link>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-muted shrink-0"
              title={`Status: ${ws.status}`}>
          <span className={cn('w-2 h-2 rounded-full', statusDot[ws.status],
                              ws.status === 'RUNNING' && 'animate-pulse')} aria-hidden="true" />
          {ws.status.toLowerCase()}
        </span>
      </div>

      <p className="text-xs text-faint mb-3 flex items-center gap-1.5 flex-wrap">
        {lang && <lang.Icon size={12} style={{ color: lang.color }} aria-hidden="true" />}
        <span>{lang?.label ?? ws.language}</span>
        {!isOwner && (
          <span className="inline-flex items-center gap-1 text-astra-600 dark:text-astra-400">
            <Users size={11} /> shared
          </span>
        )}
        {ws.forked_from_id && (
          <span className="inline-flex items-center gap-1 text-purple-600 dark:text-purple-400"
                title={`Forked from workspace #${ws.forked_from_id}`}>
            <GitFork size={11} /> forked from #{ws.forked_from_id}
          </span>
        )}
      </p>

      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className={cn('text-[10px] px-1.5 py-0.5 rounded-md border font-medium', TIER_BADGE[ws.sandbox_tier])}
              title={TIER_TITLE[ws.sandbox_tier]}>
          {ws.sandbox_tier}
        </span>
        <span className="chip" title="Risk score computed by the adaptive sandbox scorer">
          risk {ws.risk_score.toFixed(2)}
        </span>
        <span className="chip">{ws.cpu_request} cpu, {ws.memory_request} MiB</span>
        <span className="chip" title="Placement chosen by the PPO scheduler">{ws.cluster_id}</span>
      </div>

      <div className="flex gap-1.5 text-xs mt-auto">
        {ws.status !== 'RUNNING' ? (
          <button type="button"
                  onClick={async () => { await startWorkspace(ws.id); onChange(); }}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium">
            <Play size={11} /> Start
          </button>
        ) : (
          <button type="button"
                  onClick={async () => { await stopWorkspace(ws.id); onChange(); }}
                  className="btn-outline px-2.5 py-1.5 text-xs">
            <Square size={11} /> Stop
          </button>
        )}
        <Link href={`/workspaces/${ws.id}`}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-astra-600/10 text-astra-700 dark:text-astra-300 hover:bg-astra-600/20 font-medium">
          <Zap size={11} /> Open
        </Link>
        <button type="button"
                onClick={async () => {
                  try {
                    const f = await forkWorkspace(ws.id);
                    toast.success('Forked', `Created "${f.name}" as your own copy`);
                    onChange();
                  } catch (e: any) { toast.error('Fork failed', e?.response?.data?.detail || 'Server error'); }
                }}
                title="Fork this workspace into your own copy"
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-muted hover:bg-raised hover:text-ink font-medium">
          <GitFork size={11} /> Fork
        </button>
        {isOwner && (
          <button type="button"
                  onClick={async () => {
                    if (confirm(`Delete workspace "${ws.name}"?`)) {
                      try { await deleteWorkspace(ws.id); toast.success('Workspace deleted', ws.name); onChange(); }
                      catch (e: any) { toast.error('Delete failed', e?.response?.data?.detail || 'Server error'); }
                    }
                  }}
                  title={`Delete ${ws.name}`}
                  className="ml-auto inline-flex items-center gap-1 px-2 py-1.5 rounded-lg text-rose-600 dark:text-rose-400 hover:bg-rose-500/10">
            <Trash2 size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, hint, accent }:
  { label: string; value: string | number; hint?: string; accent?: string }) {
  return (
    <div className="card p-4">
      <div className="text-[11px] uppercase tracking-wider text-faint mb-1">{label}</div>
      <div className={cn('text-2xl font-bold tabular-nums', accent)}>{value}</div>
      {hint && <div className="text-xs text-faint mt-0.5">{hint}</div>}
    </div>
  );
}

function CardGridSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card p-4 animate-pulse">
          <div className="h-4 w-2/3 rounded bg-raised mb-3" />
          <div className="h-3 w-1/3 rounded bg-raised mb-4" />
          <div className="flex gap-1.5"><div className="h-5 w-14 rounded bg-raised" /><div className="h-5 w-20 rounded bg-raised" /></div>
        </div>
      ))}
    </div>
  );
}
