'use client';
// Aceternity-inspired 3D globe — wireframe sphere with latitude/longitude
// rings, animated arcs between markers, magnetic interactivity (drag to
// rotate, mouse-hover highlights nearby markers).
//
// Built on a 2D canvas with manual 3D projection. No three.js — keeps the
// bundle slim and avoids the GPU dependency.

import { useEffect, useRef, useState } from 'react';
import { cn } from '../../lib/utils';

export interface GlobeMarker {
  id:        string;
  label:     string;
  lat:       number;     // degrees
  lng:       number;     // degrees
  color?:    string;
  size?:     number;
  kind?:     'cluster' | 'user' | 'workspace';
}

export interface GlobeArc {
  fromId:    string;
  toId:      string;
  color?:    string;
  /** 0..1 — arc activity (drives pulse speed/brightness) */
  flow?:     number;
}

interface Props {
  markers:    GlobeMarker[];
  arcs?:      GlobeArc[];
  className?: string;
  height?:    number;
  /** Auto-rotation rate in degrees / frame (set to 0 to pause). */
  rotateRate?: number;
}

const COLORS = {
  bg:         '#020617',
  sphere:     'rgba(59, 130, 246, 0.18)',
  sphereLine: 'rgba(99, 102, 241, 0.25)',
  cluster:    '#60a5fa',
  user:       '#a855f7',
  workspace:  '#ec4899',
  arc:        'rgba(99, 102, 241, 0.6)',
  arcGlow:    'rgba(168, 85, 247, 0.9)',
};

