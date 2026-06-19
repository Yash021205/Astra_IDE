'use client';
// Aceternity-style Spotlight — a radial gradient that follows the user's
// cursor across its parent, creating a "lit by a spotlight" effect.

import { useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';

interface SpotlightProps {
  className?: string;
  fill?: string;
}

export default function Spotlight({ className, fill = 'white' }: SpotlightProps) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const parent = svg.parentElement;
    if (!parent) return;

    const onMouseMove = (e: MouseEvent) => {
      const rect = parent.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      svg.style.setProperty('--mx', `${x}px`);
      svg.style.setProperty('--my', `${y}px`);
    };
    parent.addEventListener('mousemove', onMouseMove);
    return () => parent.removeEventListener('mousemove', onMouseMove);
  }, []);

  return (
    <svg
      ref={ref}
      className={cn(
        'pointer-events-none absolute inset-0 h-full w-full opacity-50 mix-blend-screen',
        className,
      )}
      style={{
        maskImage:
          'radial-gradient(circle 240px at var(--mx, 50%) var(--my, 50%), white, transparent)',
        WebkitMaskImage:
          'radial-gradient(circle 240px at var(--mx, 50%) var(--my, 50%), white, transparent)',
      }}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 800 800"
      fill="none"
    >
      <circle cx="400" cy="400" r="400" fill={fill} fillOpacity="0.18" />
    </svg>
  );
}
