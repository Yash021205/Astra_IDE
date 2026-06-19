'use client';
// Share workspace with another registered user.
// Parent controls mounting (mount = open, unmount = closed).
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { UserPlus, X } from 'lucide-react';
import {
  shareWorkspace, listMembers, revokeMember,
  type WorkspaceMember,
} from '../lib/api';
import { toast } from '../lib/toast';

interface Props {
  workspaceId: number;
  onClose:     () => void;
}

export default function ShareModal({ workspaceId, onClose }: Props) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<'editor' | 'viewer'>('editor');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { refresh(); }, [workspaceId]);

  async function refresh() {
    try {
      setMembers(await listMembers(workspaceId));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load members');
    }
  }

  async function onShare(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const invitee = username.trim();
      await shareWorkspace(workspaceId, invitee, role);
      setUsername('');
      refresh();
      toast.success('Invite sent', `@${invitee} can now ${role === 'editor' ? 'edit' : 'view'}.`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to share';
      setError(msg);
      toast.error('Could not share', msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function onRevoke(userId: number, username?: string) {
    if (!confirm('Revoke this user\'s access?')) return;
    try {
      await revokeMember(workspaceId, userId);
      refresh();
      toast.success('Access revoked', username ? `@${username} removed.` : undefined);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to revoke';
      setError(msg);
      toast.error('Could not revoke', msg);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center px-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1,    opacity: 1 }}
        exit={{    scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl shadow-2xl"
      >
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <UserPlus size={18} className="text-astra-500" />
            Share workspace
          </h2>
          <button onClick={onClose} type="button" aria-label="Close"
                  className="text-slate-400 hover:text-slate-100">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={onShare} className="px-5 py-4 border-b border-slate-800">
          <label className="block text-xs text-slate-400 mb-1">Invite by username</label>
          <div className="flex gap-2">
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. alice"
              required
              className="flex-1 px-3 py-2 rounded bg-slate-800 border border-slate-700 focus:border-astra-500 outline-none text-sm"
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'editor' | 'viewer')}
              aria-label="Role"
              className="px-3 py-2 rounded bg-slate-800 border border-slate-700 text-sm"
            >
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
            <button
              type="submit" disabled={submitting || !username.trim()}
              className="px-4 py-2 rounded bg-astra-600 hover:bg-astra-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? '…' : 'Invite'}
            </button>
          </div>
          {error && (
            <p className="mt-2 text-xs text-rose-400">{error}</p>
          )}
          <p className="mt-2 text-xs text-slate-500">
            They'll be able to open this workspace at the same URL and edit
            collaboratively in real time.
          </p>
        </form>

        <div className="px-5 py-4 max-h-[320px] overflow-y-auto">
          <h3 className="text-xs uppercase text-slate-500 mb-2 tracking-wider">
            Members ({members.length})
          </h3>
          <div className="space-y-2">
            {members.map((m) => (
              <div key={m.user_id}
                   className="flex items-center justify-between px-3 py-2 rounded bg-slate-800/60 border border-slate-800">
                <div>
                  <div className="text-sm font-medium">@{m.username}</div>
                  <div className="text-xs text-slate-400 capitalize">{m.role}</div>
                </div>
                {m.role !== 'owner' && (
                  <button onClick={() => onRevoke(m.user_id, m.username)} type="button"
                          className="text-xs px-2 py-1 rounded bg-rose-900/60 hover:bg-rose-800 text-rose-200">
                    Revoke
                  </button>
                )}
              </div>
            ))}
            {members.length === 0 && (
              <p className="text-sm text-slate-500 italic">No members yet.</p>
            )}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
