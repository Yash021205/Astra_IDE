'use client';
import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import {
  ArrowLeft, Box, ChevronDown, FileCode2, FolderTree, Globe, History,
  Loader2, Play, Settings2, Share2, ShieldCheck, Square,
} from 'lucide-react';
import {
  getWorkspace, startWorkspace, stopWorkspace, updateWorkspace,
  type Workspace, type SandboxTier,
} from '../../../lib/api';
import { useAuth } from '../../../lib/auth';
import { toast } from '../../../lib/toast';
import ThemeToggle from '../../../components/ThemeToggle';
import PresenceBar, { usePresence } from '../../../components/Presence';
import Tooltip from '../../../components/ui/Tooltip';
import { cn } from '../../../lib/utils';

const CollabEditor  = dynamic(() => import('../../../components/CollabEditor'),  { ssr: false });
const FileManager   = dynamic(() => import('../../../components/FileManager'),   { ssr: false });
const PreviewPanel  = dynamic(() => import('../../../components/PreviewPanel'),  { ssr: false });
const ShareModal    = dynamic(() => import('../../../components/ShareModal'),    { ssr: false });
const HistoryModal  = dynamic(() => import('../../../components/HistoryModal'),  { ssr: false });
const SettingsModal = dynamic(() => import('../../../components/SettingsModal'), { ssr: false });

type View = 'files' | 'collab' | 'preview';
const TABS: { id: View; label: string; icon: React.ReactNode }[] = [
  { id: 'files',   label: 'Files',   icon: <FolderTree size={14} /> },
  { id: 'collab',  label: 'Editor',  icon: <FileCode2 size={14} /> },
  { id: 'preview', label: 'Preview', icon: <Globe size={14} /> },
];

const TIER_BADGE: Record<string, string> = {
  runc:        'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  gvisor:      'bg-amber-500/10  text-amber-700  dark:text-amber-300  border-amber-500/30',
  firecracker: 'bg-rose-500/10   text-rose-700   dark:text-rose-300   border-rose-500/30',
};
const STATUS_DOT: Record<string, string> = {
  PENDING: 'bg-faint', PREWARMED: 'bg-astra-500', RUNNING: 'bg-emerald-500',
  STOPPED: 'bg-faint', FAILED: 'bg-rose-500', ARCHIVED: 'bg-faint',
};

