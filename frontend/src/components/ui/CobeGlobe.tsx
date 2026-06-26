'use client';
// Real WebGL globe (cobe v2) — a solid, lit, dotted Earth like Stripe/Linear use,
// not a wireframe. Drag to spin; auto-rotates otherwise. Coloured markers mark
// the three ASTRA clusters and connected user cities, with animated arcs routing
// each user to its nearest cluster.

import { useEffect, useRef, useState } from 'react';
import createGlobe from 'cobe';
import { cn } from '../../lib/utils';

const CLUSTER = [0.69, 0.77, 0.69] as [number, number, number]; // ash sage b0c4b1
const USER    = [0.93, 0.69, 0.72] as [number, number, number]; // blossom edafb8
const ARC     = [0.80, 0.73, 0.74] as [number, number, number]; // soft blossom-grey

const CLUSTERS = {
  a: [55.5, 9.5] as [number, number],     // Denmark
  b: [28.6, 77.2] as [number, number],    // India
  c: [37.7, -122.4] as [number, number],  // US (California)
  d: [1.35, 103.8] as [number, number],   // Singapore
};

const MARKERS = [
  { location: CLUSTERS.a, size: 0.1, color: CLUSTER },
  { location: CLUSTERS.b, size: 0.1, color: CLUSTER },
  { location: CLUSTERS.c, size: 0.1, color: CLUSTER },
  { location: CLUSTERS.d, size: 0.1, color: CLUSTER },
  { location: [19.07, 72.87], size: 0.045, color: USER },  // Mumbai
  { location: [12.97, 77.59], size: 0.045, color: USER },  // Bangalore
  { location: [52.52, 13.40], size: 0.045, color: USER },  // Berlin
  { location: [51.51, -0.13], size: 0.045, color: USER },  // London
  { location: [40.71, -74.01], size: 0.045, color: USER }, // New York
  { location: [35.68, 139.69], size: 0.045, color: USER }, // Tokyo
  { location: [-33.87, 151.21], size: 0.045, color: USER },// Sydney
  { location: [-23.55, -46.63], size: 0.045, color: USER },// Sao Paulo
  { location: [3.14, 101.69], size: 0.045, color: USER },  // Kuala Lumpur
];

const ARCS = [
  { from: [19.07, 72.87] as [number, number],  to: CLUSTERS.b, color: ARC },
  { from: [12.97, 77.59] as [number, number],  to: CLUSTERS.b, color: ARC },
  { from: [52.52, 13.40] as [number, number],  to: CLUSTERS.a, color: ARC },
  { from: [51.51, -0.13] as [number, number],  to: CLUSTERS.a, color: ARC },
  { from: [40.71, -74.01] as [number, number], to: CLUSTERS.c, color: ARC },
  { from: [35.68, 139.69] as [number, number], to: CLUSTERS.d, color: ARC },
  { from: [-33.87, 151.21] as [number, number], to: CLUSTERS.d, color: ARC },
  { from: [-23.55, -46.63] as [number, number], to: CLUSTERS.c, color: ARC },
  { from: [3.14, 101.69] as [number, number],  to: CLUSTERS.d, color: ARC },
];

export default function CobeGlobe({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerInteracting = useRef<number | null>(null);
  const pointerMovement = useRef(0);
  const [r, setR] = useState(0);

  useEffect(() => {
    let phi = 0;
    let width = 0;
    let raf = 0;
    const onResize = () => { if (canvasRef.current) width = canvasRef.current.offsetWidth; };
    window.addEventListener('resize', onResize);
    onResize();

    const globe = createGlobe(canvasRef.current!, {
      devicePixelRatio: 2,
      width: width * 2,
      height: width * 2,
      phi: 0,
      theta: 0.28,
      dark: 1,
      diffuse: 1.2,
      mapSamples: 16000,
      mapBrightness: 6,
      baseColor: [0.29, 0.34, 0.35],
      markerColor: CLUSTER,
      glowColor: [0.69, 0.77, 0.69],
      markers: MARKERS,
      arcs: ARCS,
      arcColor: ARC,
      arcWidth: 0.5,
      arcHeight: 0.4,
    } as Parameters<typeof createGlobe>[1]);

    const render = () => {
      if (!pointerInteracting.current) phi += 0.004;
      globe.update({ phi: phi + r, width: width * 2, height: width * 2 } as Partial<Parameters<typeof createGlobe>[1]>);
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);

    setTimeout(() => { if (canvasRef.current) canvasRef.current.style.opacity = '1'; }, 0);

    return () => {
      cancelAnimationFrame(raf);
      globe.destroy();
      window.removeEventListener('resize', onResize);
    };
  }, [r]);

  return (
    <div className={cn('relative aspect-square w-full max-w-[600px] mx-auto', className)}>
      <canvas
        ref={canvasRef}
        onPointerDown={(e) => {
          pointerInteracting.current = e.clientX - pointerMovement.current;
          if (canvasRef.current) canvasRef.current.style.cursor = 'grabbing';
        }}
        onPointerUp={() => {
          pointerInteracting.current = null;
          if (canvasRef.current) canvasRef.current.style.cursor = 'grab';
        }}
        onPointerOut={() => {
          pointerInteracting.current = null;
          if (canvasRef.current) canvasRef.current.style.cursor = 'grab';
        }}
        onMouseMove={(e) => {
          if (pointerInteracting.current !== null) {
            const delta = e.clientX - pointerInteracting.current;
            pointerMovement.current = delta;
            setR(delta / 200);
          }
        }}
        onTouchMove={(e) => {
          if (pointerInteracting.current !== null && e.touches[0]) {
            const delta = e.touches[0].clientX - pointerInteracting.current;
            pointerMovement.current = delta;
            setR(delta / 100);
          }
        }}
        className="h-full w-full cursor-grab [contain:layout_paint_size] opacity-0 transition-opacity duration-500"
      />
    </div>
  );
}
