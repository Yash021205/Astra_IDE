'use client';
// SVG text that sits as a faint outline, then reveals a gradient fill under the
// cursor. Simplified: single clean stroke (no overlapping blocks), mask-based
// cursor reveal, theme-aware stroke colour.

import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

interface Props {
  text:       string;
  className?: string;
  duration?:  number;
}

export default function TextHoverEffect({ text, className, duration = 0.35 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hovered, setHovered] = useState(false);
  const [pos, setPos] = useState({ cx: '50%', cy: '50%' });

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onMove = (e: MouseEvent) => {
      const r = svg.getBoundingClientRect();
      setPos({ cx: `${((e.clientX - r.left) / r.width) * 100}%`,
               cy: `${((e.clientY - r.top)  / r.height) * 100}%` });
    };
    svg.addEventListener('mousemove', onMove);
    return () => svg.removeEventListener('mousemove', onMove);
  }, []);

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 900 200"
      width="100%" height="100%"
      xmlns="http://www.w3.org/2000/svg"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={className}
    >
      <defs>
        <linearGradient id="the-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"   stopColor="#618764" />
          <stop offset="30%"  stopColor="#9CB080" />
          <stop offset="60%"  stopColor="#e8b0bb" />
          <stop offset="100%" stopColor="#cddafd" />
        </linearGradient>
        <motion.radialGradient
          id="reveal"
          gradientUnits="userSpaceOnUse"
          r="22%"
          initial={{ cx: '50%', cy: '50%' }}
          animate={pos}
          transition={{ duration, ease: 'easeOut' }}
        >
          <stop offset="0%"   stopColor="white" />
          <stop offset="100%" stopColor="black" />
        </motion.radialGradient>
        <mask id="tmask">
          <rect x="0" y="0" width="100%" height="100%" fill="url(#reveal)" />
        </mask>
      </defs>

      {/* Base: thin outline only, no fill — clean, no overlapping blocks */}
      <text
        x="50%" y="50%"
        textAnchor="middle" dominantBaseline="middle"
        fill="none"
        stroke="rgb(var(--c-muted))"
        strokeWidth="0.6"
        style={{ fontSize: '7.5rem', fontFamily: 'var(--font-sans)', fontWeight: 800, letterSpacing: '-0.04em' }}
        opacity={hovered ? 0.85 : 0.55}
      >
        {text}
      </text>

      {/* Cursor-revealed gradient fill */}
      <text
        x="50%" y="50%"
        textAnchor="middle" dominantBaseline="middle"
        fill="url(#the-grad)"
        mask="url(#tmask)"
        stroke="none"
        style={{ fontSize: '7.5rem', fontFamily: 'var(--font-sans)', fontWeight: 800, letterSpacing: '-0.04em' }}
      >
        {text}
      </text>
    </svg>
  );
}
