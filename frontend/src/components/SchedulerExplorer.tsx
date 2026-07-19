'use client';
// Live scheduler explorer: pick a workload and see what each of the eight
// placement algorithms would choose right now (calls /scheduler/compare on the
// backend, which scores the real in-memory cluster state). Lets users see the
// algorithms genuinely disagree.

import { useEffect, useState, useCallback } from 'react';
import { Cpu, MemoryStick, Shield, RefreshCw, Loader2 } from 'lucide-react';
import { compareSchedulers, type SchedulerChoice } from '../lib/api';
import { cn } from '../lib/utils';
import { toast } from '../lib/toast';

const TIERS = ['runc', 'gvisor', 'firecracker'];
const LANGS = ['python', 'javascript', 'cpp', 'go', 'rust', 'bash'];

const ACCENT: Record<string, string> = {
  pfmppo: 'border-indigo-500/40 bg-indigo-500/10 text-indigo-600 dark:text-indigo-300',
  heft: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
  minmin: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
};

export default function SchedulerExplorer() {
  const [cpu, setCpu] = useState(1.0);
  const [memory, setMemory] = useState(1024);
  const [tier, setTier] = useState('runc');
  const [language, setLanguage] = useState('python');
  const [rows, setRows] = useState<SchedulerChoice[]>([]);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const res = await compareSchedulers({ cpu, memory, tier, language });
      setRows(res.results);
    } catch {
      toast.error('Could not reach scheduler', 'Is the backend running?');
    } finally {
      setLoading(false);
    }
  }, [cpu, memory, tier, language]);

  useEffect(() => { run(); /* initial */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Distinct nodes chosen (to show disagreement at a glance).
  const distinct = new Set(rows.map((r) => `${r.cluster_id}/${r.node_name}`)).size;

  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-semibold text-ink">Live scheduler explorer</h3>
          <p className="text-sm text-muted mt-1">
            Same workload, eight algorithms. They land on{' '}
            <span className="font-semibold text-ink">{distinct}</span> different nodes.
          </p>
        </div>
        <button onClick={run} disabled={loading}
                className="inline-flex items-center gap-2 rounded-full bg-astra-600 hover:bg-astra-700 text-white text-sm font-medium px-4 py-2 disabled:opacity-60">
          {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          Compare
        </button>
      </div>

      {/* controls */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
        <label className="text-xs text-muted">
          <span className="flex items-center gap-1.5 mb-1"><Cpu size={13} /> CPU: <b className="text-ink">{cpu.toFixed(1)}</b></span>
          <input type="range" min={0.5} max={8} step={0.5} value={cpu}
                 onChange={(e) => setCpu(+e.target.value)} className="w-full accent-astra-600" />
        </label>
        <label className="text-xs text-muted">
          <span className="flex items-center gap-1.5 mb-1"><MemoryStick size={13} /> Mem: <b className="text-ink">{memory}Mi</b></span>
          <input type="range" min={256} max={8192} step={256} value={memory}
                 onChange={(e) => setMemory(+e.target.value)} className="w-full accent-astra-600" />
        </label>
        <label className="text-xs text-muted">
          <span className="flex items-center gap-1.5 mb-1"><Shield size={13} /> Sandbox</span>
          <select value={tier} onChange={(e) => setTier(e.target.value)}
                  className="w-full rounded-md border border-edge bg-bg px-2 py-1.5 text-ink text-sm">
            {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted">
          <span className="mb-1 block">Language</span>
          <select value={language} onChange={(e) => setLanguage(e.target.value)}
                  className="w-full rounded-md border border-edge bg-bg px-2 py-1.5 text-ink text-sm">
            {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
      </div>

      {/* results */}
      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.algorithm}
               className="rounded-xl border border-edge bg-bg p-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <span className={cn('inline-block px-2 py-0.5 rounded-full text-[11px] font-medium border',
                ACCENT[r.algorithm] ?? 'border-edge text-muted')}>{r.label}</span>
              <div className="text-xs text-faint mt-1 truncate" title={r.reasoning}>{r.reasoning}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-mono text-sm font-semibold text-ink">{r.node_name}</div>
              <div className="text-[11px] text-faint">{r.cluster_id}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
