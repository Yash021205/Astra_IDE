'use client';
// Workspace settings (StackBlitz-style): config files + snippets, freeze
// (read-only lock), and delete. Freeze/delete are owner-only.

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  FileCog, Lock, LockOpen, Loader2, Settings2, Trash2, X, Code2,
} from 'lucide-react';
import {
  setFrozen, writeFile, deleteWorkspace, type Workspace,
} from '../lib/api';
import { toast } from '../lib/toast';
import { cn } from '../lib/utils';

const SETTINGS_TEMPLATE = `{
  "editor": { "fontSize": 14, "tabSize": 2, "wordWrap": true },
  "compile": { "trigger": "edit" },
  "preview": { "entry": "index.html" }
}
`;
const SNIPPETS_TEMPLATE = `{
  "log": {
    "prefix": "log",
    "body": ["console.log('$1');", "$2"],
    "description": "Log to console"
  }
}
`;

export default function SettingsModal({ ws, isOwner, onClose, onChanged, onOpenFile }: {
  ws: Workspace; isOwner: boolean; onClose: () => void;
  onChanged: (w: Workspace) => void; onOpenFile?: (path: string) => void;
}) {
  const router = useRouter();
  const [frozen, setFrozenState] = useState(!!ws.frozen);
  const [busy, setBusy] = useState(false);

  async function toggleFreeze() {
    setBusy(true);
    try {
      const updated = await setFrozen(ws.id, !frozen);
      setFrozenState(!!updated.frozen); onChanged(updated);
      toast.success(updated.frozen ? 'Workspace frozen' : 'Workspace unfrozen',
        updated.frozen ? 'It is now read-only.' : 'Editing re-enabled.');
    } catch (e: any) { toast.error('Could not change', e?.response?.data?.detail || 'Error'); }
    setBusy(false);
  }

  async function createConfig(path: string, body: string) {
    try {
      await writeFile(ws.id, path, body);
      toast.success('Config ready', path);
      onOpenFile?.(path); onClose();
    } catch (e: any) { toast.error('Could not create', e?.response?.data?.detail || 'Error'); }
  }

  async function onDelete() {
    if (!confirm(`Delete workspace "${ws.name}"? This cannot be undone.`)) return;
    setBusy(true);
    try { await deleteWorkspace(ws.id); toast.success('Workspace deleted', ws.name); router.push('/dashboard'); }
    catch (e: any) { toast.error('Delete failed', e?.response?.data?.detail || 'Error'); setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
         role="dialog" aria-modal="true" aria-label="Workspace settings" onClick={onClose}>
      <div className="w-full max-w-md card shadow-pop my-auto" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-edge flex items-center gap-2">
          <Settings2 size={16} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
          <h2 className="t-h3 flex-1">Workspace settings</h2>
          <button type="button" onClick={onClose} title="Close" aria-label="Close" className="btn-ghost p-1.5"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Config files */}
          <div>
            <h3 className="t-overline text-faint mb-2">Configuration</h3>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => createConfig('.astra/settings.json', SETTINGS_TEMPLATE)}
                      className="btn-outline justify-start text-sm">
                <FileCog size={14} /> Workspace settings
              </button>
              <button type="button" onClick={() => createConfig('.astra/snippets.json', SNIPPETS_TEMPLATE)}
                      className="btn-outline justify-start text-sm">
                <Code2 size={14} /> User snippets
              </button>
            </div>
            <p className="text-[11px] text-faint mt-1.5">Creates the config file and opens it in the editor.</p>
          </div>

          {/* Freeze */}
          {isOwner && (
            <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-edge bg-raised/40">
              <div className="min-w-0">
                <div className="text-sm font-medium inline-flex items-center gap-1.5">
                  {frozen ? <Lock size={13} className="text-amber-500" /> : <LockOpen size={13} />} Freeze project
                </div>
                <p className="text-[11px] text-faint">Lock the workspace read-only (prevents edits).</p>
              </div>
              <button type="button" onClick={toggleFreeze} disabled={busy}
                      className={cn('relative w-11 h-6 rounded-full transition-colors shrink-0',
                        frozen ? 'bg-amber-500' : 'bg-edge-strong')}
                      role="switch" aria-checked={frozen} aria-label="Freeze project">
                <span className={cn('absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all',
                  frozen ? 'left-[22px]' : 'left-0.5')} />
              </button>
            </div>
          )}

          {/* Danger zone */}
          {isOwner && (
            <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/5">
              <h3 className="text-xs font-semibold text-rose-600 dark:text-rose-400 mb-1.5">Danger zone</h3>
              <button type="button" onClick={onDelete} disabled={busy}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium disabled:opacity-50">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} Delete this workspace
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
