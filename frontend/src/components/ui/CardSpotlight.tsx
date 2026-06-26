'use client';
// Aceternity "Card Spotlight" — a glassy card whose surface reveals a soft radial
// spotlight that follows the cursor, over a faint animated dot matrix. Themed to
// ASTRA. Wrap any content (e.g. an auth form).

import { useRef, useState, type MouseEvent } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils';

export default function CardSpotlight({
  children, className, radius = 350,
}: {
  children: React.ReactNode; className?: string; radius?: number;
}) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  function onMouseMove(e: MouseEvent<HTMLDivElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={cn(
        'group relative overflow-hidden rounded-2xl border border-white/15',
        'bg-white/70 dark:bg-slate-900/50 backdrop-blur-2xl shadow-pop',
        className,
      )}
    >
      {/* spotlight following the cursor */}
      <motion.div
        className="pointer-events-none absolute -inset-px z-0 opacity-0 transition duration-300 group-hover:opacity-100"
        style={{
          background: `radial-gradient(${radius}px circle at ${pos.x}px ${pos.y}px, rgb(176 196 177 / 0.28), transparent 70%)`,
        }}
        animate={{ opacity: hovered ? 1 : 0 }}
      />
      {/* faint dot matrix */}
      <div className="pointer-events-none absolute inset-0 z-0 opacity-40"
           style={{
             backgroundImage: 'radial-gradient(rgb(148 163 184 / 0.25) 1px, transparent 1px)',
             backgroundSize: '16px 16px',
           }} />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
