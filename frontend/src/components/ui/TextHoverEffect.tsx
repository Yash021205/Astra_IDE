'use client';
// Aceternity-style text-hover-effect — SVG stroke text where a gradient
// "reveals" the fill as the cursor moves across the text. Pure SVG +
// CSS — no canvas, ships small.

import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

interface Props {
  text:        string;
  className?:  string;
  duration?:   number;
}

export default function TextHoverEffect({ text, className, duration = 0.4 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hovered, setHovered] = useState(false);
  const [maskPosition, setMaskPosition] = useState({ cx: '50%', cy: '50%' });

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onMove = (e: MouseEvent) => {
      const rect = svg.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width)  * 100;
      const y = ((e.clientY - rect.top)  / rect.height) * 100;
      setMaskPosition({ cx: `${x}%`, cy: `${y}%` });
    };
    svg.addEventListener('mousemove', onMove);
    return () => svg.removeEventListener('mousemove', onMove);
  }, []);

  return (
    <svg
      ref={svgRef}
      width="100%" height="100%"
      viewBox="0 0 800 200" xmlns="http://www.w3.org/2000/svg"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={className}
    >
      <defs>
        <linearGradient id="textGrad" gradientUnits="userSpaceOnUse" cx="50%" cy="50%" r="25%">
          {hovered && (
            <>
              <stop offset="0%"   stopColor="#60a5fa" />
              <stop offset="25%"  stopColor="#a855f7" />
              <stop offset="50%"  stopColor="#ec4899" />
              <stop offset="75%"  stopColor="#f97316" />
              <stop offset="100%" stopColor="#facc15" />
            </>
          )}
        </linearGradient>
        <motion.radialGradient
          id="revealMask"
          gradientUnits="userSpaceOnUse"
          r="20%"
          initial={{ cx: '50%', cy: '50%' }}
          animate={maskPosition}
          transition={{ duration, ease: 'easeOut' }}
        >
          <stop offset="0%"   stopColor="white" />
          <stop offset="100%" stopColor="black" />
        </motion.radialGradient>
        <mask id="textMask">
          <rect x="0" y="0" width="100%" height="100%" fill="url(#revealMask)" />
        </mask>
      </defs>

      {/* Outlined text (always visible, neutral stroke) */}
      <text
        x="50%" y="50%"
        textAnchor="middle" dominantBaseline="middle"
        strokeWidth="0.5"
        className="fill-transparent stroke-slate-500 font-bold"
        style={{ fontSize: '7rem', fontWeight: 800, opacity: hovered ? 0.7 : 0.5 }}
      >
        {text}
      </text>

      {/* Animated stroke draw — runs on mount */}
      <motion.text
        x="50%" y="50%"
        textAnchor="middle" dominantBaseline="middle"
        strokeWidth="0.5"
        initial={{ strokeDashoffset: 1000, strokeDasharray: 1000 }}
        animate={{ strokeDashoffset: 0, strokeDasharray: 1000 }}
        transition={{ duration: 2, ease: 'easeInOut' }}
        className="fill-transparent stroke-astra-400 font-bold"
        style={{ fontSize: '7rem', fontWeight: 800 }}
      >
        {text}
      </motion.text>

      {/* Gradient-filled text revealed under cursor */}
      <text
        x="50%" y="50%"
        textAnchor="middle" dominantBaseline="middle"
        fill="url(#textGrad)"
        mask="url(#textMask)"
        strokeWidth="0.5"
        className="font-bold"
        style={{ fontSize: '7rem', fontWeight: 800 }}
      >
        {text}
      </text>
    </svg>
  );
}