export default function InteractiveGlobe({
  markers, arcs = [], className, height = 480, rotateRate = 0.2,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<GlobeMarker | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    let raf = 0;
    let rotY = 30;    // current rotation (degrees)
    let rotX = -15;
    let velY = rotateRate;
    let velX = 0;
    let isDragging = false;
    let lastMouseX = 0, lastMouseY = 0;
    let mouseX = -1000, mouseY = -1000;

    const resize = () => {
      const parent = canvas.parentElement!;
      const w = parent.clientWidth;
      const h = height;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width  = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.scale(dpr, dpr);
    };

    const onMove = (e: MouseEvent) => {
      const r = canvas.getBoundingClientRect();
      mouseX = e.clientX - r.left;
      mouseY = e.clientY - r.top;
      if (isDragging) {
        velY = (e.clientX - lastMouseX) * 0.4;
        velX = (e.clientY - lastMouseY) * 0.4;
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
      }
    };
    const onDown = (e: MouseEvent) => {
      isDragging = true;
      lastMouseX = e.clientX;
      lastMouseY = e.clientY;
      velY = 0; velX = 0;
    };
    const onUp = () => {
      isDragging = false;
      // After drag, ease back toward gentle auto-rotation
      setTimeout(() => { if (!isDragging) velY = rotateRate; }, 300);
    };
    const onLeave = () => { mouseX = -1000; mouseY = -1000; };

    canvas.addEventListener('mousemove',  onMove);
    canvas.addEventListener('mousedown',  onDown);
    window.addEventListener('mouseup',    onUp);
    canvas.addEventListener('mouseleave', onLeave);
    window.addEventListener('resize',     resize);
    resize();

    let t = 0;

    const tick = () => {
      t += 0.016;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const cx = w / 2;
      const cy = h / 2;
      const R = Math.min(w, h) * 0.42;

      ctx.fillStyle = COLORS.bg;
      ctx.fillRect(0, 0, w, h);

      // Apply rotation velocities
      if (!isDragging) {
        velY *= 0.96;
        velX *= 0.92;
        if (Math.abs(velY) < rotateRate) velY = rotateRate;
      }
      rotY += velY;
      rotX += velX;
      rotX = clamp(rotX, -60, 60);

      const rxR = (rotX * Math.PI) / 180;
      const ryR = (rotY * Math.PI) / 180;

      // ─── Draw sphere outline + grid (latitude / longitude rings) ────────
      ctx.strokeStyle = COLORS.sphereLine;
      ctx.lineWidth = 0.5;

      // Latitude rings
      for (let lat = -75; lat <= 75; lat += 15) {
        ctx.beginPath();
        for (let lng = 0; lng <= 360; lng += 4) {
          const p = project(lat, lng, R, rxR, ryR);
          if (p.z < 0) continue;
          if (lng === 0) ctx.moveTo(cx + p.x, cy + p.y);
          else ctx.lineTo(cx + p.x, cy + p.y);
        }
        ctx.stroke();
      }
      // Longitude rings
      for (let lng = 0; lng < 360; lng += 30) {
        ctx.beginPath();
        let first = true;
        for (let lat = -90; lat <= 90; lat += 4) {
          const p = project(lat, lng, R, rxR, ryR);
          if (p.z < 0) continue;
          if (first) { ctx.moveTo(cx + p.x, cy + p.y); first = false; }
          else ctx.lineTo(cx + p.x, cy + p.y);
        }
        ctx.stroke();
      }

      // Soft inner glow
      const glow = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 1.1);
      glow.addColorStop(0, 'rgba(99, 102, 241, 0.12)');
      glow.addColorStop(1, 'rgba(99, 102, 241, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.05, 0, Math.PI * 2);
      ctx.fill();

      // ─── Arcs ─────────────────────────────────────────────────────────────
      for (const arc of arcs) {
        const a = markers.find((m) => m.id === arc.fromId);
        const b = markers.find((m) => m.id === arc.toId);
        if (!a || !b) continue;

        const pa = project(a.lat, a.lng, R, rxR, ryR);
        const pb = project(b.lat, b.lng, R, rxR, ryR);

        // Skip arcs where both ends are on the back side
        if (pa.z < 0 && pb.z < 0) continue;

        const flow = arc.flow ?? 0.5;
        const color = arc.color ?? COLORS.arc;

        // Draw a quadratic Bezier curve bulging away from the sphere
        const midX = (pa.x + pb.x) / 2;
        const midY = (pa.y + pb.y) / 2;
        const len = Math.sqrt((pb.x - pa.x) ** 2 + (pb.y - pa.y) ** 2);
        const bulge = Math.min(len * 0.5, R * 0.45);
        const cpX = midX;
        const cpY = midY - bulge;

        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2 + flow * 1.5;
        ctx.beginPath();
        ctx.moveTo(cx + pa.x, cy + pa.y);
        ctx.quadraticCurveTo(cx + cpX, cy + cpY, cx + pb.x, cy + pb.y);
        ctx.stroke();

        // Pulse traveling along arc
        const phase = ((t * (0.3 + flow * 0.6)) + arcs.indexOf(arc) * 0.13) % 1;
        const pulseX = quadBezier(pa.x, cpX, pb.x, phase);
        const pulseY = quadBezier(pa.y, cpY, pb.y, phase);
        ctx.beginPath();
        ctx.arc(cx + pulseX, cy + pulseY, 3, 0, Math.PI * 2);
        ctx.fillStyle = COLORS.arcGlow;
        ctx.fill();
      }

      // ─── Markers ─────────────────────────────────────────────────────────
      let bestHover: { marker: GlobeMarker; dist: number } | null = null;

      for (const m of markers) {
        const p = project(m.lat, m.lng, R, rxR, ryR);
        if (p.z < 0) continue;  // back of globe

        const size  = (m.size ?? 6) * (1 + p.z * 0.5);  // depth scale
        const color = m.color ?? colorForKind(m.kind);

        // Glow
        const g = ctx.createRadialGradient(cx + p.x, cy + p.y, 0, cx + p.x, cy + p.y, size * 4);
        g.addColorStop(0, color);
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.arc(cx + p.x, cy + p.y, size * 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;

        // Core
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(cx + p.x, cy + p.y, size, 0, Math.PI * 2);
        ctx.fill();

        // Outline
        ctx.strokeStyle = 'rgba(255,255,255,0.85)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Label for clusters always; users only on hover
        if (m.kind === 'cluster') {
          ctx.fillStyle = 'rgba(255,255,255,0.9)';
          ctx.font = '11px JetBrains Mono, Menlo, monospace';
          ctx.textAlign = 'center';
          ctx.fillText(m.label, cx + p.x, cy + p.y - size - 8);
        }

        // Hit test
        const dx = mouseX - (cx + p.x);
        const dy = mouseY - (cy + p.y);
        const d  = Math.sqrt(dx * dx + dy * dy);
        if (d < size + 8) {
          if (!bestHover || d < bestHover.dist) {
            bestHover = { marker: m, dist: d };
          }
        }
      }

      setHovered(bestHover?.marker ?? null);
      raf = requestAnimationFrame(tick);
    };

    tick();
    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener('mousemove',  onMove);
      canvas.removeEventListener('mousedown',  onDown);
      window.removeEventListener('mouseup',    onUp);
      canvas.removeEventListener('mouseleave', onLeave);
      window.removeEventListener('resize',     resize);
    };
  }, [markers, arcs, height, rotateRate]);

  return (
    <div className={cn('relative rounded-xl overflow-hidden border border-slate-800 bg-slate-950', className)}>
      <canvas ref={canvasRef} className="block w-full cursor-grab active:cursor-grabbing" />

      {hovered && (
        <div className="absolute top-3 left-3 px-3 py-2 rounded-lg bg-slate-900/95 border border-slate-700 text-xs shadow-xl backdrop-blur z-10 pointer-events-none">
          <div className="font-semibold text-white">{hovered.label}</div>
          <div className="text-slate-400 mt-0.5">
            {hovered.kind ?? 'marker'}
            <span className="ml-2 font-mono">
              {hovered.lat.toFixed(1)}°, {hovered.lng.toFixed(1)}°
            </span>
          </div>
        </div>
      )}

      <div className="absolute bottom-3 left-3 text-[10px] text-slate-500 pointer-events-none">
        drag to rotate
      </div>

      <div className="absolute bottom-3 right-3 px-3 py-2 rounded-lg bg-slate-900/95 border border-slate-700 text-[10px] shadow-xl backdrop-blur z-10 pointer-events-none">
        <LegendDot color={COLORS.cluster}   label="Cluster"   />
        <LegendDot color={COLORS.user}      label="User"      />
        <LegendDot color={COLORS.workspace} label="Workspace" />
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2 text-slate-300">
      <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </div>
  );
}

