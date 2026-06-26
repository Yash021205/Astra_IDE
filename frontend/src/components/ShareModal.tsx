'use client';
// Share a workspace: invite collaborators (shown with email + avatar), and —
// for the owner — choose which files to EXCLUDE from sharing (e.g. .env).
// Everything is shared by default; unchecking a file hides it from members.

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Check, EyeOff, FileCode2, Loader2, ShieldCheck, UserPlus, Users, X,
} from 'lucide-react';
import {
  shareWorkspace, listMembers, revokeMember, listFiles, getExcludes, setExcludes,
  type WorkspaceMember, type WsFile,
} from '../lib/api';
import { toast } from '../lib/toast';
import { cn } from '../lib/utils';

interface Props { workspaceId: number; isOwner?: boolean; onClose: () => void; }

export default function ShareModal({ workspaceId, isOwner = false, onClose }: Props) {
  const [tab, setTab] = useState<'people' | 'files'>('people');
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<'editor' | 'viewer'>('editor');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Exclusions
  const [files, setFiles] = useState<WsFile[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [savingEx, setSavingEx] = useState(false);

  useEffect(() => {
    listMembers(workspaceId).then(setMembers).catch((e) =>
      setError(e?.response?.data?.detail || 'Failed to load members'));
    if (isOwner) {
      listFiles(workspaceId).then((f) => setFiles(f.filter((x) => x.type === 'file'))).catch(() => {});
      getExcludes(workspaceId).then((ex) => setExcluded(new Set(ex))).catch(() => {});
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [workspaceId, isOwner, onClose]);

  async function onShare(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setSubmitting(true);
    try {
      const invitee = username.trim();
      await shareWorkspace(workspaceId, invitee, role);
      setUsername('');
      setMembers(await listMembers(workspaceId));
      toast.success('Invite sent', `${invitee} can now ${role === 'editor' ? 'edit' : 'view'}.`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to share';
      setError(msg); toast.error('Could not share', msg);
    } finally { setSubmitting(false); }
  }

  async function onRevoke(userId: number, name?: string) {
    if (!confirm("Revoke this user's access?")) return;
    try {
      await revokeMember(workspaceId, userId);
      setMembers(await listMembers(workspaceId));
      toast.success('Access revoked', name ? `${name} removed.` : undefined);
    } catch (e: any) { toast.error('Could not revoke', e?.response?.data?.detail || 'Error'); }
  }

  function toggleExclude(path: string) {
    setExcluded((prev) => { const n = new Set(prev); n.has(path) ? n.delete(path) : n.add(path); return n; });
  }
  async function saveExcludes() {
    setSavingEx(true);
    try {
      await setExcludes(workspaceId, [...excluded]);
      toast.success('Sharing updated', excluded.size ? `${excluded.size} file(s) hidden from members` : 'All files shared');
    } catch (e: any) { toast.error('Could not update', e?.response?.data?.detail || 'Error'); }
    setSavingEx(false);
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div initial={{ scale: 0.97, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        onClick={(e) => e.stopPropagation()} className="w-full max-w-lg card shadow-pop my-auto">
        <div className="px-4 py-3 border-b border-edge flex items-center gap-2">
          <UserPlus size={16} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
          <h2 className="t-h3 flex-1">Share workspace</h2>
          <button type="button" onClick={onClose} title="Close" aria-label="Close" className="btn-ghost p-1.5"><X size={16} /></button>
        </div>

        {isOwner && (
          <div className="px-4 pt-3 flex gap-1">
            {(['people', 'files'] as const).map((t) => (
              <button key={t} type="button" onClick={() => setTab(t)}
                      className={cn('px-3 py-1.5 rounded-lg text-sm capitalize inline-flex items-center gap-1.5',
                        tab === t ? 'bg-astra-500/10 text-astra-600 dark:text-astra-300 font-medium' : 'text-muted hover:bg-raised')}>
                {t === 'people' ? <Users size={13} /> : <EyeOff size={13} />}
                {t === 'people' ? 'People' : 'Shared files'}
              </button>
            ))}
          </div>
        )}

        {tab === 'people' && (
          <>
            <form onSubmit={onShare} className="px-4 py-3">
              <label htmlFor="share-user" className="block text-xs font-medium text-muted mb-1">Invite by username</label>
              <div className="flex gap-2">
                <input id="share-user" value={username} onChange={(e) => setUsername(e.target.value)}
                       placeholder="e.g. yash" required className="input-base flex-1" />
                <select value={role} onChange={(e) => setRole(e.target.value as 'editor' | 'viewer')}
                        aria-label="Role" className="rounded-lg border border-edge bg-surface px-2 text-sm">
                  <option value="editor">Editor</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button type="submit" disabled={submitting || !username.trim()} className="btn-primary px-3">
                  {submitting ? <Loader2 size={14} className="animate-spin" /> : 'Invite'}
                </button>
              </div>
              {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
            </form>

            <div className="px-4 pb-4 max-h-[40vh] overflow-y-auto">
              <h3 className="t-overline text-faint mb-2">People with access ({members.length})</h3>
              <div className="space-y-1.5">
                {members.map((m) => (
                  <div key={m.user_id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-raised/60 border border-edge">
                    <span className="w-8 h-8 rounded-full bg-astra-600 text-white text-xs font-semibold flex items-center justify-center overflow-hidden shrink-0">
                      {m.avatar_url
                        // eslint-disable-next-line @next/next/no-img-element
                        ? <img src={m.avatar_url} alt="" className="w-full h-full object-cover" />
                        : m.username[0]?.toUpperCase()}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{m.username}</div>
                      <div className="text-xs text-faint truncate">{m.email || '—'}</div>
                    </div>
                    <span className={cn('chip capitalize', m.role === 'owner' && 'text-astra-600 dark:text-astra-300')}>{m.role}</span>
                    {m.role !== 'owner' && (
                      <button type="button" onClick={() => onRevoke(m.user_id, m.username)}
                              className="text-xs px-2 py-1 rounded-lg text-rose-600 dark:text-rose-400 hover:bg-rose-500/10">
                        Revoke
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {tab === 'files' && isOwner && (
          <div className="px-4 py-3">
            <p className="text-xs text-faint mb-3">
              All files are shared by default. Uncheck any you want to keep private
              (e.g. <span className="font-mono">.env</span>) — members won't see them.
            </p>
            <div className="max-h-[40vh] overflow-y-auto rounded-lg border border-edge divide-y divide-edge">
              {files.length === 0 && <p className="px-3 py-3 text-sm text-faint">No files yet.</p>}
              {files.map((f) => {
                const isExcluded = excluded.has(f.path);
                return (
                  <button key={f.path} type="button" onClick={() => toggleExclude(f.path)}
                          className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-raised">
                    <span className={cn('w-4 h-4 rounded border flex items-center justify-center shrink-0',
                      !isExcluded ? 'bg-astra-600 border-astra-600' : 'border-edge-strong')}>
                      {!isExcluded && <Check size={11} className="text-white" />}
                    </span>
                    <FileCode2 size={13} className={cn('shrink-0', isExcluded ? 'text-faint' : 'text-astra-400')} />
                    <span className={cn('text-sm font-mono truncate', isExcluded ? 'text-faint line-through' : 'text-ink')}>
                      {f.path}
                    </span>
                    {isExcluded && <span className="ml-auto text-[11px] text-amber-600 dark:text-amber-400 inline-flex items-center gap-1"><EyeOff size={11} /> hidden</span>}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-faint inline-flex items-center gap-1.5">
                <ShieldCheck size={12} /> {excluded.size} hidden, {files.length - excluded.size} shared
              </span>
              <button type="button" onClick={saveExcludes} disabled={savingEx} className="btn-primary px-3 py-1.5">
                {savingEx ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save sharing
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
