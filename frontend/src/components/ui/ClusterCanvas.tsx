'use client';
// Interactive cluster visualization — magnetic nodes connected by animated lines.
//
// Each cluster (cluster-a / cluster-b) is a "moon" with worker pods orbiting it.
// Nodes are attracted/repelled by the cursor (magnetic). Lines between nodes
// pulse to show data flow (PPO scheduler events, eBPF telemetry, etc.).
//
// Built on a 2D canvas + requestAnimationFrame — no WebGL, no deps.

import { useEffect, useRef, useState } from 'react';
import { cn } from '../../lib/utils';

export interface ClusterNode {
  id:        string;
  label:     string;
  cluster:   string;       // grouping key
  type:      'control' | 'worker' | 'sandbox' | 'pod';
  sandbox?:  'runc' | 'gvisor' | 'firecracker';
  x:         number;       // 0..1 normalized
  y:         number;       // 0..1 normalized
  // Computed/transient — set by animation loop
  cx?:       number;
  cy?:       number;
  vx?:       number;
  vy?:       number;
}

export interface ClusterEdge {
  from:   string;
  to:     string;
  flow?:  number;          // 0..1 — strength / activity level
  kind?:  'control' | 'data' | 'telemetry';
}

interface Props {
  nodes:     ClusterNode[];
  edges:     ClusterEdge[];
  className?: string;
  height?:   number;
}

const COLOR_MAP = {
  control:      '#3b82f6',
  worker:       '#a855f7',
  sandbox:      '#10b981',
  pod_runc:     '#10b981',
  pod_gvisor:   '#f59e0b',
  pod_firecracker: '#ef4444',
  edge_control: 'rgba(59,130,246,0.4)',
  edge_data:    'rgba(168,85,247,0.4)',
  edge_telemetry: 'rgba(16,185,129,0.4)',
  bg:           '#020617',
  grid:         'rgba(148,163,184,0.05)',
};

function colorForNode(n: ClusterNode): string {
  if (n.type === 'control') return COLOR_MAP.control;
  if (n.type === 'worker')  return COLOR_MAP.worker;
  if (n.type === 'pod' && n.sandbox === 'runc')        return COLOR_MAP.pod_runc;
  if (n.type === 'pod' && n.sandbox === 'gvisor')      return COLOR_MAP.pod_gvisor;
  if (n.type === 'pod' && n.sandbox === 'firecracker') return COLOR_MAP.pod_firecracker;
  return COLOR_MAP.worker;
}

function radiusForNode(n: ClusterNode): number {
  if (n.type === 'control') return 18;
  if (n.type === 'worker')  return 12;
  if (n.type === 'pod')     return 7;
  return 9;
}