// ── 3D math ──────────────────────────────────────────────────────────────────

function project(lat: number, lng: number, R: number, rotX: number, rotY: number) {
  const phi   = (lat * Math.PI) / 180;
  const theta = (lng * Math.PI) / 180;

  // Spherical → Cartesian on unit sphere
  let x = Math.cos(phi) * Math.sin(theta);
  let y = Math.sin(phi);
  let z = Math.cos(phi) * Math.cos(theta);

  // Apply Y rotation
  const sy = Math.sin(rotY), cy = Math.cos(rotY);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  x = x1; z = z1;

  // Apply X rotation
  const sx = Math.sin(rotX), cx = Math.cos(rotX);
  const y1 = y * cx - z * sx;
  const z2 = y * sx + z * cx;
  y = y1; z = z2;

  return { x: x * R, y: -y * R, z };
}

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }
function quadBezier(a: number, c: number, b: number, t: number) {
  const it = 1 - t;
  return it * it * a + 2 * it * t * c + t * t * b;
}

function colorForKind(kind?: GlobeMarker['kind']): string {
  switch (kind) {
    case 'cluster':   return COLORS.cluster;
    case 'user':      return COLORS.user;
    case 'workspace': return COLORS.workspace;
    default:          return COLORS.cluster;
  }
}