export default function WorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { token, user, hydrated } = useAuth();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>('files');
  const [busy, setBusy] = useState(false);

  // Modals + active-file tracking (for presence + settings "open config").
  const [modal, setModal] = useState<'share' | 'history' | 'settings' | null>(null);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [openSignal, setOpenSignal] = useState<{ path: string; n: number }>({ path: '', n: 0 });
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);

  // Warn on browser close/refresh if there are unsaved edits.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsaved) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [hasUnsaved]);

  function goBack() {
    if (hasUnsaved) setConfirmLeave(true);
    else router.push('/dashboard');
  }

  // Live presence across the workspace (who's here + which file).
  const peers = usePresence(
    ws?.yjs_room || `ws-${params.id}`,
    user?.username || 'guest',
    activeFile || `(${view})`,
    user?.avatar_url,
  );

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    refresh();
  }, [token, hydrated]);

  async function refresh() {
    try { setWs(await getWorkspace(Number(params.id))); }
    catch (err: any) { setError(err?.response?.data?.detail || 'Failed to load workspace'); }
  }

  async function changeTier(tier: SandboxTier) {
    if (!ws) return;
    setBusy(true);
    try {
      const updated = await updateWorkspace(ws.id, { sandbox_override: tier });
      setWs(updated);
      toast.success('Sandbox tier updated', `Pinned to ${tier}`);
    } catch (e: any) {
      toast.error('Could not update tier', e?.response?.data?.detail || 'Server error');
    } finally { setBusy(false); }
  }

  if (error) {
    return (
      <main className="min-h-screen grid place-items-center p-8">
        <div className="text-center">
          <p className="text-rose-600 dark:text-rose-400 mb-3">{error}</p>
          <Link href="/dashboard" className="btn-outline"><ArrowLeft size={14} /> Back to dashboard</Link>
        </div>
      </main>
    );
  }
  if (!ws || !user) {
    return <main className="min-h-screen grid place-items-center text-muted">
      <span className="inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Loading workspace</span>
    </main>;
  }

  const isOwner = ws.owner_id === user.id;

  return (
    <div className="h-screen flex flex-col bg-bg overflow-hidden">
      <header className="border-b border-edge bg-surface px-3 sm:px-4 py-2 flex items-center gap-3 flex-wrap">
        <button type="button" onClick={goBack} aria-label="Back to dashboard" className="btn-ghost px-2"><ArrowLeft size={15} /></button>

        <div className="flex items-center gap-2 min-w-0">
          <h1 className="font-semibold truncate max-w-[9rem] sm:max-w-xs">{ws.name}</h1>
          <span className="hidden sm:inline text-xs text-faint font-mono">{ws.language}</span>
          {hasUnsaved && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="Unsaved changes" />}
        </div>

        <span className="inline-flex items-center gap-1.5 text-[11px] text-muted">
          <span className={cn('w-2 h-2 rounded-full', STATUS_DOT[ws.status],
                              ws.status === 'RUNNING' && 'animate-pulse')} aria-hidden="true" />
          {ws.status.toLowerCase()}
        </span>

        {isOwner ? (
          <TierMenu tier={ws.sandbox_tier as SandboxTier} risk={ws.risk_score} busy={busy} onChange={changeTier} />
        ) : (
          <span className={cn('text-[11px] px-2 py-1 rounded-md border font-medium', TIER_BADGE[ws.sandbox_tier])}>
            {ws.sandbox_tier}
          </span>
        )}

        {/* Tabs */}
        <div className="ml-1 inline-flex rounded-lg border border-edge bg-raised/60 p-0.5" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={view === t.id}
                    onClick={() => setView(t.id)}
                    className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                      view === t.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink')}>
              {t.icon}<span className="hidden sm:inline">{t.label}</span>
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <PresenceBar peers={peers} />
          <Tooltip content="Share workspace">
            <button type="button" onClick={() => setModal('share')} className="btn-ghost px-2 py-1.5">
              <Share2 size={15} /> <span className="hidden lg:inline text-xs">Share</span>
            </button>
          </Tooltip>
          {isOwner && (
            <Tooltip content="Change history">
              <button type="button" onClick={() => setModal('history')} aria-label="Change history" className="btn-ghost px-2 py-1.5">
                <History size={15} />
              </button>
            </Tooltip>
          )}
          <Tooltip content="Settings">
            <button type="button" onClick={() => setModal('settings')} aria-label="Settings" className="btn-ghost px-2 py-1.5">
              <Settings2 size={15} />
            </button>
          </Tooltip>
          <ThemeToggle />
          {ws.status !== 'RUNNING' ? (
            <button type="button" onClick={async () => { await startWorkspace(ws.id); refresh(); }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium">
              <Play size={14} /> <span className="hidden sm:inline">Start</span>
            </button>
          ) : (
            <button type="button" onClick={async () => { await stopWorkspace(ws.id); refresh(); }}
                    className="btn-outline px-3 py-1.5 text-sm">
              <Square size={14} /> <span className="hidden sm:inline">Stop</span>
            </button>
          )}
        </div>
      </header>

      {/* All views stay mounted so the terminal session, open file and unsaved
          edits persist when you switch tabs or go to Preview/Editor and back. */}
      <section className="flex-1 min-h-0 relative" role="tabpanel">
        <div className={cn('absolute inset-0', view !== 'files' && 'hidden')}>
          <FileManager workspaceId={ws.id} frozen={!!ws.frozen}
                       onActiveFile={setActiveFile} openSignal={openSignal}
                       onDirtyChange={setHasUnsaved} />
        </div>
        <div className={cn('absolute inset-0', view !== 'collab' && 'hidden')}>
          <CollabEditor
            workspaceId={ws.id} room={ws.yjs_room} language={ws.language}
            initialCode={undefined} username={user.username}
            isOwner={isOwner} status={ws.status} sandbox={ws.sandbox_tier}
          />
        </div>
        <div className={cn('absolute inset-0', view !== 'preview' && 'hidden')}>
          <PreviewPanel workspaceId={ws.id} onClose={() => setView('files')} />
        </div>
      </section>

      {modal === 'share' && <ShareModal workspaceId={ws.id} isOwner={isOwner} onClose={() => setModal(null)} />}
      {modal === 'history' && <HistoryModal workspaceId={ws.id} onClose={() => setModal(null)} />}
      {modal === 'settings' && (
        <SettingsModal ws={ws} isOwner={isOwner} onChanged={setWs}
                       onClose={() => setModal(null)}
                       onOpenFile={(p) => { setView('files'); setOpenSignal((s) => ({ path: p, n: s.n + 1 })); }} />
      )}

      {confirmLeave && (
        <div className="fixed inset-0 z-[70] grid place-items-center p-4 bg-black/55 backdrop-blur-sm"
             role="dialog" aria-modal="true" onClick={() => setConfirmLeave(false)}>
          <div className="card p-5 max-w-sm w-full shadow-pop" onClick={(e) => e.stopPropagation()}>
            <h3 className="t-h3 mb-1.5">Leave with unsaved changes?</h3>
            <p className="text-sm text-muted mb-5">
              You have edits that haven&apos;t been saved. Leaving now will discard them.
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmLeave(false)} className="btn-outline px-3 py-1.5 text-sm">
                Cancel
              </button>
              <button type="button" onClick={() => router.push('/dashboard')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium">
                Discard &amp; leave
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TierMenu({ tier, risk, busy, onChange }: {
  tier: SandboxTier; risk: number; busy: boolean; onChange: (t: SandboxTier) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const OPTS: { id: SandboxTier; label: string; sub: string; icon: React.ReactNode }[] = [
    { id: 'runc',        label: 'runc',        sub: 'fastest, shared kernel', icon: <Box size={14} /> },
    { id: 'gvisor',      label: 'gVisor',      sub: 'user-space kernel',      icon: <ShieldCheck size={14} /> },
    { id: 'firecracker', label: 'Firecracker', sub: 'dedicated microVM',      icon: <ShieldCheck size={14} /> },
  ];
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)} disabled={busy}
              aria-haspopup="menu" aria-expanded={open}
              title={`Sandbox tier (risk ${risk.toFixed(2)}). Click to re-pin.`}
              className={cn('inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md border font-medium', TIER_BADGE[tier])}>
        {busy ? <Loader2 size={11} className="animate-spin" /> : <ShieldCheck size={11} />}
        {tier}<ChevronDown size={12} />
      </button>
      {open && (
        <div role="menu" className="absolute left-0 top-full mt-1.5 z-50 w-56 card p-1.5 shadow-pop">
          <div className="px-2.5 py-1.5 text-[11px] text-faint border-b border-edge mb-1">
            Adaptive policy scored risk <span className="font-mono text-ink">{risk.toFixed(2)}</span>. Pin a tier to override:
          </div>
          {OPTS.map((o) => (
            <button key={o.id} type="button" role="menuitem" onClick={() => { onChange(o.id); setOpen(false); }}
                    className={cn('w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-raised',
                      tier === o.id && 'bg-astra-500/10')}>
              <span className="text-muted">{o.icon}</span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">{o.label}</span>
                <span className="block text-[11px] text-faint">{o.sub}</span>
              </span>
              {tier === o.id && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-astra-500" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
