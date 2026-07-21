'use client';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { Github } from 'lucide-react';

import Navbar              from '../components/Navbar';
import AuroraBackground    from '../components/ui/AuroraBackground';
import ThreeDCard          from '../components/ui/ThreeDCard';
import HoverBorderGradient from '../components/ui/HoverBorderGradient';
import CanvasText          from '../components/ui/CanvasText';
import TextHoverEffect     from '../components/ui/TextHoverEffect';
import TeamPhoto           from '../components/ui/TeamPhoto';
import AnimatedTerminal, { type TerminalLine } from '../components/ui/AnimatedTerminal';
import LayoutGrid, { type GridCard } from '../components/ui/LayoutGrid';
import ComparisonTable     from '../components/ui/ComparisonTable';
import SchedulerCompare     from '../components/ui/SchedulerCompare';
import NoiseBackground     from '../components/ui/NoiseBackground';
import BigFooter           from '../components/ui/BigFooter';
import CountUp             from '../components/ui/CountUp';
import GoToTop             from '../components/ui/GoToTop';
import { useTheme }        from '../lib/theme';
import { Brain, Cpu, Eye, Shield, Network, Leaf, Users } from 'lucide-react';

const GithubGlobe = dynamic(() => import('../components/ui/GithubGlobe'), { ssr: false });

const DEMO_TERMINAL: TerminalLine[] = [
  { kind: 'cmd', prompt: 'user@iiitm:~$', text: 'POST /api/v1/workspaces  language=bash network=true' },
  { kind: 'out', text: '-> risk scorer evaluating...' },
  { kind: 'ok',  text: 'x language=bash         +0.30' },
  { kind: 'ok',  text: 'x network_access=true   +0.20' },
  { kind: 'ok',  text: 'x filesystem_write=true +0.20' },
  { kind: 'warn', text: '! suspicious "subprocess" in code  +0.10' },
  { kind: 'out', text: '-> final risk = 0.80 -> sandbox = firecracker' },
  { kind: 'cmd', prompt: 'user@iiitm:~$', text: 'kubectl apply -f workspace.yaml' },
  { kind: 'out', text: 'runtimeClassName=firecracker' },
  { kind: 'ok',  text: 'x pod ws-7-a2c3 scheduled on node-eu-2 (lowest carbon)' },
  { kind: 'cmd', prompt: 'user@iiitm:~$', text: 'tetragon trace --pod ws-7-a2c3' },
  { kind: 'out', text: 'sched_switch  cpu=2  run_q=3   net=124KiB/s' },
];

