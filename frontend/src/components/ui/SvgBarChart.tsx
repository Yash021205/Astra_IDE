'use client';
// Lightweight, dependency-free SVG bar chart (shadcn-style): gridlines, animated
// bars, value labels, "best" highlight. Horizontal layout so long algorithm
// names read cleanly. Pure SVG — no charting library.

import { useId } from 'react';
import { cn } from '../../lib/utils';

export interface BarDatum {
  label: string;
  value: number;
  color?: string;      // bar fill (CSS color)
  best?: boolean;      // highlight as the winner
  display?: string;    // formatted value text
}

export default function SvgBarChart({
  data, max, unit = '', height,
}: {
  data: BarDatum[]; max?: number; unit?: string; height?: number;
}) {
  const gid = useId();
  const top = max ?? Math.max(...data.map((d) => d.value), 1);
  const rowH = 34;
  const gap = 10;
  const labelW = 116;
  const chartW = 520;          // viewBox width (scales responsively)
  const barAreaW = chartW - labelW - 56;
  const h = height ?? data.length * (rowH + gap) + 12;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg viewBox={`0 0 ${chartW} ${h}`} className="w-full" role="img"
         preserveAspectRatio="xMidYMid meet">

      {/* gridlines */}
      {ticks.map((t) => {
        const x = labelW + t * barAreaW;
        return (
          <g key={t}>
            <line x1={x} y1={4} x2={x} y2={h - 16} stroke="currentColor"
                  className="text-edge" strokeWidth={1} strokeDasharray={t === 0 ? '' : '3 3'} />
            <text x={x} y={h - 4} textAnchor="middle" className="fill-faint text-[9px]">
              {fmtTick(t * top, unit)}
            </text>
          </g>
        );
      })}

      {data.map((d, i) => {
        const y = 6 + i * (rowH + gap);
        const w = Math.max(2, (d.value / top) * barAreaW);
        return (
          <g key={d.label}>
            <text x={labelW - 10} y={y + rowH / 2} textAnchor="end" dominantBaseline="middle"
                  className={cn('text-[11px]', d.best ? 'fill-ink font-semibold' : 'fill-muted')}>
              {d.label}
            </text>
            <rect x={labelW} y={y} width={barAreaW} height={rowH} rx={6}
                  fill="rgb(var(--c-edge))" opacity={0.5} />
            <rect x={labelW} y={y} width={w} height={rowH} rx={6}
                  fill={d.color || '#9CB080'} opacity={d.best ? 1 : 0.55}
                  stroke={d.best ? d.color || '#2B5748' : 'transparent'} strokeWidth={d.best ? 1.5 : 0}>
              <animate attributeName="width" from="0" to={w} dur="0.7s" fill="freeze"
                       calcMode="spline" keySplines="0.16 1 0.3 1" keyTimes="0;1" />
            </rect>
            <text x={labelW + w + 8} y={y + rowH / 2} dominantBaseline="middle"
                  className={cn('text-[11px] font-mono', d.best ? 'fill-ink font-semibold' : 'fill-muted')}>
              {d.display ?? d.value.toFixed(0)}{d.best ? '  ★' : ''}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function fmtTick(v: number, unit: string): string {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (v < 1 && v > 0) return v.toFixed(2);
  return `${Math.round(v)}${unit === '%' ? '%' : ''}`;
}
