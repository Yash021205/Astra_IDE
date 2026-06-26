'use client';
// Aceternity-style GitHub globe — a real three.js ThreeGlobe with hex-polygon
// landmasses, glowing arcs between the ASTRA clusters and connected cities, an
// atmosphere, and slow auto-rotation. Themed in the brand green/blossom palette.

import { useEffect, useRef, useState } from 'react';
import { Canvas, extend, useThree, type Object3DNode } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import ThreeGlobe from 'three-globe';
import { Color, Fog, PointLight, AmbientLight, DirectionalLight } from 'three';

extend({ ThreeGlobe });

// eslint-disable-next-line @typescript-eslint/no-namespace
declare global {
  namespace JSX {
    interface IntrinsicElements {
      threeGlobe: Object3DNode<ThreeGlobe, typeof ThreeGlobe>;
    }
  }
}

const CLUSTERS = {
  a: { lat: 55.5, lng: 9.5 }, b: { lat: 28.6, lng: 77.2 },
  c: { lat: 37.7, lng: -122.4 }, d: { lat: 1.35, lng: 103.8 },
};
const SAGE = '#9CB080', GREEN = '#2B5748', BLOSSOM = '#e08e9b';

const ARCS = [
  { startLat: 19.07, startLng: 72.87, endLat: CLUSTERS.b.lat, endLng: CLUSTERS.b.lng, color: SAGE },
  { startLat: 12.97, startLng: 77.59, endLat: CLUSTERS.b.lat, endLng: CLUSTERS.b.lng, color: SAGE },
  { startLat: 52.52, startLng: 13.40, endLat: CLUSTERS.a.lat, endLng: CLUSTERS.a.lng, color: SAGE },
  { startLat: 51.51, startLng: -0.13, endLat: CLUSTERS.a.lat, endLng: CLUSTERS.a.lng, color: BLOSSOM },
  { startLat: 40.71, startLng: -74.01, endLat: CLUSTERS.c.lat, endLng: CLUSTERS.c.lng, color: SAGE },
  { startLat: 35.68, startLng: 139.69, endLat: CLUSTERS.d.lat, endLng: CLUSTERS.d.lng, color: BLOSSOM },
  { startLat: -33.87, startLng: 151.21, endLat: CLUSTERS.d.lat, endLng: CLUSTERS.d.lng, color: SAGE },
  { startLat: -23.55, startLng: -46.63, endLat: CLUSTERS.c.lat, endLng: CLUSTERS.c.lng, color: BLOSSOM },
  { startLat: 3.14, startLng: 101.69, endLat: CLUSTERS.d.lat, endLng: CLUSTERS.d.lng, color: SAGE },
];

const POINTS = [
  ...Object.values(CLUSTERS).map((c) => ({ lat: c.lat, lng: c.lng, color: SAGE, size: 0.9 })),
  ...[[19.07,72.87],[12.97,77.59],[52.52,13.40],[51.51,-0.13],[40.71,-74.01],[35.68,139.69],[-33.87,151.21],[-23.55,-46.63],[3.14,101.69]]
     .map(([lat, lng]) => ({ lat, lng, color: BLOSSOM, size: 0.5 })),
];

function Globe() {
  const ref = useRef<ThreeGlobe>(null);
  const [countries, setCountries] = useState<any>(null);

  useEffect(() => {
    fetch('/countries.geojson').then((r) => r.json()).then(setCountries).catch(() => setCountries({ features: [] }));
  }, []);

  useEffect(() => {
    const g = ref.current;
    if (!g || !countries) return;
    g.hexPolygonsData(countries.features)
      .hexPolygonResolution(3)
      .hexPolygonMargin(0.62)
      .hexPolygonColor(() => 'rgba(156,196,140,0.85)')
      .showAtmosphere(true)
      .atmosphereColor('#7ec8e3')
      .atmosphereAltitude(0.22);
    const mat: any = g.globeMaterial();
    mat.color = new Color('#1a3040');
    mat.emissive = new Color('#1a3848');
    mat.emissiveIntensity = 0.35;
    mat.shininess = 0.9;

    g.arcsData(ARCS)
      .arcColor((d: any) => d.color)
      .arcAltitude(0.22)
      .arcStroke(0.8)
      .arcDashLength(0.9)
      .arcDashGap(3)
      .arcDashAnimateTime(1800)
      .arcsTransitionDuration(800);

    g.pointsData(POINTS)
      .pointColor((d: any) => d.color)
      .pointAltitude(0.01)
      .pointRadius((d: any) => d.size * 1.4);
  }, [countries]);

  return <threeGlobe ref={ref} />;
}

function Lights() {
  const { scene } = useThree();
  useEffect(() => {
    scene.fog = new Fog(0x1a3040, 400, 2000);
    const amb = new AmbientLight(0xc8dde8, 1.0);
    const dir = new DirectionalLight(0xffffff, 1.2); dir.position.set(-200, 200, 200);
    const p1 = new PointLight(0xe8b0bb, 1.0); p1.position.set(-200, 300, 200);
    const p2 = new PointLight(0x7ec8e3, 0.8); p2.position.set(200, -200, 200);
    scene.add(amb, dir, p1, p2);
    return () => { scene.remove(amb, dir, p1, p2); };
  }, [scene]);
  return null;
}

export default function GithubGlobe({ className }: { className?: string }) {
  return (
    <div className={className} style={{ width: '100%', aspectRatio: '1 / 1', maxWidth: 620, margin: '0 auto' }}>
      <Canvas camera={{ position: [0, 0, 320], fov: 50, near: 180, far: 1800 }}>
        <Lights />
        <Globe />
        <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={0.6}
                       minPolarAngle={Math.PI / 3.5} maxPolarAngle={Math.PI - Math.PI / 3} />
      </Canvas>
    </div>
  );
}
