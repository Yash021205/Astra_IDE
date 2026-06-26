# ASTRA-IDE — Meeting Guide for Faculty (June 19, 2026)

**Live site:** https://34-14-181-224.sslip.io
**Swagger:** https://34-14-181-224.sslip.io/api/v1/docs
**Team:** Prasanna Mishra (2023IMT-059), Udit Srivastava (2023IMT-084), Yash Wani (2023IMT-087)

---

## Part 1: What is ASTRA-IDE? (the elevator pitch)

ASTRA-IDE is a **cloud IDE** (like Replit/Codespaces) where the **infrastructure manages itself using AI**.

In plain words: you open a browser, write code, and run it. But unlike Replit, our backend is doing 7 research-grade things under the hood:

1. A **reinforcement-learning agent** (DRL-PPO) decides which server runs your code
2. **eBPF probes** inside the Linux kernel watch every syscall in real time
3. An **LSTM neural network** predicts when you'll log in and pre-warms your workspace
4. A **risk scorer** automatically picks the right security jail (runc/gVisor/Firecracker)
5. **Karmada federation** ties 3 geographic clusters into one pool that survives region failures
6. **Carbon-aware scheduling** defers batch jobs to low-carbon electricity windows
7. **CRDT-based collaboration** lets multiple people edit the same file simultaneously (like Google Docs)

Every one of these is implemented, benchmarked against a real dataset, and compared to the numbers in a 2022-2026 research paper.

---

## Part 2: The 7 Breakthroughs Explained Simply

### B1: DRL-PPO Scheduler (the brain)

**What it is:** When you create a workspace, Kubernetes normally uses a simple rule like "pick the server with the most free CPU." We replaced that with a PPO (Proximal Policy Optimization) agent — a type of reinforcement learning — that LEARNS from experience.

**How it works:**
- The agent sees a **40-number snapshot** of the entire cluster: CPU per node, memory per node, how many pods are queued, the risk score of the workspace, the carbon intensity of each region, network latency.
- It outputs an **action**: which node to place the pod on AND which sandbox tier to use.
- After placement, it gets a **reward** based on: was latency low? was the node not overloaded? was security appropriate? was carbon considered?
- Over thousands of episodes, it learns a policy that balances ALL of these simultaneously — something no hand-written rule can do well.

**What paper we followed:** Xu et al. (arXiv:2403.07905, 2024) — "DRL for Kubernetes scheduling." They showed learned > heuristic; we reproduced that direction.

**Our result:** PPO reward 177 vs best heuristic (least-loaded) 84 = **+112% improvement**. Lowest SLA violations (0.57%). Best load balance across nodes.

**Where you see it on the website:** Dashboard → create a workspace → the backend runs the risk scorer + PPO agent → assigns a node + sandbox tier → you see the tier badge (runc/gVisor/Firecracker) in the workspace header. The Benchmarks page shows PPO vs baselines.

**Key design choice:** We added a **security penalty** (−3 reward for under-sandboxing risky code) so the PPO can't game latency by always picking runc. This couples B1 with B4.

---

### B2: eBPF Telemetry (the eyes)

**What it is:** eBPF (extended Berkeley Packet Filter) lets you run tiny safe programs INSIDE the Linux kernel. We use Cilium Tetragon to hook 10 syscalls (execve, openat, connect, sendto, recvfrom, write, read, mmap, mprotect, clone) and stream events out at 500ms resolution.

**How it works:**
- A **TracingPolicy** YAML tells Tetragon which kernel functions to watch
- Events flow into our **aggregator** which builds a feature vector every 500ms: CPU usage, run-queue depth, network bytes, syscall frequency, page faults
- This vector feeds into **two consumers**: the PPO scheduler (B1 state) and the anomaly IDS (B4 intrusion detection)

**What paper we followed:** eHashPipe (sketch-based Top-K per-PID counting). We implemented the multi-stage evict-minimum sketch — reproduces their precision: 100% at small k, 90% at k=20 in bounded memory.

**Our result:** Collected a **171,000-event corpus** from 3 real workloads on the GCP VM. This is our own first-party training data for the IDS.

**Where you see it:** Clusters page shows per-node metrics. Under the hood, the telemetry aggregator feeds the scheduler and the risk scorer.

**Simple analogy for ma'am:** "Think of eBPF as putting a stethoscope on the kernel — we can hear every heartbeat (syscall) of every workspace, without slowing anything down (< 1% overhead)."

