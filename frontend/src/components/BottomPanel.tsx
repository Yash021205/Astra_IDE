'use client';
// VS Code-style tabbed bottom panel.
//
// Tabs:
//   - Output   → most recent execution stdout/stderr (this replaces the
//                standalone OutputPanel when this component is mounted)
//   - Problems → static lint hints + compile errors parsed from stderr
//   - Terminal → mock shell showing scheduler/run events
//
// The user can close the whole panel; the parent restores it when a Run
// happens (it pushes new output, opens automatically).

import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, X, Terminal as TerminalIcon, AlertOctagon, FileOutput } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ExecuteResponse } from '../lib/api';

interface Props {
  result?:    ExecuteResponse | null;
  running?:   boolean;
  onClose?:   () => void;
  workspace?: { name: string; language: string; sandbox: string };
}

type Tab = 'output' | 'problems' | 'terminal';

interface ProblemRow {
  severity: 'error' | 'warning';
  line?:    number;
  column?:  number;
  message:  string;
}

// Parse compile/runtime stderr lines like "main.cpp:7:5: error: ..."
function parseProblems(stderr: string): ProblemRow[] {
  if (!stderr) return [];
  const rows: ProblemRow[] = [];
  const re = /^([^:\n]+):(\d+)(?::(\d+))?:\s*(error|warning):\s*(.+)$/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(stderr)) !== null) {
    rows.push({
      severity: m[4] as 'error' | 'warning',
      line:     parseInt(m[2], 10),
      column:   m[3] ? parseInt(m[3], 10) : undefined,
      message:  m[5].trim(),
    });
  }
  // If we couldn't parse structured rows but stderr exists, surface the
  // whole thing as a single error.
  if (rows.length === 0 && stderr.trim()) {
    rows.push({ severity: 'error', message: stderr.split('\n').slice(0, 5).join('\n').trim() });
  }
  return rows;
}

