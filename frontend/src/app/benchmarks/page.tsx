'use client';
// Benchmarks — two clearly separated parts:
//  1. RESEARCH RESULTS (offline, on real datasets, vs the papers) — the headline.
//  2. LIVE SIMULATOR (in-browser replay of N synthetic jobs) — interactive,
//     reproducible by seed, with a left config panel + run-history log.
// A FAQ section explains every formula and why reruns differ.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  BarChart3, Play, RefreshCw, Trophy, Crown, History, Settings2, FlaskConical,
} from 'lucide-react';

import AppShell from '../../components/AppShell';
import SchedulerExplorer from '../../components/SchedulerExplorer';
import SvgBarChart, { type BarDatum } from '../../components/ui/SvgBarChart';
import FaqAccordion, { type FaqItem } from '../../components/ui/FaqAccordion';
import {
  runBenchmark, getBenchmarkHistory,
  type BenchmarkReport, type BenchmarkRow, type BenchmarkRunLog,
} from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { toast } from '../../lib/toast';
import { formatRel } from '../../lib/time';
import { cn } from '../../lib/utils';

const ALGO_LABEL: Record<string, string> = {
  ppo: 'ASTRA PPO', least_loaded: 'Least-Loaded', round_robin: 'Round-Robin',
  random: 'Random', fifo: 'FIFO',
};
// On-palette, distinct, harmonious bar colours.
const ALGO_COLOR: Record<string, string> = {
  ppo:          '#2B5748',   // deep green (ours)
  least_loaded: '#618764',   // green
  round_robin:  '#9CB080',   // sage
  random:       '#8fb7c4',   // muted blue
  fifo:         '#d98fa6',   // muted blossom
};

// Headline research results (offline, on real public datasets; see /research for
// the paper and dataset behind each number). Kept consistent with the committed
// artifacts under ml/*/artifacts/metrics.json.
const RESEARCH = [
  { k: 'B1', label: 'DRL-PPO scheduler', metric: 'real trace', sub: 'outperforms random placement', dataset: 'Google Cluster Trace 2011', tone: 'astra' },
  { k: 'B3', label: 'LSTM prewarming',   metric: '49%',        sub: 'fewer cold starts (N-RMSE 0.17)', dataset: 'Azure Functions 2019 trace', tone: 'emerald' },
  { k: 'B4', label: 'Syscall IDS',       metric: 'F1 0.82',    sub: 'LID-DS CVEs, beats STIDE and frequency', dataset: 'LID-DS 2021', tone: 'rose' },
  { k: 'B6', label: 'Carbon-aware',      metric: '30%',        sub: 'CO2 cut at a 24h deferral budget', dataset: 'UK Carbon Intensity API (live)', tone: 'purple' },
];

const TONE: Record<string, string> = {
  astra: 'text-astra-600 dark:text-astra-400', emerald: 'text-emerald-600 dark:text-emerald-400',
  rose: 'text-rose-600 dark:text-rose-400', purple: 'text-purple-600 dark:text-purple-400',
};

