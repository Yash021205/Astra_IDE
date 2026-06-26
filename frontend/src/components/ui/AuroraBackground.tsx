'use client';
// Theme-aware hero backdrop. Light mode: a calm, static soft-pastel gradient
// (linen / lavender / mint / periwinkle). Dark mode: subtle drifting aurora in
// the brand greens. No grain, no pointer-reactive animation.

import { cn } from '../../lib/utils';

export default function AuroraBackground({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn('relative overflow-hidden bg-bg', className)}>
      {/* Light: static pastel wash */}
      <div className="absolute inset-0 dark:hidden pointer-events-none aurora-light" aria-hidden="true" />
      {/* Dark: gentle aurora blobs */}
      <div className="absolute inset-0 hidden dark:block pointer-events-none" aria-hidden="true">
        <div className="aurora-layer aurora-1" />
        <div className="aurora-layer aurora-2" />
        <div className="aurora-layer aurora-3" />
      </div>
      <div className="relative z-10">{children}</div>
    </div>
  );
}
