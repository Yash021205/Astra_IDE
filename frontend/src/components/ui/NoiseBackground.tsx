'use client';
// Aceternity "Noise" background — an animated film-grain texture layered over a
// gradient. Used as a CTA surface. Children render above the noise.

import { cn } from '../../lib/utils';

export default function NoiseBackground({
  children, className,
}: {
  children: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn(
      'relative overflow-hidden rounded-2xl',
      'bg-gradient-to-br from-astra-600 via-astra-500 to-blossom-400',
      className,
    )}>
      <div className="noise-layer pointer-events-none absolute inset-0 opacity-[0.18]" aria-hidden="true" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
