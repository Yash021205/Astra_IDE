'use client';
// Aceternity-style "background ripple" — an interactive grid of cells. Hovering
// a cell lights it up; clicking sends a distance-based ripple outward. Themed in
// ASTRA blue/purple (not grey).

import { useMemo, useState } from 'react';
import { cn } from '../../lib/utils';

interface Props {
  rows?: number;
  cols?: number;
  cellSize?: number;
  className?: string;
}

export default function BackgroundRippleEffect({
  rows = 9, cols = 30, cellSize = 56, className,
}: Props) {
  const [clicked, setClicked] = useState<{ r: number; c: number } | null>(null);
  const [rippleKey, setRippleKey] = useState(0);

  const cells = useMemo(
    () => Array.from({ length: rows * cols }, (_, i) => ({ r: Math.floor(i / cols), c: i % cols })),
    [rows, cols],
  );

  return (
    <div className={cn('absolute inset-0 h-full w-full overflow-hidden', className)} aria-hidden="true">
      {/* soft theme glow behind the grid */}
      <div className="absolute inset-0"
           style={{ background: 'radial-gradient(ellipse 70% 60% at 50% 0%, rgb(176 196 177 / 0.22), transparent 70%)' }} />
      <div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ width: cols * cellSize, height: rows * cellSize }}
      >
        <div
          key={rippleKey}
          className="grid h-full w-full"
          style={{ gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`, gridTemplateRows: `repeat(${rows}, ${cellSize}px)` }}
        >
          {cells.map((cell, i) => {
            const dist = clicked
              ? Math.hypot(cell.r - clicked.r, cell.c - clicked.c)
              : 0;
            return (
              <button
                key={i}
                type="button"
                tabIndex={-1}
                onClick={() => { setClicked(cell); setRippleKey((k) => k + 1); }}
                className="ripple-cell border-[0.5px] border-astra-500/10 transition-colors duration-500
                           hover:bg-astra-500/15 hover:border-astra-500/40"
                style={clicked ? { animationDelay: `${dist * 55}ms` } : undefined}
              />
            );
          })}
        </div>
      </div>
      {/* fade edges into the page background */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(ellipse 80% 80% at 50% 50%, transparent 35%, rgb(var(--c-bg)) 95%)' }} />
    </div>
  );
}
