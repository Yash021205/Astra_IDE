'use client';
// Aceternity-style "background ripple" — a full-page interactive grid. Hovering a
// cell clearly lights it up (feels clickable); clicking sends a distance-based
// ripple outward across the whole grid.

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '../../lib/utils';

interface Props { cellSize?: number; className?: string; }

export default function BackgroundRippleEffect({ cellSize = 54, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ rows: 16, cols: 28 });
  const [clicked, setClicked] = useState<{ r: number; c: number } | null>(null);
  const [rippleKey, setRippleKey] = useState(0);

  // Fill the whole container with a uniform grid (recomputed on resize).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth, h = el.clientHeight;
      setDims({ cols: Math.ceil(w / cellSize) + 1, rows: Math.ceil(h / cellSize) + 1 });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [cellSize]);

  const cells = useMemo(
    () => Array.from({ length: dims.rows * dims.cols }, (_, i) =>
      ({ r: Math.floor(i / dims.cols), c: i % dims.cols })),
    [dims.rows, dims.cols],
  );

  return (
    <div ref={ref} className={cn('absolute inset-0 h-full w-full overflow-hidden', className)} aria-hidden="true">
      {/* soft theme glow */}
      <div className="absolute inset-0"
           style={{ background: 'radial-gradient(ellipse 80% 70% at 50% 0%, rgb(99 102 241 / 0.16), transparent 72%)' }} />
      {/* full-cover grid */}
      <div
        key={rippleKey}
        className="absolute inset-0 grid"
        style={{
          gridTemplateColumns: `repeat(${dims.cols}, ${cellSize}px)`,
          gridTemplateRows: `repeat(${dims.rows}, ${cellSize}px)`,
        }}
      >
        {cells.map((cell, i) => {
          const dist = clicked ? Math.hypot(cell.r - clicked.r, cell.c - clicked.c) : 0;
          return (
            <button
              key={i}
              type="button"
              tabIndex={-1}
              onClick={() => { setClicked(cell); setRippleKey((k) => k + 1); }}
              className="ripple-cell border-[0.5px] border-astra-500/15 transition-all duration-300
                         hover:bg-astra-500/30 hover:border-astra-500/60 hover:shadow-[inset_0_0_18px_rgb(99_102_241_/_0.35)]"
              style={clicked ? { animationDelay: `${dist * 50}ms` } : undefined}
            />
          );
        })}
      </div>
      {/* gentle edge vignette so the card stays readable, grid still visible everywhere */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(ellipse 75% 75% at 50% 50%, transparent 55%, rgb(var(--c-bg) / 0.55) 100%)' }} />
    </div>
  );
}