export default function ClusterCanvas({ nodes, edges, className, height = 460 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<ClusterNode | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf  = 0;
    let mouseX = -1000, mouseY = -1000;
    const dpr  = window.devicePixelRatio || 1;

    // Initialize each node's transient state
    const live = nodes.map((n) => ({ ...n, cx: 0, cy: 0, vx: 0, vy: 0 }));

    const resize = () => {
      const parent = canvas.parentElement!;
      const w = parent.clientWidth;
      const h = height;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width  = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.scale(dpr, dpr);
      // Anchor: convert normalized x/y to pixels
      for (const n of live) {
        n.cx = n.x * w;
        n.cy = n.y * h;
        n.vx = 0; n.vy = 0;
      }
    };

    const onMove = (e: MouseEvent) => {
      const r = canvas.getBoundingClientRect();
      mouseX = e.clientX - r.left;
      mouseY = e.clientY - r.top;
      // Hit-test for hover
      let found: ClusterNode | null = null;
      for (const n of live) {
        const dx = mouseX - n.cx!;
        const dy = mouseY - n.cy!;
        if (dx * dx + dy * dy < radiusForNode(n) ** 2 * 2.5) {
          found = n; break;
        }
      }
      setHovered(found);
    };
    const onLeave = () => { mouseX = -1000; mouseY = -1000; setHovered(null); };

    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
    window.addEventListener('resize', resize);

    let t = 0;

    const tick = () => {
      t += 0.016;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;

      // Clear
      ctx.fillStyle = COLOR_MAP.bg;
      ctx.fillRect(0, 0, w, h);

      // Light grid
      ctx.strokeStyle = COLOR_MAP.grid;
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += 40) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Physics: spring back to anchor + magnetic mouse attraction
      for (const n of live) {
        const anchorX = n.x * w;
        const anchorY = n.y * h;

        // Spring pull to anchor
        const springX = (anchorX - n.cx!) * 0.04;
        const springY = (anchorY - n.cy!) * 0.04;
        n.vx! += springX;
        n.vy! += springY;

        // Magnetic attraction toward cursor (within range)
        const dx = mouseX - n.cx!;
        const dy = mouseY - n.cy!;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 180 && dist > 0) {
          const strength = (180 - dist) / 180 * 0.6;
          n.vx! += (dx / dist) * strength;
          n.vy! += (dy / dist) * strength;
        }

        // Damping
        n.vx! *= 0.82;
        n.vy! *= 0.82;
        n.cx! += n.vx!;
        n.cy! += n.vy!;
      }

      // Edges (drawn first, behind nodes)
      for (const e of edges) {
        const a = live.find((n) => n.id === e.from);
        const b = live.find((n) => n.id === e.to);
        if (!a || !b) continue;
        const flow = (e.flow ?? 0.5);

        const kind = e.kind ?? 'data';
        const baseColor =
          kind === 'control'   ? COLOR_MAP.edge_control :
          kind === 'telemetry' ? COLOR_MAP.edge_telemetry :
                                  COLOR_MAP.edge_data;

        ctx.strokeStyle = baseColor;
        ctx.lineWidth = 1 + flow * 1.5;
        ctx.beginPath();
        ctx.moveTo(a.cx!, a.cy!);
        ctx.lineTo(b.cx!, b.cy!);
        ctx.stroke();

        // Pulsing dot traveling along the edge
        const phase = ((t * (0.4 + flow * 0.6)) + (a.cx! + a.cy!) * 0.002) % 1;
        const px = a.cx! + (b.cx! - a.cx!) * phase;
        const py = a.cy! + (b.cy! - a.cy!) * phase;
        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = baseColor.replace(/0\.\d+/, '0.95');
        ctx.fill();
      }

      // Nodes
      for (const n of live) {
        const r = radiusForNode(n);
        const color = colorForNode(n);

        // Soft glow
        const glow = ctx.createRadialGradient(n.cx!, n.cy!, 0, n.cx!, n.cy!, r * 2.5);
        glow.addColorStop(0, color);
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.arc(n.cx!, n.cy!, r * 2.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;

        // Core
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(n.cx!, n.cy!, r, 0, Math.PI * 2);
        ctx.fill();

        // Outline
        ctx.strokeStyle = 'rgba(255,255,255,0.6)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Label for control + worker only (avoid clutter for pods)
        if (n.type === 'control' || n.type === 'worker') {
          ctx.fillStyle = 'rgba(255,255,255,0.85)';
          ctx.font = '11px JetBrains Mono, Menlo, monospace';
          ctx.textAlign = 'center';
          ctx.fillText(n.label, n.cx!, n.cy! + r + 14);
        }
      }

      raf = requestAnimationFrame(tick);
    };

    resize();
    tick();

    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mouseleave', onLeave);
      window.removeEventListener('resize', resize);
    };
  }, [nodes, edges, height]);

  return (
    <div className={cn('relative rounded-xl overflow-hidden border border-slate-800 bg-slate-950', className)}>
      <canvas ref={canvasRef} className="block w-full" />

      {/* Hovered node tooltip */}
      {hovered && (
        <div className="absolute top-3 left-3 px-3 py-2 rounded-lg bg-slate-900/95 border border-slate-700 text-xs shadow-xl backdrop-blur z-10 pointer-events-none">
          <div className="font-semibold text-white">{hovered.label}</div>
          <div className="text-slate-400 mt-0.5">
            {hovered.type}
            {hovered.sandbox && <span className="ml-2">· {hovered.sandbox}</span>}
            {hovered.cluster && <span className="ml-2">· {hovered.cluster}</span>}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-3 right-3 px-3 py-2 rounded-lg bg-slate-900/95 border border-slate-700 text-[10px] shadow-xl backdrop-blur z-10 pointer-events-none">
        <div className="space-y-1">
          <LegendDot color={COLOR_MAP.control} label="Control plane" />
          <LegendDot color={COLOR_MAP.worker}  label="Worker node" />
          <LegendDot color={COLOR_MAP.pod_runc}     label="runc pod" />
          <LegendDot color={COLOR_MAP.pod_gvisor}   label="gVisor pod" />
          <LegendDot color={COLOR_MAP.pod_firecracker} label="Firecracker pod" />
        </div>
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
