// Single source of truth for the seven research contributions: the real result
// from our committed benchmark artifacts (ml/*/artifacts/metrics.json), the paper
// each one implements, and the official dataset used. Rendered on /sources and in
// the benchmark results cards, so the numbers stay consistent and honest.

export interface ResearchItem {
  id: string;                 // B1..B7
  name: string;               // product-facing capability
  summary: string;            // one line, plain language
  result: string;             // headline number (real)
  resultSub: string;          // what the number means
  method: string;             // the technique
  paper: string;              // paper title (implemented)
  paperVenue: string;         // venue / authors
  paperUrl?: string;          // official link when known
  dataset: string;            // dataset name
  datasetUrl?: string;        // official dataset link
  tone: 'astra' | 'emerald' | 'rose' | 'purple' | 'amber' | 'sky';
}

export const RESEARCH: ResearchItem[] = [
  {
    id: 'B1',
    name: 'Learned workload scheduling',
    summary: 'A deep reinforcement learning agent places each workspace across heterogeneous nodes.',
    result: 'real trace',
    resultSub: 'PPO policy trained on the Google trace; outperforms random workspace placement',
    method: 'PF-MPPO (multi-agent PPO over top-K task and VM pairs)',
    paper: 'PF-MPPO: task-dependent workflow scheduling via deep reinforcement learning in dynamic heterogeneous cloud environments',
    paperVenue: 'Future Generation Computer Systems (Elsevier)',
    paperUrl: 'https://www.sciencedirect.com/science/article/pii/S0167739X25005308',
    dataset: 'Google Cluster Trace 2011 (clusterdata-2011-2)',
    datasetUrl: 'https://github.com/google/cluster-data',
    tone: 'astra',
  },
  {
    id: 'B2',
    name: 'eBPF telemetry',
    summary: 'Per-workspace syscall and resource capture in the kernel with near-zero overhead.',
    result: 'Top-K sketch',
    resultSub: 'HashPipe heavy-hitter detection, O(d*m) memory regardless of process count',
    method: 'Tetragon (eBPF) capture plus a HashPipe streaming sketch',
    paper: 'HashPipe: heavy-hitter detection entirely in the data plane',
    paperVenue: 'Sivaraman et al., SIGCOMM 2017',
    paperUrl: 'https://dl.acm.org/doi/10.1145/3050220.3063772',
    dataset: 'First-party Tetragon syscall corpus',
    datasetUrl: 'https://tetragon.io',
    tone: 'sky',
  },
  {
    id: 'B3',
    name: 'Predictive pre-warming',
    summary: 'An LSTM forecasts session demand and adapts container keep-alive to cut cold starts.',
    result: '49%',
    resultSub: 'cold-start reduction vs a fixed 10-minute keep-alive window (N-RMSE 0.17)',
    method: 'Univariate LSTM forecaster plus an adaptive keep-alive policy',
    paper: 'Serverless in the Wild: characterizing and optimizing the serverless workload',
    paperVenue: 'Shahrad et al., USENIX ATC 2020',
    paperUrl: 'https://www.usenix.org/conference/atc20/presentation/shahrad',
    dataset: 'Azure Functions Trace 2019',
    datasetUrl: 'https://github.com/Azure/AzurePublicDataset',
    tone: 'purple',
  },
  {
    id: 'B4',
    name: 'Adaptive sandboxing and intrusion detection',
    summary: 'A risk model picks the cheapest safe isolation tier; a graph model flags exploits.',
    result: 'F1 0.82',
    resultSub: 'on LID-DS CVE traces, above STIDE (0.75) and a frequency baseline (0.73)',
    method: 'Risk-scored runc/gVisor/Firecracker tiers plus a multi-scale syscall-graph IDS',
    paper: 'A graph deep-learning intrusion detection system for containers',
    paperVenue: 'Iacovazzi and Raza, IEEE CSR 2022',
    dataset: 'LID-DS 2021 and ADFA-LD',
    datasetUrl: 'https://github.com/LID-DS/LID-DS',
    tone: 'rose',
  },
  {
    id: 'B5',
    name: 'Multi-cluster federation',
    summary: 'Karmada spreads workspaces across clusters with automatic failover.',
    result: 'live failover',
    resultSub: 'workspace pods reschedule when a member cluster is taken down',
    method: 'Karmada propagation and override policies plus a demand-aware optimizer',
    paper: 'AI-driven cloud resource optimization for multi-cluster environments',
    paperVenue: 'Punniyamoorthy et al., 2025',
    dataset: 'Karmada multi-cluster (kind)',
    datasetUrl: 'https://karmada.io',
    tone: 'amber',
  },
  {
    id: 'B6',
    name: 'Carbon-aware scheduling',
    summary: 'Placement and deferrable work follow live grid carbon intensity.',
    result: '30%',
    resultSub: 'CO2 reduction at a 24-step deferral budget on real UK grid data',
    method: 'PCAPS-style temporal shifting plus a carbon term in the scheduler',
    paper: 'Carbon- and Precedence-Aware Scheduling for data processing clusters (PCAPS)',
    paperVenue: 'Lechowicz et al.',
    dataset: 'UK Carbon Intensity API (live gCO2/kWh)',
    datasetUrl: 'https://carbonintensity.org.uk',
    tone: 'emerald',
  },
  {
    id: 'B7',
    name: 'Real-time collaboration',
    summary: 'Multiple users edit the same file with conflict-free CRDT synchronization.',
    result: 'converges',
    resultSub: 'order-independent merge verified on a real keystroke trace',
    method: 'Yjs CRDT bound to Monaco over a WebSocket relay',
    paper: 'Collaborative Text Editing with Eg-walker: better, faster, smaller',
    paperVenue: 'Kleppmann et al., EuroSys 2025',
    dataset: 'Yjs and the automerge editing trace',
    datasetUrl: 'https://github.com/yjs/yjs',
    tone: 'sky',
  },
];
