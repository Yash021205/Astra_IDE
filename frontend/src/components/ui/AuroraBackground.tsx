'use client';
// Aceternity-style aurora background — soft animated blobs of color
// that drift across the screen. Pure CSS, no JS animation loop.

import { cn } from '../../lib/utils';

export default function AuroraBackground({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn('relative overflow-hidden bg-slate-950', className)}>
      <div className="aurora-layer aurora-1" />
      <div className="aurora-layer aurora-2" />
      <div className="aurora-layer aurora-3" />
      <div className="aurora-grain" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
