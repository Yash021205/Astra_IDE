'use client';
// Feature comparison: ASTRA-IDE vs the mainstream cloud IDEs. Uses lucide icons
// (Check / X / Minus) rather than emoji, per the design guidance. ASTRA's column
// is highlighted; cells light up on row hover. Theme-aware, no external assets.

import { Check, X, Minus } from 'lucide-react';
import { cn } from '../../lib/utils';

type Cell = 'yes' | 'no' | 'partial';

const PRODUCTS = ['ASTRA-IDE', 'GitHub Codespaces', 'Gitpod', 'Replit', 'Coder'] as const;

interface Row { feature: string; note?: string; cells: Cell[]; }

// cells order matches PRODUCTS. Honest: partial = exists but limited/not adaptive.
const ROWS: Row[] = [
  { feature: 'Self-scheduling control plane (RL)', note: 'learned placement policy',
    cells: ['yes', 'no', 'no', 'no', 'no'] },
  { feature: 'Adaptive sandbox tiers', note: 'runc / gVisor / Firecracker by risk',
    cells: ['yes', 'partial', 'partial', 'partial', 'no'] },
  { feature: 'eBPF syscall telemetry', note: 'Tetragon, per-workspace',
    cells: ['yes', 'no', 'no', 'no', 'no'] },
  { feature: 'Predictive pre-warming', note: 'forecast sessions, cut cold starts',
    cells: ['yes', 'partial', 'yes', 'no', 'no'] },
  { feature: 'Multi-cluster federation', note: 'Karmada, cross-region failover',
    cells: ['yes', 'no', 'no', 'no', 'partial'] },
  { feature: 'Carbon-aware placement', note: 'live grid intensity',
    cells: ['yes', 'no', 'no', 'no', 'no'] },
  { feature: 'Real-time CRDT collaboration', note: 'multi-cursor, conflict-free',
    cells: ['yes', 'partial', 'yes', 'yes', 'no'] },
  { feature: 'Intrusion detection on syscalls', note: 'anomaly IDS',
    cells: ['yes', 'no', 'no', 'no', 'no'] },
  { feature: 'Open source', cells: ['yes', 'no', 'partial', 'no', 'yes'] },
  { feature: 'Self-hostable', cells: ['yes', 'no', 'yes', 'no', 'yes'] },
];

function Mark({ v }: { v: Cell }) {
  if (v === 'yes')
    return <Check size={18} className="text-emerald-500" aria-label="yes" />;
  if (v === 'partial')
    return <Minus size={18} className="text-amber-500" aria-label="partial" />;
  return <X size={16} className="text-slate-300 dark:text-slate-600" aria-label="no" />;
}

export default function ComparisonTable() {
  return (
    <div className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full border-collapse text-sm min-w-[720px]">
        <thead>
          <tr className="border-b border-edge">
            <th className="text-left font-semibold text-ink px-5 py-4 w-[38%]">Capability</th>
            {PRODUCTS.map((p, i) => (
              <th key={p}
                  className={cn('px-3 py-4 text-center font-semibold whitespace-nowrap',
                    i === 0
                      ? 'text-ink bg-emerald-500/10 border-x border-emerald-500/30'
                      : 'text-muted')}>
                {i === 0
                  ? <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />{p}
                    </span>
                  : p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.feature}
                className="border-b border-edge/70 last:border-0 transition-colors hover:bg-raised/60">
              <td className="px-5 py-3.5">
                <div className="font-medium text-ink">{r.feature}</div>
                {r.note && <div className="text-xs text-faint mt-0.5">{r.note}</div>}
              </td>
              {r.cells.map((c, i) => (
                <td key={i}
                    className={cn('px-3 py-3.5 text-center',
                      i === 0 && 'bg-emerald-500/[0.07] border-x border-emerald-500/20')}>
                  <span className="inline-flex justify-center"><Mark v={c} /></span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
