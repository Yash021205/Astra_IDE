'use client';
// Aceternity-style canvas text — renders the heading on a canvas with
// per-letter particles that react to the cursor (magnetic dispersion).
//
// Pure canvas + requestAnimationFrame — no three.js dependency.

import { useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';

interface Props {
  text:        string;
  className?:  string;
  height?:     number;
  fontSize?:   number;
  fontWeight?: number;
  /** Gradient colors used for the text fill (left → right). */
  gradient?:   [string, string, string];
}

interface Particle {
  ox: number;  oy: number;     // origin
  x:  number;  y:  number;     // current
  vx: number;  vy: number;     // velocity
  color: string;
}

export default function CanvasText({
  text, className,
  height     = 200,
  fontSize   = 96,
  fontWeight = 800,
  gradient   = ['#dedbd2', '#b0c4b1', '#edafb8'],
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    let particles: Particle[] = [];
    let mouseX = -1000, mouseY = -1000;
    let raf = 0;

    const setup = () => {
      const parent = canvas.parentElement!;
      const w = parent.clientWidth;
      const h = height;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width  = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.scale(dpr, dpr);

      // Draw the text once into an offscreen canvas to sample pixels
      const off = document.createElement('canvas');
      off.width  = w;
      off.height = h;
      const octx = off.getContext('2d')!;
      octx.fillStyle = '#fff';
      octx.font = `${fontWeight} ${fontSize}px "Inter", system-ui, sans-serif`;
      octx.textAlign = 'left';
      octx.textBaseline = 'top';

      // Auto-shrink if text overflows
      let actualFontSize = fontSize;
      while (octx.measureText(text).width > w && actualFontSize > 16) {
        actualFontSize -= 2;
        octx.font = `${fontWeight} ${actualFontSize}px "Inter", system-ui, sans-serif`;
      }
      const metrics = octx.measureText(text);
      const textW = metrics.width;
      const x0 = (w - textW) / 2;
      const y0 = (h - actualFontSize) / 2;
      octx.fillText(text, x0, y0);

      // Sample every 3px — find pixels with alpha > 200, make a particle
      const data = octx.getImageData(0, 0, w, h).data;
      particles = [];
      const step = 3;
      for (let y = 0; y < h; y += step) {
        for (let x = 0; x < w; x += step) {
          const idx = (y * w + x) * 4;
          if (data[idx + 3] > 200) {
            const ratio = textW > 0 ? (x - x0) / textW : 0;
            particles.push({
              ox: x, oy: y, x, y, vx: 0, vy: 0,
              color: lerpGradient(gradient, Math.max(0, Math.min(1, ratio))),
            });
          }
        }
      }
    };

    const onMove = (e: MouseEvent) => {
      const r = canvas.getBoundingClientRect();
      mouseX = e.clientX - r.left;
      mouseY = e.clientY - r.top;
    };
    const onLeave = () => { mouseX = -1000; mouseY = -1000; };

    const tick = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);

      for (const p of particles) {
        // Magnetic repulsion: closer to mouse → pushed away
        const dx = p.x - mouseX;
        const dy = p.y - mouseY;
        const dist2 = dx * dx + dy * dy;
        if (dist2 < 9000) {
          const f = (9000 - dist2) / 9000 * 0.4;
          p.vx += (dx / Math.sqrt(dist2 + 0.001)) * f;
          p.vy += (dy / Math.sqrt(dist2 + 0.001)) * f;
        }
        // Spring back to origin
        p.vx += (p.ox - p.x) * 0.04;
        p.vy += (p.oy - p.y) * 0.04;
        // Damping
        p.vx *= 0.86;
        p.vy *= 0.86;
        p.x  += p.vx;
        p.y  += p.vy;

        ctx.fillStyle = p.color;
        ctx.fillRect(p.x, p.y, 2.2, 2.2);
      }
      raf = requestAnimationFrame(tick);
    };

    setup();
    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
    window.addEventListener('resize', setup);
    tick();
    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mouseleave', onLeave);
      window.removeEventListener('resize', setup);
    };
  }, [text, height, fontSize, fontWeight, gradient]);

  return (
    <canvas
      ref={canvasRef}
      className={cn('block w-full cursor-default', className)}
      aria-label={text}
      role="img"
    />
  );
}

// Linear interpolation across a 3-color gradient
function lerpGradient(colors: [string, string, string], t: number): string {
  if (t < 0.5) {
    return mix(colors[0], colors[1], t * 2);
  }
  return mix(colors[1], colors[2], (t - 0.5) * 2);
}

function mix(a: string, b: string, t: number): string {
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const r = Math.round(A.r + (B.r - A.r) * t);
  const g = Math.round(A.g + (B.g - A.g) * t);
  const bb = Math.round(A.b + (B.b - A.b) * t);
  return `rgb(${r}, ${g}, ${bb})`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return { r: 255, g: 255, b: 255 };
  return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) };
}
