'use client';
// A rounded-square photo that sits in black & white, then floods into colour on
// hover — the colour layer is revealed by a circular clip-path expanding from the
// centre, like a drop of ink spreading through water.

import { useState } from 'react';
import { cn } from '../../lib/utils';

export default function TeamPhoto({ src, alt, size = 96 }: { src: string; alt: string; size?: number }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      className="relative mx-auto rounded-2xl overflow-hidden ring-1 ring-edge shadow-card"
      style={{ width: size, height: size }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Base: grayscale */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} width={size} height={size}
           className="absolute inset-0 w-full h-full object-cover grayscale" />
      {/* Colour layer, revealed by an expanding circular clip (ink-in-water) */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="" aria-hidden="true" width={size} height={size}
           className={cn('absolute inset-0 w-full h-full object-cover transition-[clip-path] duration-700 ease-out')}
           style={{ clipPath: hover ? 'circle(150% at 50% 50%)' : 'circle(0% at 50% 50%)' }} />
    </div>
  );
}
