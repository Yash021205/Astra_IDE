'use client';
// Aceternity-style Sparkles — small twinkling stars rendered on a canvas
// behind text. Pure canvas + requestAnimationFrame.

import { useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';

interface SparklesProps {
  className?:    string;
  density?:      number;   // particles per 1000 px²
  minSize?:      number;
  maxSize?:      number;
  color?:        string;
  background?:   string;
}

export default function Sparkles({
  className,
  density    = 0.5,
  minSize    = 0.6,
  maxSize    = 1.4,
  color      = '#a5b4fc',
  background = 'transparent',
}: SparklesProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf = 0;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = window.devicePixelRatio || 1;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width  = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.scale(dpr, dpr);
      buildParticles(w, h);
    };

    interface Particle {
      x: number; y: number; size: number; opacity: number; speed: number;
    }
    let particles: Particle[] = [];

    const buildParticles = (w: number, h: number) => {
      const count = Math.max(20, Math.floor((w * h * density) / 1000));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        size: minSize + Math.random() * (maxSize - minSize),
        opacity: Math.random(),
        speed: 0.005 + Math.random() * 0.015,
      }));
    };

    const animate = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (background !== 'transparent') {
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, w, h);
      }
      for (const p of particles) {
        p.opacity += p.speed;
        if (p.opacity > 1 || p.opacity < 0) p.speed *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = Math.max(0, Math.min(1, p.opacity));
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(animate);
    };

    resize();
    animate();
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, [density, minSize, maxSize, color, background]);

  return (
    <canvas
      ref={canvasRef}
      className={cn('pointer-events-none absolute inset-0', className)}
    />
  );
}
