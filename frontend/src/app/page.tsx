'use client';
import Link from 'next/link';
import Image from 'next/image';
import {
  Brain, Cpu, Eye, Shield, Network, Leaf, Users, Github,
} from 'lucide-react';

import AuroraBackground   from '../components/ui/AuroraBackground';
import Spotlight          from '../components/ui/Spotlight';
import Sparkles           from '../components/ui/Sparkles';
import ThreeDCard         from '../components/ui/ThreeDCard';
import HoverBorderGradient from '../components/ui/HoverBorderGradient';
import CanvasText         from '../components/ui/CanvasText';
import TextHoverEffect    from '../components/ui/TextHoverEffect';
import AnimatedTerminal, { type TerminalLine } from '../components/ui/AnimatedTerminal';
import InteractiveGlobe, { type GlobeMarker, type GlobeArc } from '../components/ui/InteractiveGlobe';
import { BentoGrid, BentoCard } from '../components/ui/BentoGrid';

const DEMO_TERMINAL: TerminalLine[] = [
  { kind: 'comment', text: '# user requests a workspace' },
  { kind: 'cmd', prompt: '$', text: 'POST /api/v1/workspaces  language=bash network=true' },
  { kind: 'out', text: '-> risk scorer evaluating...' },
  { kind: 'ok',  text: 'x language=bash         +0.30' },
  { kind: 'ok',  text: 'x network_access=true   +0.20' },
  { kind: 'ok',  text: 'x filesystem_write=true +0.20' },
  { kind: 'warn', text: '! suspicious "subprocess" in code  +0.10' },
  { kind: 'out', text: '-> final risk = 0.80 -> sandbox = firecracker' },
  { kind: 'cmd', prompt: '$', text: 'kubectl apply -f workspace.yaml  runtimeClassName=firecracker' },
  { kind: 'ok',  text: 'x pod ws-7-a2c3 scheduled on node-eu-2 (lowest carbon)' },
  { kind: 'comment', text: '# eBPF telemetry feeds PPO scheduler state in real-time' },
  { kind: 'cmd', prompt: '$', text: 'tetragon trace --pod ws-7-a2c3' },
  { kind: 'out', text: 'sched_switch  cpu=2  run_q=3   net=124KiB/s' },
];

// Simulated live users + clusters around the world
const GLOBE_MARKERS: GlobeMarker[] = [
  { id: 'cluster-a', label: 'cluster-a (DK)',   lat: 55.5,  lng: 9.5,    kind: 'cluster' },
  { id: 'cluster-b', label: 'cluster-b (IN)',   lat: 28.6,  lng: 77.2,   kind: 'cluster' },
  { id: 'cluster-c', label: 'cluster-c (US)',   lat: 37.7,  lng: -122.4, kind: 'cluster' },
  { id: 'u-mum',  label: 'Mumbai',        lat: 19.07, lng: 72.87, kind: 'user' },
  { id: 'u-bng',  label: 'Bangalore',     lat: 12.97, lng: 77.59, kind: 'user' },
  { id: 'u-blr',  label: 'Berlin',        lat: 52.52, lng: 13.40, kind: 'user' },
  { id: 'u-lon',  label: 'London',        lat: 51.51, lng:  -0.13, kind: 'user' },
  { id: 'u-nyc',  label: 'New York',      lat: 40.71, lng: -74.01, kind: 'user' },
  { id: 'u-tky',  label: 'Tokyo',         lat: 35.68, lng: 139.69, kind: 'user' },
  { id: 'u-syd',  label: 'Sydney',        lat: -33.87, lng: 151.21, kind: 'user' },
  { id: 'u-spo',  label: 'Sao Paulo',     lat: -23.55, lng: -46.63, kind: 'user' },
  { id: 'w-1', label: 'ws-py-runc',    lat: 56.0,  lng: 10.0,  kind: 'workspace' },
  { id: 'w-2', label: 'ws-cpp-gvisor', lat: 28.0,  lng: 78.0,  kind: 'workspace' },
  { id: 'w-3', label: 'ws-sh-fc',      lat: 37.0,  lng: -121.0, kind: 'workspace' },
];

const GLOBE_ARCS: GlobeArc[] = [
  { fromId: 'u-mum',  toId: 'cluster-b', flow: 0.8 },
  { fromId: 'u-bng',  toId: 'cluster-b', flow: 0.7 },
  { fromId: 'u-blr',  toId: 'cluster-a', flow: 0.6 },
  { fromId: 'u-lon',  toId: 'cluster-a', flow: 0.5 },
  { fromId: 'u-nyc',  toId: 'cluster-c', flow: 0.9 },
  { fromId: 'u-tky',  toId: 'cluster-b', flow: 0.4 },
  { fromId: 'u-syd',  toId: 'cluster-c', flow: 0.5 },
  { fromId: 'u-spo',  toId: 'cluster-c', flow: 0.6 },
  { fromId: 'cluster-a', toId: 'cluster-b', flow: 0.3, color: 'rgba(168,85,247,0.5)' },
  { fromId: 'cluster-b', toId: 'cluster-c', flow: 0.3, color: 'rgba(168,85,247,0.5)' },
];

