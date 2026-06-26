'use client';
// Change history (Google-Docs style) — visible only to the workspace owner.
// Lists each saved edit: who, which file, lines added/removed, when.

import { useEffect, useState } from 'react';
import { History, Loader2, Plus, Minus, X } from 'lucide-react';
import { getHistory, type EditEntry } from '../lib/api';
import { formatRel } from '../lib/time';

export default function HistoryModal({ workspaceId, onClose }:
  { workspaceId: number; onClose: () => void }) {
  const [entries, setEntries] = useState<EditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHistory(workspaceId).then(setEntries)
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load history'));
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [workspaceId, onClose]);

  return (
    <div className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
         role="dialog" aria-modal="true" aria-label="Change history" onClick={onClose}>
      <div className="w-full max-w-2xl card shadow-pop my-auto" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-edge flex items-center gap-2">
          <History size={16} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
          <h2 className="t-h3 flex-1">Change history</h2>
          <button type="button" onClick={onClose} title="Close" aria-label="Close" className="btn-ghost p-1.5"><X size={16} /></button>
        </div>
        <p className="px-4 pt-3 text-xs text-faint">
          Every save is logged here, like Google Docs. Only you (the owner) can see this.
          Forks keep their own separate history.
        </p>
        <div className="p-4 max-h-[60vh] overflow-auto">
          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
          {!error && entries === null && (
            <p className="text-faint text-sm inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Loading</p>
          )}
          {entries && entries.length === 0 && (
            <p className="text-faint text-sm">No edits recorded yet. Save a file to start the log.</p>
          )}
          {entries && entries.length > 0 && (
            <ul className="divide-y divide-edge">
              {entries.map((e, i) => (
                <li key={i} className="py-2.5 flex items-center gap-3">
                  <span className="w-7 h-7 rounded-full bg-astra-600 text-white text-[11px] font-semibold flex items-center justify-center shrink-0">
                    {e.username[0]?.toUpperCase() ?? '?'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">
                      <span className="font-medium">{e.username}</span>
                      <span className="text-faint"> edited </span>
                      <span className="font-mono text-[13px]">{e.path}</span>
                    </div>
                    <div className="text-[11px] text-faint">{formatRel(e.created_at)}</div>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono shrink-0">
                    {e.lines_added > 0 && (
                      <span className="inline-flex items-center text-emerald-600 dark:text-emerald-400">
                        <Plus size={11} />{e.lines_added}
                      </span>
                    )}
                    {e.lines_removed > 0 && (
                      <span className="inline-flex items-center text-rose-600 dark:text-rose-400">
                        <Minus size={11} />{e.lines_removed}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
