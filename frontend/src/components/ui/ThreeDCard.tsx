'use client';
// 3D card — tilts toward the mouse on hover, with depth shadow and a
// floating glare highlight. More pronounced than the previous version.

import { useRef, useState, useEffect } from 'react';
import { cn } from '../../lib/utils';

interface Props {
  children:   React.ReactNode;
  className?: string;
  /** Tilt magnitude in degrees at the corner. Bigger = more dramatic. */
  intensity?: number;
  /** If true, no perspective container wrapper is added (use when parent
   *  already establishes the perspective). */
  flat?:      boolean;
}

export default function ThreeDCard({
  children, className, intensity = 14, flat = false,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({});
  const [hovered, setHovered] = useState(false);
  const [glare, setGlare] = useState({ x: 50, y: 50 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top)  / r.height;
      const rx = (py - 0.5) * -2 * intensity;
      const ry = (px - 0.5) *  2 * intensity;
      setStyle({
        transform:
          `perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) scale3d(1.04, 1.04, 1.04)`,
        boxShadow: hovered
          ? `0 28px 40px -16px rgba(59,130,246,0.35), 0 12px 20px -8px rgba(168,85,247,0.25)`
          : '',
      });
      setGlare({ x: px * 100, y: py * 100 });
    };
    const onEnter = () => setHovered(true);
    const onLeave = () => {
      setHovered(false);
      setStyle({
        transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)',
        boxShadow: '',
      });
    };

    el.addEventListener('mousemove',  onMove);
    el.addEventListener('mouseenter', onEnter);
    el.addEventListener('mouseleave', onLeave);
    return () => {
      el.removeEventListener('mousemove',  onMove);
      el.removeEventListener('mouseenter', onEnter);
      el.removeEventListener('mouseleave', onLeave);
    };
  }, [intensity, hovered]);

  const inner = (
    <div
      ref={ref}
      className={cn(
        'relative transition-transform duration-150 ease-out will-change-transform',
        className,
      )}
      style={{ transformStyle: 'preserve-3d', ...style }}
    >
      {children}
      {/* Glare highlight — only when hovered */}
      {hovered && (
        <div
          className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-40 mix-blend-overlay"
          style={{
            background: `radial-gradient(circle at ${glare.x}% ${glare.y}%, rgba(255,255,255,0.45), transparent 50%)`,
          }}
        />
      )}
    </div>
  );

  if (flat) return inner;
  return <div className="[perspective:1000px]">{inner}</div>;
}