// Team — sorted by roll number ascending
const TEAM = [
  { name: 'Prasanna Mishra',   roll: '2023IMT-059' },
  { name: 'Udit Srivastava',   roll: '2023IMT-084' },
  { name: 'Yash Wani',         roll: '2023IMT-087' },
];

export default function HomePage() {
  return (
    <main className="min-h-screen">
      {/* ─────────── HERO ─────────── */}
      <AuroraBackground className="relative min-h-screen overflow-hidden">
        <Spotlight className="-top-40 left-0 md:left-60 md:-top-20" fill="rgba(168,85,247,0.7)" />
        <Sparkles density={0.4} color="#a5b4fc" />

        {/* Navbar */}
        <nav className="relative z-20 max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/logo.png" alt="ASTRA-IDE" width={36} height={36} className="rounded" />
            <span className="text-xl font-bold tracking-tight">
              ASTRA-<span className="text-astra-500">IDE</span>
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="px-3 py-1.5 text-sm rounded hover:bg-slate-800/70 text-slate-200">
              Log in
            </Link>
            <Link href="/register">
              <HoverBorderGradient containerClassName="text-sm">Sign up</HoverBorderGradient>
            </Link>
          </div>
        </nav>

        {/* Hero content */}
        <section className="relative z-10 max-w-7xl mx-auto px-6 pt-8 pb-24 grid grid-cols-1 lg:grid-cols-5 gap-12 items-center">
          <div className="lg:col-span-3 space-y-7">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-astra-400 mb-3">
                Cloud IDE
              </p>
              <CanvasText
                text="The cloud IDE"
                height={130}
                fontSize={104}
                gradient={['#60a5fa', '#a855f7', '#ec4899']}
              />
              <CanvasText
                text="that schedules itself."
                height={130}
                fontSize={92}
                gradient={['#a855f7', '#ec4899', '#f97316']}
              />
            </div>

            <p className="text-slate-300 text-lg leading-relaxed max-w-2xl">
              <span className="text-astra-400 font-semibold">DRL-PPO</span> scheduling,{' '}
              <span className="text-purple-400 font-semibold">eBPF</span> telemetry,{' '}
              <span className="text-pink-400 font-semibold">adaptive sandboxing</span>,{' '}
              <span className="text-amber-400 font-semibold">LSTM prewarming</span>, multi-cluster
              federation, and conflict-free collaboration — one open research platform.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link href="/register">
                <HoverBorderGradient containerClassName="text-base">
                  Get started — it&apos;s free →
                </HoverBorderGradient>
              </Link>
              <a
                href="https://github.com/PrasannaMishra001/astra-ide"
                className="px-5 py-2.5 rounded-full border border-slate-700 hover:border-slate-500 bg-slate-900/60 text-sm font-medium inline-flex items-center gap-2"
              >
                <Github size={16} /> View on GitHub
              </a>
            </div>

            <div className="pt-6 grid grid-cols-3 gap-6 max-w-xl text-sm">
              <Stat value="< 2s"   label="Cold start (predicted)" />
              <Stat value="78%+"   label="Resource utilization" />
              <Stat value="< 20ms" label="Collab latency" />
            </div>
          </div>

          {/* Logo card with improved 3D tilt */}
          <div className="lg:col-span-2 flex justify-center">
            <ThreeDCard intensity={18} className="w-full max-w-sm">
              <div className="rounded-2xl bg-slate-900/70 backdrop-blur p-8 border border-slate-800 shadow-2xl">
                <div className="relative w-full aspect-square">
                  <Image src="/logo.png" alt="ASTRA-IDE Logo" fill className="object-contain" priority />
                </div>
                <div className="text-center mt-4">
                  <div className="text-xs text-slate-400 font-mono">v0.1 · 2026</div>
                </div>
              </div>
            </ThreeDCard>
          </div>
        </section>
      </AuroraBackground>

      {/* ─────────── INTERACTIVE GLOBE ─────────── */}
      <section className="bg-slate-950 py-24 border-t border-slate-900">
        <div className="max-w-6xl mx-auto px-6">
          <div className="mb-10 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-400 mb-3">Live globe</p>
            <h2 className="text-3xl md:text-4xl font-bold">Workspaces around the world</h2>
            <p className="text-slate-400 mt-4 max-w-2xl mx-auto">
              Every user connects to the nearest cluster. The PPO scheduler watches global state and
              routes workspaces across <span className="text-astra-400">cluster-a (Denmark)</span>,{' '}
              <span className="text-purple-400">cluster-b (India)</span>, and{' '}
              <span className="text-pink-400">cluster-c (US)</span>.
              Drag the globe to rotate it.
            </p>
          </div>
          <InteractiveGlobe markers={GLOBE_MARKERS} arcs={GLOBE_ARCS} height={520} />
        </div>
      </section>

      {/* ─────────── DEMO TERMINAL ─────────── */}
      <section className="bg-slate-950 py-24 border-t border-slate-900">
        <div className="max-w-5xl mx-auto px-6">
          <div className="mb-10 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-400 mb-3">Live demo</p>
            <h2 className="text-3xl md:text-4xl font-bold">Adaptive sandboxing — in real time</h2>
            <p className="text-slate-400 mt-4 max-w-2xl mx-auto">
              When a user submits code, the risk scorer routes it to the right isolation tier:
              <span className="text-emerald-400"> runc </span>(low overhead),
              <span className="text-amber-400"> gVisor </span>(user-space kernel), or
              <span className="text-rose-400"> Firecracker </span>(hardware microVM).
            </p>
          </div>
          <AnimatedTerminal lines={DEMO_TERMINAL} title="astra-ide@scheduler" />
        </div>
      </section>

      {/* ─────────── BENTO GRID ─────────── */}
      <section className="bg-slate-950 py-24 border-t border-slate-900">
        <div className="max-w-7xl mx-auto px-6">
          <div className="mb-12 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-400 mb-3">Seven breakthroughs</p>
            <h2 className="text-3xl md:text-4xl font-bold">Built for research, designed for production</h2>
          </div>

          <BentoGrid>
            <BentoCard accent="astra" span="col-2"
              icon={<Brain size={28} />}
              title="DRL-PPO Scheduler"
              description="40-dim state vector. Multi-discrete action space. Proximal Policy Optimization replaces Kubernetes' default scheduler — learns optimal pod placement from live telemetry."
            />
            <BentoCard accent="cyan"
              icon={<Eye size={28} />}
              title="eBPF Telemetry"
              description="Sub-second kernel-level signals via Tetragon + sched_ext. < 1% overhead."
            />
            <BentoCard accent="rose"
              icon={<Shield size={28} />}
              title="Adaptive Sandboxing"
              description="runc -> gVisor -> Firecracker, auto-selected by real-time risk scoring."
            />
            <BentoCard accent="emerald"
              icon={<Cpu size={28} />}
              title="LSTM Prewarming"
              description="Predicts user sessions 15 min ahead. Cold start eliminated for warm-pool hits."
            />
            <BentoCard accent="amber"
              icon={<Network size={28} />}
              title="Multi-Cluster"
              description="Karmada federation routes load across regions. PPO sees the global state."
            />
            <BentoCard accent="purple"
              icon={<Leaf size={28} />}
              title="Carbon-Aware"
              description="Real-time electricityMaps signal. Batch workloads defer to low-carbon windows."
            />
            <BentoCard accent="cyan" span="col-2"
              icon={<Users size={28} />}
              title="Yjs CRDT Collaboration"
              description="Real-time conflict-free editing inside Monaco. Awareness shows every cursor. < 20ms sync latency over WebSocket."
            />
          </BentoGrid>
        </div>
      </section>

      {/* ─────────── TEXT HOVER + TEAM ─────────── */}
      <section className="bg-slate-950 py-24 border-t border-slate-900">
        <div className="max-w-6xl mx-auto px-6">
          <div className="h-52 md:h-72">
            <TextHoverEffect text="ASTRA-IDE" />
          </div>

          <div className="mt-8">
            <p className="text-xs uppercase tracking-widest text-astra-400 mb-6 text-center">Team</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              {TEAM.map((m) => (
                <ThreeDCard key={m.roll} intensity={10}>
                  <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur text-center">
                    <div className="mx-auto w-14 h-14 rounded-full bg-gradient-to-br from-astra-500 to-purple-600 flex items-center justify-center text-xl font-bold mb-3">
                      {m.name.split(' ').map((w) => w[0]).join('').slice(0, 2)}
                    </div>
                    <div className="font-semibold">{m.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5 font-mono">{m.roll}</div>
                  </div>
                </ThreeDCard>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─────────── CTA ─────────── */}
      <section className="bg-slate-950 py-24 border-t border-slate-900">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Ready to try the future of cloud IDEs?
          </h2>
          <p className="text-slate-400 mb-8 max-w-xl mx-auto">
            Spin up a workspace in seconds. Get a private Monaco editor with collaborative editing,
            real-time risk-tier assignment, and one-click code execution.
          </p>
          <Link href="/register">
            <HoverBorderGradient containerClassName="text-base">
              Create your free account →
            </HoverBorderGradient>
          </Link>
        </div>
      </section>

      <footer className="border-t border-slate-900 px-6 py-6 text-xs text-slate-500 text-center">
        ASTRA-IDE · 2026 · <a href="https://github.com/PrasannaMishra001/astra-ide"
                              className="text-slate-400 hover:text-slate-200">GitHub</a>
      </footer>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="text-2xl font-bold text-astra-400">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
    </div>
  );
}