---

### B3: LSTM Prewarming (the fortune teller)

**What it is:** Starting a container from scratch takes 5-15 seconds (cold start). If we can PREDICT when a user will log in, we pre-start their workspace before they arrive.

**How it works:**
- We trained a **2-layer LSTM** (Long Short-Term Memory neural network) on the Azure Functions 2019 trace — a real-world serverless dataset with 143 million invocations
- The LSTM looks at the last N invocation timestamps for a function and predicts: how many invocations in the next time window?
- If the prediction says "user is coming soon," we start their workspace into a **warm pool** — so when they click, it's already running

**What paper we followed:** The Transformer-cold-start paper (IEEE) which compared LSTM vs Transformer on Azure traces. We targeted their LSTM baseline rows.

**Our result:**
- Median N-RMSE: **0.085** (paper's LSTM: 0.12-0.18 — **we beat the paper** using a global model trained across 150 functions)
- Cold-start reduction: histogram policy cuts 73.5%, oracle 96.5% (paper reports 50-80%)

**Honest finding:** For very sparse functions (someone who logs in once a week), the LSTM doesn't help much — a simple histogram of "they usually come at 9 AM" works better. Our design: use LSTM forecast for **how many** to prewarm, histogram for **how long** to keep warm.

**Where you see it:** Not directly visible in the UI today (needs a live cluster), but the Benchmarks page shows the cold-start prediction results.

---

### B4: Adaptive Sandboxing (the security guard)

**What it is:** Not all code is equally risky. A simple Python print("hello") doesn't need the same security as a bash script that downloads from the internet. We automatically pick the right isolation level:

| Tier | Technology | When used | Overhead |
|------|-----------|-----------|----------|
| **L1: runc** | Standard Linux container | Low risk (simple code, no network) | ~0% |
| **L2: gVisor** | User-space kernel (intercepts all syscalls) | Medium risk (network, file writes) | ~18% |
| **L3: Firecracker** | Full hardware microVM (separate kernel) | High risk (untrusted deps, shell scripts) | Boot < 125ms |

**How it works:**
1. **Risk Scorer:** looks at: language (+0.3 for bash), network access (+0.2), filesystem write (+0.2), suspicious patterns in code (+0.1), user trust score
2. Risk < 0.3 → runc, 0.3-0.6 → gVisor, > 0.6 → Firecracker
3. **Transactional Executor** (Paper 1, Yan arXiv:2512.12806): before running code, we classify it as SAFE/UNSAFE/UNCERTAIN using policy rules. UNSAFE code is blocked before execution. UNCERTAIN code runs in a snapshot-rollback sandbox.
4. **Anomaly IDS** (Paper 3, Iacovazzi CSR 2022): anonymous-walk graph embeddings of syscall sequences → Random Forest → ensemble of Isolation Forests. Detects anomalous behavior at runtime.

**Our results:**
- Policy gate: recall 0.95 at near-zero false positive rate (after benchmark-driven fixes)
- IDS on our own eBPF corpus: accuracy 0.80, FPR 0.10

**Where you see it:** Create a workspace → risk score computed → tier assigned → shown as a colored badge in the workspace header. Owners can manually override ("pin") to a stricter tier from the dropdown.

**Simple analogy:** "It's like airport security — if you have no bags, you go through the fast lane (runc). If you have liquids, you get the scanner (gVisor). If you're flagged, you get the full pat-down (Firecracker)."

---

### B5: Multi-Cluster Federation (the safety net)

**What it is:** We run 3 Kubernetes clusters in different regions: Denmark (EU), India, US. Karmada ties them into one federated control plane so the scheduler sees ALL clusters as one pool.

**How it works:**
- **Karmada** (CNCF sandbox project) provides PropagationPolicy that distributes workspaces across clusters
- If a cluster goes down (node failure, network partition), the surviving clusters absorb the workloads
- We verified: kill a cluster → **workloads redistribute in ~10 seconds**

**What paper we followed:** arXiv:2512.24914 — AI-driven multi-cluster optimization. We reproduced their 4-metric comparison:
- Utilization: 0.64 → 0.71 (paper: 0.62 → 0.78)
- Load balance: 0.81 → 0.96 (paper: 0.71 → 0.88)
- Stability: 6.8 → 3.8 events/hour (paper: 6.4 → 3.1)

**Where you see it:** The globe on the landing page shows the 3 clusters with arcs connecting users to their nearest cluster. Clusters page shows per-cluster health.

**Is it scalable?** Yes — Karmada is designed for 100+ clusters. Adding a 4th cluster is just `karmadactl join`. The PPO scheduler's state vector would grow by ~5 dimensions per cluster; retraining takes minutes on CPU.

---

### B6: Carbon-Aware Scheduling (the green conscience)

**What it is:** Different regions have different electricity mixes at different times. Denmark at 2 PM might be 80% wind; India at the same time might be 70% coal. For batch jobs (tests, builds), we can WAIT for a greener window.

**How it works:**
- Real-time carbon intensity from the UK Carbon Intensity API (free, no key needed) or electricityMaps (key for per-zone)
- If a job is marked as deferrable, the carbon scheduler checks: "If I wait 2 hours, will the grid be 30% greener?"
- If yes, it defers. The user sees "scheduled for a low-carbon window"

**What paper we followed:** PCAPS (Lechowicz) — up to 32.9% carbon reduction for deferrable workloads.

**Our result:** 12h flexibility → **25.8% reduction**, 24h → **45% reduction** (matches their reported range).

**Where you see it:** Platform page shows carbon integration status. The scheduler considers carbon as one term in the PPO reward function.

---

### B7: CRDT Collaboration (the Google Docs for code)

**What it is:** Two people open the same workspace → both can type at the same time → edits merge automatically with zero conflicts. Exactly like Google Docs but for code.

**How it works:**
- **Yjs** (a JavaScript CRDT library) runs in the browser and on a lightweight Node.js relay server
- Each keystroke is encoded as a CRDT operation (position-based, like Logoot/LSEQ)
- Operations commute — inserting at position 5 and position 10 can happen in any order and produce the same result
- **Awareness protocol** broadcasts each user's cursor position, selection, and name

**What paper we followed:** Eg-walker (Kleppmann, EuroSys 2025). We verified convergence on the authors' OWN editing trace (automerge-paper from josephg/editing-traces).

**Our result:** Correct convergence under reordered operations, < 20ms sync latency.

**Where you see it:** Open a workspace in two browser tabs → both show the other's cursor with their name. The presence bar in the header shows who's viewing which file.

---

## Part 3: System Design Overview

### Architecture (how data flows)

```
User's Browser (Next.js + Monaco + Yjs)
    │
    ├── HTTP/JSON (JWT auth) ──→ FastAPI Backend
    │                               │
    │                               ├── Risk Scorer (computes risk 0-1)
    │                               ├── PPO Scheduler (picks node + tier)
    │                               ├── LSTM Prewarmer (predicts sessions)
    │                               └── Carbon Scheduler (defers batch jobs)
    │
    ├── WebSocket ──→ Yjs Collab Server (CRDT sync)
    │
    └── WebSocket ──→ Terminal (xterm.js ↔ PTY shell)

Backend ──→ Kubernetes API ──→ Karmada ──→ 3 Clusters
                                              │
                                        Tetragon eBPF
                                        (kernel telemetry)
```

### Tech Stack (full list with status)

| Layer | Technology | Status |
|-------|-----------|--------|
| **Frontend** | Next.js 14 (App Router), TailwindCSS, Monaco Editor, Yjs, xterm.js, Framer Motion, cobe (globe) | Live |
| **Backend** | FastAPI, SQLAlchemy, Pydantic v2, JWT, Google OAuth | Live |
| **Database** | PostgreSQL (prod), SQLite (dev) | Live |
| **Cache** | Redis (with in-memory fallback) | Live |
| **Object Store** | MinIO (workspace snapshots) | Live |
| **ML/AI** | PyTorch (LSTM), Stable-Baselines3 (PPO), Gymnasium, scikit-learn (IDS) | Live + Benchmarked |
| **Containers** | Docker, runc, gVisor (runsc), Firecracker (Kata) | Artifacts ready |
| **Orchestration** | Kubernetes (kind clusters on GCP VM) | Verified |
| **Federation** | Karmada v1.18 (3-cluster setup) | Verified (failover proven) |
| **Telemetry** | Cilium Tetragon (eBPF), Prometheus, Grafana | Live on VM |
| **Autoscaling** | KEDA (scales backend on workspace queue depth) | Artifact ready |
| **Infrastructure** | GCP e2-medium VM, Terraform, Caddy (auto-HTTPS), Docker Compose | Live |
| **CI/CD** | GitHub Actions (lint + test + docker build) | Live |
| **Collab** | y-websocket server (LevelDB persistence) | Live |

### How the sandbox tiers map to Kubernetes

```
Risk < 0.3     →  runtimeClassName: runc
                  (just a Linux container, no extra kernel)

0.3 ≤ Risk < 0.6  →  runtimeClassName: runsc  (gVisor)
                      (syscalls go through gVisor's Sentry,
                       a user-space kernel written in Go)

Risk ≥ 0.6     →  runtimeClassName: kata-fc  (Firecracker)
                  (entire microVM boots in < 125ms,
                   separate Linux kernel, hardware isolation)
```

---

## Part 4: Paper-by-Paper Summary (what values we took from where)

| # | Paper | Year | What we took from it | Our result vs theirs |
|---|-------|------|---------------------|---------------------|
| B1 | Xu, arXiv:2403.07905 | 2024 | DRL > heuristic for K8s scheduling, PPO formulation | PPO +112% over best baseline (matches direction) |
| B2 | eHashPipe | 2022 | Multi-stage sketch for per-PID Top-K | Precision 100% small k, 90% k=20 (paper 95%) |
| B3 | Transformer-cold-start (IEEE) | 2024 | LSTM baseline on Azure trace, N-RMSE metric | Our N-RMSE 0.085 < paper 0.12-0.18 |
| B3+ | Springer/Kumari | 2024 | 49.52% cold-start improvement claim | Our histogram: 73.5% (honest: different method) |
| B4-P1 | Yan, arXiv:2512.12806 | 2025 | Transactional execution, SAFE/UNSAFE/UNCERTAIN policy | Table 1 reproduced 100%, recall 0.95 after benchmark |
| B4-P2 | Marchand, arXiv:2603.02277 | 2026 | Difficulty-grounded severity scoring | Ordering reproduced |
| B4-P3 | Iacovazzi & Raza, CSR | 2022 | Anonymous-walk IDS (graph embedding → RF → IF) | FPR matches (0.03/0.057); F1 NOT reproduced (honest) |
| B5 | arXiv:2512.24914 | 2025 | AI multi-cluster optimization, 4-metric comparison | 3/4 metrics match direction, 1 honestly limited |
| B6 | PCAPS (Lechowicz) | 2024 | Carbon-shifting for deferrable workloads | 25.8-45% reduction (matches their range) |
| B7 | Eg-walker (Kleppmann, EuroSys) | 2025 | CRDT convergence, verified on their trace | Correct convergence, < 20ms latency |

**Honest limitations we documented:**
- B4 IDS: paper's F1 on CloudSuite doesn't transfer to other datasets (we got AUC 0.59 multi-class) — windowing made it worse
- B5 latency: 2-cluster sim can't show deep-overload latency + oscillation together
- B3 sparse functions: LSTM loses to histogram for very infrequent users

---

## Part 5: Live Demo Walkthrough (what to show ma'am)

### Step 1: Landing page (30s)
Open https://34-14-181-224.sslip.io. Scroll through:
- The animated terminal showing risk scoring in action
- The 3D globe showing 3 clusters and user connections
- Click any of the 7 feature cards — they expand with "What it does" and "How to use it"

### Step 2: Register + Login (30s)
- Register a new account (or sign in with Google)
- Shows JWT auth + Google OAuth working

### Step 3: Create workspace (1 min)
- Dashboard → New workspace → Python
- Show the **sandbox tier** assigned (Auto mode picks based on risk)
- Show the tier badge in workspace header
- Click the tier dropdown → explain "owners can pin to a stricter tier"

### Step 4: File management (1 min)
- New file → write Python code → auto-save (1.2s debounce, shows "saved" indicator)
- Import a GitHub repo (e.g. `https://github.com/octocat/Hello-World`)
- Folder expand/collapse, search across files

### Step 5: Terminal (30s)
- Toggle terminal button → real bash shell in the container
- Run `ls`, `python --version`, etc.

### Step 6: Collaboration (1 min)
- Open same workspace in 2 browser tabs
- Type in both → see live cursors with names
- Show the presence bar ("2 here, viewing app.py")

### Step 7: Share + Exclude (30s)
- Share button → invite a username → member appears with email/avatar
- "Shared files" tab → uncheck .env → hidden from collaborators

### Step 8: History (30s)
- History button → shows every edit: who, which file, +lines/-lines, when
- "Only the owner can see this — like Google Docs version history"

### Step 9: Preview (30s)
- Create an index.html → Preview tab → shows in sandboxed iframe
- Reload / open in new tab buttons

### Step 10: Settings (30s)
- Settings → Freeze toggle → workspace becomes read-only
- Create config files (.astra/settings.json)
- Delete workspace (danger zone)

### Step 11: Theme + polish (15s)
- Toggle dark/light mode
- Show the tooltip animations on hover

---

## Part 6: Competitors and Our Advantages

### Competitors

| Competitor | What they do | What they DON'T do |
|-----------|-------------|-------------------|
| **Replit** | Browser IDE, multi-language, hosting | No adaptive security, no DRL scheduling, no eBPF |
| **GitHub Codespaces** | VS Code in browser, tied to GitHub | No risk-based sandbox tiers, no carbon awareness |
| **Gitpod** | Cloud dev environments, prebuilds | No ML-based prewarming, no multi-cluster |
| **StackBlitz** | WebContainer-based, runs in browser | No server-side isolation, no collaboration |
| **Google Colab** | Notebooks, GPU | No real-time collab editing, no security tiers |

### Our unique advantages

1. **Adaptive security** — no competitor adjusts container isolation based on code risk in real time
2. **DRL scheduling** — no competitor uses reinforcement learning for pod placement
3. **eBPF telemetry** — kernel-level visibility with < 1% overhead (Replit/Codespaces don't expose this)
4. **Predictive prewarming** — LSTM beats paper baselines; cold start reduced by 73%
5. **Carbon awareness** — no major cloud IDE considers carbon intensity in scheduling
6. **Multi-cluster failover** — proven 10s failover; competitors are single-region
7. **Research-grounded** — every feature cites and reproduces a 2022-2026 paper

### Honest weaknesses vs competitors

1. Replit has a **much larger team** and polished UX (years of iteration)
2. Codespaces has **VS Code parity** (extensions, debugger, devcontainers)
3. We don't have **live container execution** per workspace yet (terminal runs in the backend container, not a per-user pod) — this is the main gap for a production-grade system
4. No **GPU support** (Colab's strength)

---

## Part 7: Scalability Discussion

**Current state:** runs on a single GCP e2-medium VM (2 vCPU, 4 GB RAM) with 3 kind clusters for Karmada demo. This is a **prototype** — the architecture is designed to scale.

**What scales:**
- Backend is stateless (FastAPI) → horizontal scaling behind a load balancer
- PostgreSQL → can move to managed Cloud SQL
- Redis/MinIO → managed services or clustered
- Karmada → designed for 100+ clusters; adding a cluster is one command
- PPO scheduler → trains in minutes on CPU; inference is a single forward pass (~1ms)
- Yjs collab server → multiple instances with shared LevelDB or Redis adapter

**What would need work for 1000+ users:**
- Per-workspace containers (not shared backend container) — needs a real K8s cluster
- WebSocket connection pooling for terminal/collab
- Sharding the PostgreSQL database
- CDN for the Next.js frontend
- Rate limiting and admission control

---

## Part 8: What We Can Add Next (future features)

### Short-term (could do in 2-4 weeks)
1. **Live container execution** — each workspace gets its own pod; terminal connects to it
2. **VS Code extension marketplace** — Monaco supports extensions via OpenVSX
3. **Debugger integration** — DAP (Debug Adapter Protocol) over WebSocket
4. **File upload/download** — drag-and-drop files into the workspace
5. **Workspace templates** — React, Node, Flask pre-built templates
6. **GitHub/GitLab integration** — push/pull from the IDE

### Medium-term (1-2 months)
7. **GPU workspaces** — for ML/data science use cases
8. **AI code assistant** — integrate an LLM for code completion
9. **CI/CD pipelines** — run tests on push, deploy from the IDE
10. **Custom domains** — map your domain to a workspace
11. **Usage analytics dashboard** — track resource consumption per team

### Research extensions
12. **Multi-agent RL** — AGMARL (multiple schedulers coordinating across clusters)
13. **Transformer prewarmer** — replace LSTM with a Transformer for better long-range patterns
14. **Federated learning** — train the scheduler across clusters without sharing raw telemetry
15. **Formal verification** of the CRDT (prove convergence mathematically)
16. **Confidential computing** — use Intel SGX/TDX for workspace memory encryption

---

## Part 9: Cross-Questions Ma'am Might Ask

**Q: How is this different from just using Docker?**
A: Docker gives you containers but no intelligence. We add 7 layers of intelligence ON TOP of Docker/Kubernetes: automated security tiering, ML-based scheduling, predictive prewarming, carbon awareness, etc. Docker is like giving someone a car; we built the self-driving system.

**Q: Does the PPO scheduler actually run in production?**
A: In our prototype, the PPO agent runs as a Python service alongside the backend. It trains on simulated cluster data (using our Gymnasium environment) and makes placement decisions. In a production system, it would run as a Kubernetes scheduler extender (a Go plugin that calls the PPO model). The training and the model are real; the integration path is documented.

**Q: How do you know the eBPF probes don't slow down the system?**
A: eBPF programs run IN the kernel (not as separate processes) and are JIT-compiled to native code. Tetragon (by Cilium, used in production at Google/Meta) reports < 1% CPU overhead. We measured on our VM and confirmed.

**Q: Is the LSTM better than a simple cron job?**
A: For regular users (login at 9 AM daily), a histogram is just as good. The LSTM shines for irregular patterns — someone who codes on weekdays but only evenings, or bursts during exam season. Our honest finding: use LSTM for prediction, histogram for keep-alive timeout.

**Q: Why 3 sandbox tiers? Why not just always use the most secure one?**
A: Firecracker (the most secure) boots a full microVM — it's safe but adds ~125ms boot time and uses more memory. For simple code that doesn't touch the network, that's wasted overhead. Our scoring gives each workspace the MINIMUM security it needs — fast for safe code, locked down for risky code.

**Q: What if a student submits malicious code to break out?**
A: Three defenses: (1) Risk scorer catches dangerous patterns before execution (recall 0.95). (2) The sandbox tier contains execution — Firecracker is hardware-isolated, gVisor has a separate kernel. (3) The IDS watches syscall patterns at runtime and can flag anomalies. No system is 100% secure, but we match industry practice (gVisor is what Google uses for Cloud Run).

**Q: Can this really handle 100 concurrent users?**
A: On the current single VM, practically 10-20 concurrent users. But the architecture scales: FastAPI is async, the database is PostgreSQL (handles thousands of connections), and Kubernetes autoscales pods. Moving to a managed cloud cluster (GKE, EKS) with KEDA autoscaling would handle hundreds.

**Q: Why not just use AWS Lambda / Google Cloud Run?**
A: Those are serverless platforms for running functions. We need persistent workspaces (a user opens an IDE, writes code over hours, comes back tomorrow). Lambda has a 15-minute timeout. We also need the GPU/terminal/filesystem that serverless doesn't provide. But our prewarming approach (B3) is inspired by serverless cold-start research.

**Q: What real datasets did you use?**
A: Azure Functions 2019 trace (143M invocations, Microsoft Research — B3), ADFA-LD (Australian Defence Force — B4 IDS), LID-DS-2021 (Leipzig intrusion detection — B4), NL2Bash + SandboxEscapeBench (B4 policy), UK Carbon Intensity API (B6), automerge-paper editing trace (B7). Plus our own 171k-event Tetragon eBPF corpus from the GCP VM (B4).

**Q: Did you write all the code yourselves?**
A: Yes, all application code. We use open-source libraries (Yjs, Stable-Baselines3, PyTorch, Tetragon, Karmada) as building blocks — the same way any research project uses libraries. The RL environment, reward function, risk scorer, IDS pipeline, federation optimizer, carbon scheduler, and all the benchmarks are our original code. 121 tests across ML and backend.

---

## Part 10: Publication Discussion (for asking ma'am)

### Questions to ask
1. "We have reproducible results on 7 research topics with real datasets. Is this sufficient scope for a publication?"
2. "Should we target a full paper, a short/workshop paper, or a poster?"
3. "Which venue would be most appropriate — systems/cloud conferences or an applied ML venue?"
4. "Should we focus the paper on one breakthrough (e.g., just the DRL scheduler + eBPF) or the integrated system?"

### Potential venues

**Conferences (systems/cloud):**
- **ACM SoCC** (Symposium on Cloud Computing) — premier cloud venue, covers scheduling + containers
- **IEEE CLOUD** — IEEE International Conference on Cloud Computing
- **USENIX ATC** (Annual Technical Conference) — systems, often has cloud scheduling papers
- **MIDDLEWARE** — ACM/IFIP Middleware conference
- **IC2E** (IEEE International Conference on Cloud Engineering)
- **CCGrid** (IEEE/ACM International Symposium on Cluster, Cloud and Grid Computing)

**Conferences (applied ML/systems):**
- **MLSys** — ML + systems intersection (the DRL scheduler fits here)
- **AAAI/IJCAI** (AI conferences) — if framed as applied RL for resource management

**Journals:**
- **IEEE Transactions on Cloud Computing** (TCC) — high impact, 6-12 month review
- **Journal of Systems and Software** (JSS, Elsevier) — good for systems papers
- **Future Generation Computer Systems** (FGCS, Elsevier) — cloud + AI focus
- **Cluster Computing** (Springer) — directly relevant
- **SoftwareX** (Elsevier) — for open-source research software (short, focused on the tool)
- **IEEE Access** — open access, faster review (~2-3 months)

**Workshop papers (easier entry point):**
- **HotCloud** (USENIX) — hot topics in cloud
- **SoCC Posters** — low bar, good visibility
- **NeurIPS Workshop on ML for Systems** — if framing the DRL angle

### Recommendation
A focused paper on "DRL-PPO scheduling with eBPF telemetry and adaptive sandboxing for cloud IDEs" (B1+B2+B4 together) would be the strongest submission — these three are tightly coupled and have the clearest results. B3/B5/B6/B7 can be mentioned as system components. Target **IEEE CLOUD 2027** or **SoCC 2027** (deadlines are usually March-May for fall conferences).

---

## Part 11: Key Terms Glossary (for explaining to ma'am)

| Term | Simple explanation |
|------|-------------------|
| **DRL** | Deep Reinforcement Learning — an AI agent learns by trial and error, like training a dog with treats |
| **PPO** | Proximal Policy Optimization — a specific RL algorithm that learns stably (doesn't change too much per step) |
| **eBPF** | Programs that run safely inside the Linux kernel to observe what's happening — like a security camera |
| **LSTM** | Long Short-Term Memory — a neural network that remembers patterns in time series (good for "when will the user come back?") |
| **CRDT** | Conflict-free Replicated Data Type — a math structure that lets multiple people edit at once and always converge to the same result |
| **gVisor** | Google's user-space kernel — intercepts all syscalls before they reach the real kernel. Used by Google Cloud Run |
| **Firecracker** | Amazon's lightweight VM (powers AWS Lambda). Boots in < 125ms. Hardware isolation |
| **Karmada** | CNCF project for managing multiple Kubernetes clusters as one. Like a federation of countries |
| **Tetragon** | Cilium's eBPF tool for runtime security — watches kernel events in real time |
| **Kubernetes** | Container orchestration platform — manages where containers run, restarts them if they crash |
| **Sandbox** | An isolated environment where untrusted code can run without affecting the host system |
| **Pod** | The smallest deployable unit in Kubernetes — one or more containers that share networking |
| **Cold start** | The delay when a container starts from scratch (downloading image, booting, initializing) |
| **Warm pool** | Pre-started containers waiting for users — eliminates cold start |
| **Carbon intensity** | How many grams of CO2 per kWh of electricity — varies by region and time (wind/solar = low, coal = high) |
| **YAML** | A human-readable configuration format used by Kubernetes |
| **JWT** | JSON Web Token — a signed token for authentication (like a digital ID card) |
| **OAuth** | "Sign in with Google" — delegates authentication to a trusted provider |
| **WebSocket** | A persistent two-way connection between browser and server (for real-time updates) |
| **Monaco** | The code editor used by VS Code — Microsoft open-sourced it |
| **Yjs** | A JavaScript CRDT library for real-time collaboration |
| **State vector** | The 40 numbers the PPO agent sees at each decision point (CPU, memory, risk, carbon, etc.) |
| **Reward function** | The signal that tells the RL agent whether its decision was good or bad |
| **Gymnasium** | OpenAI's standard interface for RL environments (like a game the agent plays) |

---

## Part 12: Demo Troubleshooting

If the VM is stopped: start it from GCP Console (Compute Engine → VM instances → astra-cluster-a → Start). Wait 2 minutes, containers auto-restart.

If the site doesn't load: SSH via `gcloud compute ssh astra-cluster-a --zone asia-south1-a --tunnel-through-iap` and run `cd ~/astra-ide/deploy && PUBLIC_HOST=34.14.181.224 docker compose -f docker-compose.yml -f docker-compose.https.yml up -d`.

If Google OAuth fails: use email/password login instead (register a fresh account).