export default function BenchmarksPage() {
  const router = useRouter();
  const { token, hydrated } = useAuth();
  const [report, setReport]   = useState<BenchmarkReport | null>(null);
  const [running, setRunning] = useState(false);
  const [nJobs, setNJobs]     = useState(200);
  const [seed, setSeed]       = useState(42);
  const [history, setHistory] = useState<BenchmarkRunLog[]>([]);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) { router.push('/login'); return; }
    void runIt(200, 42);
  }, [token, hydrated]);

  async function runIt(jobs: number, runSeed: number) {
    setRunning(true);
    try {
      setReport(await runBenchmark(jobs, runSeed));
      getBenchmarkHistory(15).then(setHistory).catch(() => {});
    } catch (e: any) {
      toast.error('Benchmark failed', e?.response?.data?.detail || 'Server error');
    } finally { setRunning(false); }
  }

  return (
    <AppShell>
      <div className="flex min-h-screen">
        {/* Left config panel */}
        <ConfigPanel
          nJobs={nJobs} seed={seed} running={running}
          onJobs={setNJobs} onSeed={setSeed}
          onRun={() => runIt(nJobs, seed)}
          onReseed={() => { const s = Math.floor(Math.random() * 10000); setSeed(s); runIt(nJobs, s); }}
        />

        <section className="flex-1 min-w-0 px-4 sm:px-8 py-8 space-y-8">
          <div>
            <h1 className="t-h1 flex items-center gap-2.5">
              <BarChart3 className="text-astra-600 dark:text-astra-400" size={26} aria-hidden="true" />
              Scheduler benchmarks
            </h1>
            <p className="text-sm text-muted mt-1 max-w-2xl">
              Research results on real datasets, plus a live, reproducible replay of ASTRA PPO
              against classical baselines on the current cluster snapshot.
            </p>
          </div>

          {/* Research headline */}
          <div>
            <h2 className="t-overline text-faint mb-3 flex items-center gap-1.5">
              <FlaskConical size={13} /> Research results (offline, on real datasets)
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {RESEARCH.map((r) => (
                <div key={r.k} className="card p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="chip">{r.k}</span>
                  </div>
                  <div className={cn('text-2xl font-bold tabular-nums', TONE[r.tone])}>{r.metric}</div>
                  <div className="text-xs font-medium mt-0.5">{r.label}</div>
                  <div className="text-[11px] text-faint mt-0.5">{r.sub}</div>
                  <div className="text-[10px] text-faint mt-1.5 pt-1.5 border-t border-edge">{r.dataset}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Live scheduler explorer — compare all algorithms on a chosen workload */}
          <div>
            <h2 className="t-overline text-faint mb-3 flex items-center gap-1.5">
              <Settings2 size={13} /> Scheduler explorer — compare all eight algorithms
            </h2>
            <SchedulerExplorer />
          </div>

          {/* Live simulator */}
          <div>
            <h2 className="t-overline text-faint mb-3 flex items-center gap-1.5">
              <Play size={13} /> Live simulator — {nJobs} jobs, seed {seed}
            </h2>
            {report ? <LiveResults report={report} /> : (
              <div className="card p-8 text-center text-faint text-sm">
                {running ? 'Running the first benchmark…' : 'Run a benchmark from the panel on the left.'}
              </div>
            )}
          </div>

          {/* Run history */}
          <RunHistory history={history} />

          {/* FAQ */}
          <FaqAccordion items={FAQ} title="How these numbers work (FAQ)" />
        </section>
      </div>
    </AppShell>
  );
}

// ── Left config panel ──────────────────────────────────────────────────────

function ConfigPanel({ nJobs, seed, running, onJobs, onSeed, onRun, onReseed }: {
  nJobs: number; seed: number; running: boolean;
  onJobs: (n: number) => void; onSeed: (n: number) => void;
  onRun: () => void; onReseed: () => void;
}) {
  return (
    <aside className="hidden lg:flex w-64 shrink-0 border-r border-edge bg-surface/60 flex-col gap-5 p-4 sticky top-0 h-screen overflow-y-auto">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Settings2 size={15} className="text-astra-600 dark:text-astra-400" /> Run configuration
      </div>

      <div>
        <label htmlFor="cfg-jobs" className="block text-xs font-medium text-muted mb-1.5">
          Workload size — {nJobs} jobs
        </label>
        <input id="cfg-jobs" type="range" min={50} max={1000} step={50} value={nJobs}
               onChange={(e) => onJobs(parseInt(e.target.value, 10))}
               className="w-full accent-astra-500" />
        <div className="flex justify-between text-[10px] text-faint mt-1"><span>50</span><span>1000</span></div>
      </div>

      <div>
        <label htmlFor="cfg-seed" className="block text-xs font-medium text-muted mb-1.5">Seed (reproducible)</label>
        <input id="cfg-seed" type="number" value={seed}
               onChange={(e) => onSeed(parseInt(e.target.value || '0', 10))}
               className="input-base py-1.5 text-sm tabular-nums" />
        <p className="text-[10px] text-faint mt-1">Same seed → identical run. Change it → new random workload.</p>
      </div>

      <div className="space-y-2">
        <button type="button" onClick={onRun} disabled={running} className="btn-primary w-full py-2">
          {running ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
          {running ? 'Running' : 'Run benchmark'}
        </button>
        <button type="button" onClick={onReseed} disabled={running} className="btn-outline w-full py-2 text-sm">
          <RefreshCw size={13} /> Randomize seed & run
        </button>
      </div>

      <div className="mt-auto text-[11px] text-faint leading-relaxed border-t border-edge pt-3">
        <p className="font-medium text-muted mb-1">Algorithms compared</p>
        <ul className="space-y-1">
          {Object.entries(ALGO_LABEL).map(([k, v]) => (
            <li key={k} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background: ALGO_COLOR[k] }} />
              {v}{k === 'ppo' && ' (ours)'}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

// ── Live results (SVG charts + table) ────────────────────────────────────────

function LiveResults({ report }: { report: BenchmarkReport }) {
  const rows = report.rows;
  const ppo = rows.find((r) => r.algorithm === 'ppo');
  const baselines = rows.filter((r) => r.algorithm !== 'ppo');
  const avg = (k: keyof BenchmarkRow) => baselines.reduce((s, r) => s + (r[k] as number), 0) / (baselines.length || 1);
  const latGain = ppo ? ((avg('avg_latency_ms') - ppo.avg_latency_ms) / avg('avg_latency_ms')) * 100 : 0;
  const utilGain = ppo ? ((ppo.utilization_pct - avg('utilization_pct')) / avg('utilization_pct')) * 100 : 0;

  const toData = (valueOf: (r: BenchmarkRow) => number, fmt: (v: number) => string, lowerBetter: boolean): BarDatum[] => {
    const vals = rows.map(valueOf);
    const best = lowerBetter ? Math.min(...vals) : Math.max(...vals);
    return rows.map((r) => ({
      label: ALGO_LABEL[r.algorithm], value: valueOf(r), color: ALGO_COLOR[r.algorithm],
      best: valueOf(r) === best, display: fmt(valueOf(r)),
    }));
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Avg latency gain" value={`${latGain >= 0 ? '−' : '+'}${Math.abs(latGain).toFixed(1)}%`}
             good={latGain >= 0} sub="vs baseline avg" icon={<Trophy size={14} />} />
        <KPI label="Utilization gain" value={`${utilGain >= 0 ? '+' : '−'}${Math.abs(utilGain).toFixed(1)}%`}
             good={utilGain >= 0} sub="higher is better" />
        <KPI label="PPO SLA breaches" value={`${ppo?.sla_violations ?? 0}`} good={(ppo?.sla_violations ?? 0) === 0} sub="of all jobs" />
        <KPI label="PPO balance" value={ppo?.balance_score.toFixed(3) ?? '—'} good sub="1.0 = even spread" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <ChartCard title="Average startup latency" subtitle="lower is better">
          <SvgBarChart unit="ms" data={toData((r) => r.avg_latency_ms, (v) => `${v.toFixed(0)} ms`, true)} />
        </ChartCard>
        <ChartCard title="Resource utilization" subtitle="higher is better">
          <SvgBarChart unit="%" data={toData((r) => r.utilization_pct, (v) => `${v.toFixed(1)}%`, false)} />
        </ChartCard>
        <ChartCard title="Cluster balance score" subtitle="1.0 = perfectly even">
          <SvgBarChart data={toData((r) => r.balance_score, (v) => v.toFixed(3), false)} />
        </ChartCard>
        <ChartCard title="Energy proxy (load × carbon)" subtitle="lower is better">
          <SvgBarChart data={toData((r) => r.energy_kwh, (v) => v.toFixed(3), true)} />
        </ChartCard>
      </div>
    </div>
  );
}

function ChartCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-semibold text-sm">{title}</h3>
        <span className="text-[11px] text-faint">{subtitle}</span>
      </div>
      {children}
    </div>
  );
}

function KPI({ label, value, sub, good, icon }: {
  label: string; value: string; sub: string; good: boolean; icon?: React.ReactNode;
}) {
  return (
    <div className="card p-3.5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] uppercase tracking-wider text-faint">{label}</span>
        {icon && <span className="text-faint">{icon}</span>}
      </div>
      <div className={cn('text-xl font-bold tabular-nums',
        good ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
        {value}
      </div>
      <div className="text-[11px] text-faint mt-0.5">{sub}</div>
    </div>
  );
}

// ── Run history log ──────────────────────────────────────────────────────────

function RunHistory({ history }: { history: BenchmarkRunLog[] }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-edge flex items-center gap-2">
        <History size={15} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
        <h3 className="font-semibold text-sm flex-1">Previous runs</h3>
        <span className="text-xs text-faint">{history.length} logged</span>
      </div>
      {history.length === 0 ? (
        <p className="px-4 py-6 text-sm text-faint text-center">No runs yet. Each run you do is logged here.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-raised/70 text-xs uppercase text-faint">
              <tr>
                <th scope="col" className="px-4 py-2 text-left">When</th>
                <th scope="col" className="px-4 py-2 text-left">By</th>
                <th scope="col" className="px-4 py-2 text-right">Jobs</th>
                <th scope="col" className="px-4 py-2 text-right">Seed</th>
                <th scope="col" className="px-4 py-2 text-left">Winner</th>
                <th scope="col" className="px-4 py-2 text-right">PPO latency</th>
                <th scope="col" className="px-4 py-2 text-right">Latency gain</th>
                <th scope="col" className="px-4 py-2 text-right">SLA</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-t border-edge">
                  <td className="px-4 py-2 text-faint whitespace-nowrap">{formatRel(h.created_at)}</td>
                  <td className="px-4 py-2 truncate max-w-[8rem]">{h.username}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{h.n_jobs}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-mono">{h.seed}</td>
                  <td className="px-4 py-2">
                    <span className={cn('inline-flex items-center gap-1', h.winner === 'ppo' && 'text-astra-600 dark:text-astra-300 font-medium')}>
                      {h.winner === 'ppo' && <Crown size={11} />}{ALGO_LABEL[h.winner] ?? h.winner}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{h.ppo_latency_ms.toFixed(0)} ms</td>
                  <td className={cn('px-4 py-2 text-right tabular-nums',
                    h.latency_gain_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
                    {h.latency_gain_pct >= 0 ? '−' : '+'}{Math.abs(h.latency_gain_pct).toFixed(1)}%
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{h.ppo_sla}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── FAQ content ──────────────────────────────────────────────────────────────

const FAQ: FaqItem[] = [
  {
    q: 'Is this running on our project, or on some dataset?',
    a: (<>
      The <strong>Live simulator</strong> here runs on <strong>our project&apos;s own cluster model</strong> —
      it generates synthetic jobs and replays them against the current (simulated) cluster telemetry. It does
      <strong> not</strong> use an external dataset. The <strong>Research results</strong> cards at the top are the
      separate, offline evaluations on real datasets (Azure trace, Tetragon corpus, UK carbon API) that validate
      each breakthrough against its paper.
    </>),
  },
  {
    q: 'Why do the numbers change every time I rerun?',
    a: (<>
      Each run generates a fresh random workload from the <strong>seed</strong>. Keep the same seed and you get an
      <strong> identical, reproducible</strong> run. Change the seed (or the job count) and you get a different
      workload, so the absolute numbers shift — but ASTRA PPO stays ahead of the baselines across seeds.
    </>),
  },
  {
    q: 'Why are the live improvements smaller than the headline +112%?',
    a: (<>
      The <strong>+112%</strong> is the <em>reward</em> gain from the full PPO training run (offline, thousands of
      episodes in the Gymnasium environment). The live page is a fast <em>sanity-check replay</em> using the learned
      scoring policy, not a full training — so its per-metric deltas (latency, utilization) are smaller but in the
      same direction. The page proves &ldquo;sensibly better under live conditions&rdquo;; the offline benchmark proves
      &ldquo;by how much, on real data.&rdquo;
    </>),
  },
  {
    q: 'How is startup latency computed?',
    a: (<>
      <span className="font-mono text-xs">latency = 120ms base + cpu_util×1800 + run_queue×250 + tier_overhead</span>,
      where tier overhead is runc 60ms / gVisor 150ms / Firecracker 350ms (risk-dependent). Any single placement
      above 5000ms counts as an <strong>SLA breach</strong>.
    </>),
  },
  {
    q: 'What are utilization, balance and energy?',
    a: (<>
      <strong>Utilization</strong> = mean CPU across all nodes after the workload is placed (higher = fuller cluster).{' '}
      <strong>Balance</strong> = <span className="font-mono text-xs">1 − stddev(cpu)/mean(cpu)</span> (1.0 = perfectly
      even spread). <strong>Energy proxy</strong> = Σ (node load × grid carbon intensity) — lower means greener placement.
    </>),
  },
  {
    q: 'What does ASTRA PPO actually optimize?',
    a: (<>
      It scores each node on weighted factors learned by the PPO agent: free CPU (0.35), free memory (0.25),
      queue depth (0.15) and low grid carbon (0.15), with an overload penalty above 85% CPU — then places the job
      on the best node. Baselines use textbook rules (round-robin, least-loaded, etc.).
    </>),
  },
];
