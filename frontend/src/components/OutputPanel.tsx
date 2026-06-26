'use client';
// Output panel — shows stdout/stderr from the most recent code execution.
import { X } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ExecuteResponse } from '../lib/api';

interface Props {
  result?:  ExecuteResponse | null;
  running?: boolean;
  onClose?: () => void;
}

export default function OutputPanel({ result, running, onClose }: Props) {
  const status = !result
    ? (running ? 'running' : 'idle')
    : (result.timeout ? 'timeout'
       : result.exit_code === 0 ? 'success'
       : 'error');

  const badgeColors: Record<string, string> = {
    idle:    'bg-slate-700 text-slate-300',
    running: 'bg-blue-700 text-blue-100 animate-pulse',
    success: 'bg-emerald-700 text-emerald-100',
    error:   'bg-rose-700 text-rose-100',
    timeout: 'bg-amber-700 text-amber-100',
  };

  return (
    <div className="flex flex-col bg-slate-950 border-t border-slate-800 text-sm font-mono">
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span className={cn('px-2 py-0.5 rounded font-semibold', badgeColors[status])}>
            {status.toUpperCase()}
          </span>
          {result && (
            <>
              <span className="text-slate-400">exit {result.exit_code}</span>
              <span className="text-slate-400">{result.runtime_ms}ms</span>
              {result.truncated && (
                <span className="text-amber-400">truncated</span>
              )}
            </>
          )}
        </div>
        {onClose && (
          <button onClick={onClose} type="button"
                  className="text-slate-400 hover:text-slate-200" title="Close" aria-label="Close"><X size={14} /></button>
        )}
      </div>

      <div className="p-3 overflow-y-auto h-[200px] whitespace-pre-wrap">
        {running && (
          <span className="text-slate-400 italic">Running…</span>
        )}
        {result && result.stdout && (
          <div className="text-slate-200">{result.stdout}</div>
        )}
        {result && result.stderr && (
          <div className="text-rose-300 mt-2">{result.stderr}</div>
        )}
        {result && !result.stdout && !result.stderr && (
          <span className="text-slate-500 italic">
            (no output; exit code {result.exit_code})
          </span>
        )}
      </div>
    </div>
  );
}
