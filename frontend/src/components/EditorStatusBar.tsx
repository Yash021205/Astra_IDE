'use client';
// VS Code-style status bar at the bottom of the editor.
// Shows: language, cursor position, encoding, indent, online peers, kbd hint.

import { Circle, Keyboard, Users } from 'lucide-react';
import { cn } from '../lib/utils';

interface Props {
  language:   string;
  line:       number;
  column:     number;
  peers:      number;
  status:     string;          // workspace status (PENDING/RUNNING/etc.)
  sandbox:    string;          // sandbox tier
  onOpenHelp: () => void;
}

export default function EditorStatusBar({
  language, line, column, peers, status, sandbox, onOpenHelp,
}: Props) {
  const statusColors: Record<string, string> = {
    PENDING:   'bg-slate-600',
    PREWARMED: 'bg-blue-600',
    RUNNING:   'bg-emerald-600',
    STOPPED:   'bg-slate-700',
    FAILED:    'bg-red-600',
    ARCHIVED:  'bg-slate-700',
  };
  const sandboxColors: Record<string, string> = {
    runc:        'text-emerald-400',
    gvisor:      'text-amber-400',
    firecracker: 'text-rose-400',
  };

  return (
    <div className="flex items-center gap-3 px-3 py-1 bg-astra-700 text-white text-[11px] font-mono select-none">
      {/* Workspace status pill */}
      <div className="flex items-center gap-1.5">
        <Circle size={8} className={cn('rounded-full', statusColors[status] || 'bg-slate-600')}
                fill="currentColor" />
        <span>{status}</span>
      </div>

      {/* Sandbox tier */}
      <div className={cn('flex items-center gap-1', sandboxColors[sandbox])}>
        <span>sandbox: {sandbox}</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Cursor position */}
      <span title="Cursor position">Ln {line}, Col {column}</span>

      {/* Indent */}
      <span className="text-white/70">Spaces: 4</span>

      {/* Encoding */}
      <span className="text-white/70">UTF-8</span>

      {/* Language */}
      <span title="Current language" className="font-semibold">{language}</span>

      {/* Peers online */}
      <div className="flex items-center gap-1" title="Editors online">
        <Users size={11} />
        <span>{peers}</span>
      </div>

      {/* Keybindings help */}
      <button
        type="button"
        onClick={onOpenHelp}
        title="Show keyboard shortcuts (Ctrl+K)"
        className="inline-flex items-center gap-1 hover:bg-white/10 rounded px-1.5 py-0.5"
      >
        <Keyboard size={11} />
        <span>?</span>
      </button>
    </div>
  );
}