const FEATURE_CARDS: GridCard[] = [
  {
    id: 'ppo', accent: 'astra', span: 'md:col-span-2', icon: <Brain size={28} />,
    title: 'DRL-PPO Scheduler',
    blurb: 'A reinforcement-learning agent decides which machine runs your workspace.',
    what: 'Instead of the default Kubernetes scheduler, ASTRA uses a Proximal Policy Optimization (PPO) agent. It reads a 40-number snapshot of the whole cluster (CPU, memory, queue length, carbon, latency) and learns from experience where to place each workspace so the cluster stays fast and full without overloading any node.',
    how: [
      'Create a workspace — placement is automatic, you do nothing.',
      'Open the Platform page to watch the agent\'s live decisions and reward.',
      'Heavy load? The agent spreads new pods to idle nodes on its own.',
    ],
  },
  {
    id: 'ebpf', accent: 'cyan', icon: <Eye size={28} />,
    title: 'eBPF Telemetry',
    blurb: 'Kernel-level signals collected with under 1% overhead.',
    what: 'Tiny safe programs run inside the Linux kernel (via Tetragon) and report what every workspace actually does — syscalls, CPU scheduling, network bytes — in well under a second. This is the live data the scheduler and the security scorer both feed on.',
    how: [
      'Run any code in a workspace; telemetry starts automatically.',
      'See per-workspace CPU / run-queue / network in the Clusters view.',
      'Suspicious syscalls raise the risk score in real time.',
    ],
  },
  {
    id: 'sandbox', accent: 'rose', icon: <Shield size={28} />,
    title: 'Adaptive Sandboxing',
    blurb: 'Risky code is automatically locked into a stronger jail.',
    what: 'Every workspace gets a risk score from its language, permissions, and code patterns. Low risk runs in fast runc containers; medium risk in gVisor (a user-space kernel); high risk in a Firecracker microVM with its own kernel — so dangerous code can\'t escape.',
    how: [
      'Pick "Auto" when creating a workspace to let the scorer choose.',
      'See the chosen tier (runc / gVisor / Firecracker) in the header.',
      'Owners can pin a stricter tier from the tier menu any time.',
    ],
  },
  {
    id: 'lstm', accent: 'emerald', icon: <Cpu size={28} />,
    title: 'LSTM Prewarming',
    blurb: 'Predicts when you\'ll log in and warms a workspace beforehand.',
    what: 'A small LSTM model learns each user\'s usage rhythm and predicts sessions about 15 minutes ahead. Matching workspaces are pre-started into a warm pool, so when you actually open one the cold-start wait is gone.',
    how: [
      'Just use ASTRA normally for a few days so it learns your pattern.',
      'Return at your usual time — your workspace opens near-instantly.',
      'Warm-pool hits show up on the Benchmarks page.',
    ],
  },
  {
    id: 'multi', accent: 'amber', icon: <Network size={28} />,
    title: 'Multi-Cluster',
    blurb: 'Three regions act as one pool the scheduler sees globally.',
    what: 'Karmada federates cluster-a (Denmark), cluster-b (India) and cluster-c (US). Workspaces are routed to the nearest healthy region, and if a cluster fails its workloads are rescheduled to a survivor in seconds.',
    how: [
      'You connect to the closest region automatically — lowest latency.',
      'Watch live region health on the Clusters page.',
      'If a region goes down, your workspaces fail over on their own.',
    ],
  },
  {
    id: 'carbon', accent: 'purple', icon: <Leaf size={28} />,
    title: 'Carbon-Aware',
    blurb: 'Batch jobs wait for cleaner, lower-carbon electricity.',
    what: 'ASTRA reads each region\'s real-time grid carbon intensity (electricityMaps). Interactive workspaces run immediately, but deferrable batch jobs are scheduled into greener time windows or greener regions to cut emissions.',
    how: [
      'Mark a job as batch/deferrable when you submit it.',
      'ASTRA delays it to a low-carbon window automatically.',
      'See carbon saved per run on the Platform page.',
    ],
  },
  {
    id: 'crdt', accent: 'cyan', span: 'md:col-span-2', icon: <Users size={28} />,
    title: 'Yjs CRDT Collaboration',
    blurb: 'Edit the same file together in real time — like Google Docs for code.',
    what: 'Monaco is wired to a Yjs CRDT so multiple people can type in the same file at once with no merge conflicts. Awareness shows every collaborator\'s cursor and selection, and sync latency stays under 20ms over WebSocket.',
    how: [
      'Open a workspace and click Share to invite teammates by username.',
      'Open the Editor tab — you\'ll see their live cursors and names.',
      'Use the presence bar to see who is viewing which file right now.',
    ],
  },
];

const TEAM = [
  { name: 'Prasanna Mishra',   roll: '2023IMT-059', img: '/team/prasanna.png' },
  { name: 'Udit Srivastava',   roll: '2023IMT-084', img: '/team/udit.png' },
  { name: 'Yash Wani',         roll: '2023IMT-087', img: '/team/yash.png' },
];