export default function BottomPanel({ result, running, onClose, workspace }: Props) {
  const [tab, setTab] = useState<Tab>('output');
  const [termLines, setTermLines] = useState<{ kind: 'info' | 'cmd' | 'out' | 'err'; text: string }[]>([
    { kind: 'info', text: 'ASTRA-IDE shell (read-only demo). Ctrl+J toggles this panel.' },
  ]);
  const termRef = useRef<HTMLDivElement>(null);

  // When a new run lands, switch to Output tab and emit terminal log
  useEffect(() => {
    if (!result) return;
    setTab('output');
    setTermLines((lines) => [
      ...lines,
      { kind: 'cmd', text: `astra exec --lang ${result.language}` },
      { kind: 'info', text: `[sandbox=${workspace?.sandbox ?? '?'} runtime=${result.runtime_ms}ms]` },
      ...(result.stdout ? result.stdout.split('\n').map((t) => ({ kind: 'out' as const, text: t })) : []),
      ...(result.stderr ? result.stderr.split('\n').map((t) => ({ kind: 'err' as const, text: t })) : []),
      { kind: 'info', text: `exit ${result.exit_code}${result.timeout ? ' (timeout)' : ''}` },
    ]);
  }, [result, workspace?.sandbox]);

  // Autoscroll terminal
  useEffect(() => {
    if (tab === 'terminal' && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [tab, termLines]);

  const problems = useMemo(() => parseProblems(result?.stderr ?? ''), [result]);

  return (
    <div className="flex flex-col bg-slate-950 border-t border-slate-800 text-sm font-mono">
      {/* Tab strip */}
      <div className="flex items-center bg-slate-900 border-b border-slate-800 text-xs">
        <TabButton
          icon={<FileOutput   size={12} />}
          label="OUTPUT"      active={tab === 'output'}
          badge={result ? (result.exit_code === 0 ? 'ok' : 'err') : undefined}
          onClick={() => setTab('output')}
        />
        <TabButton
          icon={<AlertOctagon size={12} />}
          label="PROBLEMS"    active={tab === 'problems'}
          badge={problems.length > 0 ? String(problems.length) : undefined}
          badgeClass="bg-rose-700/80"
          onClick={() => setTab('problems')}
        />
        <TabButton
          icon={<TerminalIcon size={12} />}
          label="TERMINAL"    active={tab === 'terminal'}
          onClick={() => setTab('terminal')}
        />
        <div className="flex-1" />
        {onClose && (
          <button
            type="button" onClick={onClose} aria-label="Close panel"
            className="px-2 py-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          >
            <ChevronDown size={14} />
          </button>
        )}
      </div>

      {/* Tab content */}
      <div className="h-[200px] overflow-hidden relative">
        <AnimatePresence mode="wait">
          {tab === 'output' && (
            <motion.div
              key="output"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 p-3 overflow-y-auto whitespace-pre-wrap"
            >
              {running && <span className="text-slate-400 italic">Running…</span>}
              {result && result.stdout && (
                <div className="text-slate-200">{result.stdout}</div>
              )}
              {result && result.stderr && (
                <div className="text-rose-300 mt-2">{result.stderr}</div>
              )}
              {!running && !result && (
                <p className="text-slate-500 italic">
                  No runs yet. Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-astra-300">Ctrl+Enter</kbd> to execute.
                </p>
              )}
              {result && !result.stdout && !result.stderr && (
                <p className="text-slate-500 italic">
                  (no output; exit code {result.exit_code})
                </p>
              )}
            </motion.div>
          )}

          {tab === 'problems' && (
            <motion.div
              key="problems"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 overflow-y-auto"
            >
              {problems.length === 0 ? (
                <p className="p-3 text-slate-500 italic">No problems detected.</p>
              ) : (
                <table className="w-full text-xs">
                  <tbody>
                    {problems.map((p, idx) => (
                      <tr key={idx} className="hover:bg-slate-900/60 border-b border-slate-800/50">
                        <td className="px-3 py-1.5 w-16">
                          <span className={cn(
                            'inline-block w-2 h-2 rounded-full mr-1.5',
                            p.severity === 'error' ? 'bg-rose-500' : 'bg-amber-500',
                          )} />
                          <span className="text-slate-400 uppercase tracking-wider">
                            {p.severity}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-slate-400 w-20 font-mono">
                          {p.line ? `Ln ${p.line}${p.column ? `:${p.column}` : ''}` : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-slate-200 whitespace-pre-wrap">
                          {p.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </motion.div>
          )}

          {tab === 'terminal' && (
            <motion.div
              key="terminal"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 bg-black"
            >
              <div ref={termRef} className="h-full overflow-y-auto p-3 text-[12px] leading-relaxed">
                {termLines.map((l, idx) => (
                  <div key={idx} className={cn('whitespace-pre-wrap',
                    l.kind === 'cmd'  && 'text-emerald-400',
                    l.kind === 'info' && 'text-slate-500 italic',
                    l.kind === 'out'  && 'text-slate-200',
                    l.kind === 'err'  && 'text-rose-300',
                  )}>
                    {l.kind === 'cmd' && <span className="text-astra-400 mr-1.5">$</span>}
                    {l.text}
                  </div>
                ))}
                <div className="flex items-center mt-1 text-slate-400">
                  <span className="text-astra-400 mr-1.5">$</span>
                  <span className="inline-block w-2 h-3.5 bg-slate-300 animate-pulse" />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function TabButton({
  icon, label, active, badge, badgeClass, onClick,
}: {
  icon: React.ReactNode; label: string; active: boolean;
  badge?: string; badgeClass?: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick} type="button"
      className={cn(
        'px-3 py-2 flex items-center gap-1.5 border-b-2 transition-colors',
        active
          ? 'border-astra-500 text-white bg-slate-950'
          : 'border-transparent text-slate-400 hover:text-slate-200',
      )}
    >
      {icon}
      <span className="tracking-wider">{label}</span>
      {badge && (
        <span className={cn(
          'ml-1 inline-flex items-center justify-center min-w-[16px] px-1 h-4 rounded-full text-[9px] font-semibold',
          badgeClass ?? 'bg-emerald-600/80 text-white',
        )}>
          {badge}
        </span>
      )}
    </button>
  );
}
