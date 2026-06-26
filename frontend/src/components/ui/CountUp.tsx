'use client';
// Counts a number up to its target when it scrolls into view (eases out).
// Supports a prefix/suffix and decimals so "< 2s", "78%+", "< 20ms" animate.

import { useEffect, useRef, useState } from 'react';

export default function CountUp({
  value, prefix = '', suffix = '', decimals = 0, duration = 1400, className,
}: {
  value: number; prefix?: string; suffix?: string; decimals?: number; duration?: number; className?: string;
}) {
  const [n, setN] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && !started.current) {
        started.current = true;
        const t0 = performance.now();
        const tick = (t: number) => {
          const p = Math.min(1, (t - t0) / duration);
          const eased = 1 - Math.pow(1 - p, 3);   // easeOutCubic
          setN(value * eased);
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [value, duration]);

  return (
    <span ref={ref} className={className}>
      {prefix}{n.toFixed(decimals)}{suffix}
    </span>
  );
}