export default function HomePage() {
  const [theme] = useTheme();
  // Dot-matrix headline colours: dark greens on the light pastel hero,
  // light sage/pastels on the dark hero.
  const grad1: [string, string, string] = theme === 'dark' ? ['#9CB080', '#cddafd', '#fde2e4'] : ['#273338', '#2B5748', '#618764'];
  const grad2: [string, string, string] = theme === 'dark' ? ['#cddafd', '#9CB080', '#fad2e1'] : ['#2B5748', '#618764', '#9CB080'];

  return (
    <main className="min-h-screen overflow-x-hidden">
      {/* HERO */}
      <AuroraBackground className="relative min-h-screen overflow-hidden">
        <Navbar variant="hero" />

        <section className="relative z-10 max-w-7xl mx-auto px-6 pt-28 pb-16 grid grid-cols-1 lg:grid-cols-5 gap-12 items-center">
          <div className="lg:col-span-3 space-y-7">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-astra-700 dark:text-astra-300 mb-3">
                Cloud IDE
              </p>
              <CanvasText text="The cloud IDE" height={130} fontSize={104} gradient={grad1} />
              <CanvasText text="that schedules itself." height={130} fontSize={92} gradient={grad2} />
            </div>

            <p className="text-muted text-lg leading-relaxed max-w-2xl">
              <span className="text-astra-700 dark:text-astra-300 font-semibold">DRL-PPO</span> scheduling,{' '}
              <span className="text-blossom-600 dark:text-blossom-300 font-semibold">eBPF</span> telemetry,{' '}
              <span className="text-astra-600 dark:text-astra-200 font-semibold">adaptive sandboxing</span>,{' '}
              <span className="text-blossom-500 dark:text-blossom-200 font-semibold">LSTM prewarming</span>, multi-cluster
              federation, and conflict-free collaboration, in one open research platform.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link href="/register">
                <HoverBorderGradient containerClassName="text-base">
                  Get started for free
                </HoverBorderGradient>
              </Link>
              <a
                href="https://github.com/PrasannaMishra001/astra-ide"
                className="px-5 py-2.5 rounded-full border border-edge-strong hover:bg-raised bg-surface/60 backdrop-blur text-ink text-sm font-medium inline-flex items-center gap-2 transition-colors"
              >
                <Github size={16} /> View on GitHub
              </a>
            </div>

            <div className="pt-6 grid grid-cols-3 gap-6 max-w-xl text-sm">
              <Stat prefix="< " value={2}  suffix="s"  label="Cold start (predicted)" />
              <Stat value={78} suffix="%+" label="Resource utilization" />
              <Stat prefix="< " value={20} suffix="ms" label="Collab latency" />
            </div>
          </div>

          <div className="lg:col-span-2 flex justify-center">
            <AnimatedTerminal lines={DEMO_TERMINAL} title="astra-ide@cloud"
                              speedMul={2} bodyHeight={400} className="w-full max-w-xl" />
          </div>
        </section>
      </AuroraBackground>

      {/* GLOBE - text left, globe right (partially clipped) */}
      <section className="relative bg-bg py-14 border-t border-edge overflow-hidden">
        <SectionBlobs a="#6366f1" b="#38bdf8" c="#22d3ee" />
        <div className="relative max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
            <div className="space-y-6">
              <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400">Live globe</p>
              <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight t-liquid leading-tight">
                Workspaces around the world
              </h2>
              <p className="text-muted leading-relaxed max-w-lg">
                Every user connects to the nearest cluster. The PPO scheduler watches global state and
                routes workspaces across four federated regions:{' '}
                <span className="text-astra-600 dark:text-astra-300 font-medium">Denmark</span>,{' '}
                <span className="text-blossom-500 dark:text-blossom-300 font-medium">India</span>,{' '}
                <span className="text-astra-500 dark:text-astra-400 font-medium">California</span> and{' '}
                <span className="text-blossom-400 dark:text-blossom-200 font-medium">Singapore</span>.
                Drag the globe to rotate it.
              </p>
              <div className="grid grid-cols-3 gap-4 pt-2">
                <MiniStat label="Clusters" value="4" />
                <MiniStat label="Regions" value="EU / IN / US / SG" />
                <MiniStat label="Failover" value="< 10s" />
              </div>
            </div>
            <div className="relative lg:-mr-24 xl:-mr-32">
              <GithubGlobe />
              <div className="flex items-center justify-center gap-5 mt-2 text-[11px] text-faint">
                <Legend color="#e08e9b" label="User cities" />
                <Legend color="#9CB080" label="Clusters" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* DEMO TERMINAL */}
      <section className="relative bg-bg py-14 border-t border-edge overflow-hidden">
        <SectionBlobs a="#2dd4bf" b="#f472b6" c="#818cf8" />
        <div className="relative max-w-5xl mx-auto px-6">
          <div className="mb-10 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400 mb-3">Live demo</p>
            <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight t-liquid">Adaptive sandboxing, in real time</h2>
            <p className="text-muted mt-4 max-w-2xl mx-auto">
              When a user submits code, the risk scorer routes it to the right isolation tier:
              <span className="text-emerald-600 dark:text-emerald-400"> runc </span>(low overhead),
              <span className="text-amber-600 dark:text-amber-400"> gVisor </span>(user-space kernel), or
              <span className="text-rose-600 dark:text-rose-400"> Firecracker </span>(hardware microVM).
            </p>
          </div>
          <AnimatedTerminal lines={DEMO_TERMINAL} title="astra-ide@scheduler" />
        </div>
      </section>

      {/* FEATURE LAYOUT GRID (click a card to expand + learn) */}
      <section className="relative bg-bg py-14 border-t border-edge overflow-hidden">
        <SectionBlobs a="#818cf8" b="#38bdf8" c="#f472b6" />
        <div className="relative max-w-7xl mx-auto px-6">
          <div className="mb-12 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400 mb-3">Seven breakthroughs</p>
            <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight t-liquid">Built for research, designed for production</h2>
            <p className="text-muted mt-4 max-w-xl mx-auto">
              Click any card to see what it does in plain language and how to use it.
            </p>
          </div>

          <LayoutGrid cards={FEATURE_CARDS} />
        </div>
      </section>

      {/* SCHEDULER ALGORITHMS + BENCHMARK */}
      <section className="relative bg-bg py-16 border-t border-edge overflow-hidden">
        <SectionBlobs />
        <div className="relative max-w-6xl mx-auto px-6">
          <div className="mb-10">
            <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400 mb-3">Scheduling</p>
            <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight text-ink">
              Eight schedulers, one honest benchmark
            </h2>
            <p className="text-muted mt-4 max-w-2xl">
              Placement is a choice, not a black box. Compare deep-RL against the classical
              heuristics on real workloads and pick what fits.
            </p>
          </div>
          <SchedulerCompare />
        </div>
      </section>

      {/* COMPETITOR COMPARISON */}
      <section className="relative bg-bg py-16 border-t border-edge overflow-hidden">
        <SectionBlobs />
        <div className="relative max-w-6xl mx-auto px-6">
          <div className="mb-10 text-center">
            <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400 mb-3">How it compares</p>
            <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight text-ink">
              A research control plane the others don't have
            </h2>
            <p className="text-muted mt-4 max-w-2xl mx-auto">
              Mainstream cloud IDEs fix their scheduling, isolation and placement. ASTRA-IDE
              makes each an adaptive, measured decision.
            </p>
          </div>
          <ComparisonTable />
        </div>
      </section>

      {/* TEXT HOVER + TEAM */}
      <section className="relative bg-bg py-14 border-t border-edge overflow-hidden">
        <SectionBlobs a="#f472b6" b="#818cf8" c="#38bdf8" />
        <div className="relative max-w-6xl mx-auto px-6">
          <div className="h-52 md:h-72">
            <TextHoverEffect text="ASTRA-IDE" />
          </div>

          <div className="mt-8">
            <p className="text-xs uppercase tracking-widest text-astra-600 dark:text-astra-400 mb-6 text-center">Team</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              {TEAM.map((m, i) => (
                <ThreeDCard key={m.roll} intensity={10}>
                  <div className="p-5 card neon-hover text-center"
                       style={{ ['--neon' as any]: ['168 85 247', '34 211 238', '244 114 182'][i % 3] }}>
                    <TeamPhoto src={m.img} alt={m.name} size={96} />
                    <div className="font-semibold mt-3">{m.name}</div>
                    <div className="text-xs text-faint mt-0.5 font-mono">{m.roll}</div>
                  </div>
                </ThreeDCard>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA with animated noise background */}
      <section className="border-t border-edge bg-bg py-14">
        <div className="max-w-5xl mx-auto px-6">
          <NoiseBackground className="px-8 py-16 sm:px-16 text-center">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
              Ready to try the future of cloud IDEs?
            </h2>
            <p className="text-white/80 mb-8 max-w-xl mx-auto">
              Spin up a workspace in seconds. Get a private Monaco editor with collaborative editing,
              real-time risk-tier assignment, and one-click code execution.
            </p>
            <Link href="/register"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-white text-slate-900
                             font-semibold text-base shadow-lg hover:scale-[1.03] transition-transform">
              Create your free account
            </Link>
          </NoiseBackground>
        </div>
      </section>

      <BigFooter />
      <GoToTop />
    </main>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
      {label}
    </span>
  );
}

// Minimal, Vercel-style faint dot grid that fades toward the edges — replaces the
// old colour blobs. Keeps sections clean and white in light mode; the colour now
// lives on the cards and hover states instead. (Props kept for call-site compat.)
function SectionBlobs(_props: { a?: string; b?: string; c?: string }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0"
         style={{
           backgroundImage: 'radial-gradient(circle, rgba(148,163,184,0.13) 1px, transparent 1px)',
           backgroundSize: '22px 22px',
           maskImage: 'radial-gradient(ellipse 70% 60% at 50% 35%, black, transparent 82%)',
           WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 50% 35%, black, transparent 82%)',
         }} />
  );
}

function Stat({ value, label, prefix = '', suffix = '' }:
  { value: number; label: string; prefix?: string; suffix?: string }) {
  return (
    <div>
      <CountUp value={value} prefix={prefix} suffix={suffix}
               className="text-2xl font-bold text-astra-700 dark:text-astra-300" />
      <div className="text-xs text-faint mt-1">{label}</div>
    </div>
  );
}

function MiniStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <div className="text-lg font-bold text-ink">{value}</div>
      <div className="text-[11px] text-faint">{label}</div>
    </div>
  );
}
