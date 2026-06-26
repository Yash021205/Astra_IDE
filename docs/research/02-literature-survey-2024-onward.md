# Literature Survey (2024 onward) — per Breakthrough

> Curated, **abstract-verified** recent papers for each of ASTRA-IDE's seven
> breakthroughs. Each entry states what the paper actually shows and how it maps
> to our system: **[baseline]** (compare against), **[method]** (technique we
> adopt/adapt), **[improvement]** (a direction to upgrade our current code), or
> **[validation]** (evidence our design choice is sound).
>
> Verification legend:
> - ✅ abstract read in full and confirmed relevant
> - 🔎 abstract surfaced via database search snippet (read the full PDF on the
>   IEEE/Elsevier/Springer LAN to cite formally)
>
> Honest note on access: IEEE Xplore / ScienceDirect full text needs your campus
> login (their servers block automated fetch). Abstracts below are public; pull
> the PDFs yourself for the final reference list.

---

## B1 — DRL-PPO Kubernetes Scheduler

1. ✅ **Zhou, H., Chan, H.Y., Zhang, S.Y., Lin, M., Ni, J.** *A Kubernetes custom
   scheduler based on reinforcement learning for compute-intensive pods.*
   arXiv:2601.13579 (Jan 2026).
   - **What:** Two DQN-based schedulers (SDQN, SDQN-n) as real K8s custom
     schedulers. Reduce average per-node CPU utilization by **10%** (SDQN) and
     **>20%** (SDQN-n) vs the default scheduler, and **beat LSTM- and
     Transformer-based alternatives**.
   - **Maps to ASTRA:** **[baseline]** — the strongest recent default-scheduler
     comparison; cite when we report PPO vs kube-scheduler. Also justifies a
     consolidation (bin-packing) objective for energy.
   - https://arxiv.org/abs/2601.13579

2. 🔎 **PF-MPPO: Task-dependent workflow scheduling method based on deep
   reinforcement learning in dynamic heterogeneous cloud environments.**
   *Future Generation Computer Systems* (Elsevier), 2025.
   - **What:** Pre-training + fine-tuning **multi-agent PPO**; models workflows
     as DAGs; optimizes latency, energy, and load balancing in heterogeneous
     dynamic clouds.
   - **Maps to ASTRA:** **[method]** — closest published use of *PPO* (our exact
     algorithm) for cloud scheduling; the pre-train/fine-tune split is directly
     applicable to our offline→online training plan.
   - https://www.sciencedirect.com/science/article/abs/pii/S0167739X25005308

3. ✅ **Hamzeh, H.** *AGMARL-DKS: An Adaptive Graph-Enhanced Multi-Agent
   Reinforcement Learning for Dynamic Kubernetes Scheduling.* arXiv:2603.12031
   (2026).
   - **What:** Each node is an agent; a **GNN** builds a global cluster-state
     representation; a stress-aware lexicographic policy replaces static linear
     reward combos. Evaluated on **GKE**; beats default scheduler on fault
     tolerance, utilization, and cost for batch + mission-critical workloads.
   - **Maps to ASTRA:** **[improvement]** — a GNN state encoder is a concrete
     upgrade over our flat 40-dim state vector; the lexicographic-ordering idea
     is an alternative to our weighted reward.
   - https://arxiv.org/abs/2603.12031

4. 🔎 **Xu, Z., Gong, Y., et al.** *Enhancing Kubernetes Automated Scheduling
   with Deep Learning and Reinforcement Techniques for Large-Scale Cloud
   Computing Optimization.* arXiv:2403.07905 (Feb 2024).
   - **Maps to ASTRA:** **[method]** — the two-stage DL+RL scheduler our design
     was originally inspired by; still a valid recent anchor.
   - https://arxiv.org/abs/2403.07905

---

## B2 — eBPF Telemetry → Scheduler Feedback

1. ✅ **Dai, Y., Guo, Q., Wang, X., et al.** *eHashPipe: Lightweight Top-K and
   Per-PID Resource Monitoring with eBPF.* arXiv:2509.09879 (2025).
   - **What:** In-kernel eBPF + HashPipe sketching for per-PID CPU/memory;
     exposes short-lived bursts at **~14× finer temporal resolution than `top`**
     with very low overhead; no user-space polling.
   - **Maps to ASTRA:** **[method]** — exactly the per-process, sub-second
     telemetry our scheduler needs as state input; cite for the 500 ms feedback
     window. (It observes but doesn't close the loop — our scheduler-feedback
     coupling is the novel part.)
   - https://arxiv.org/abs/2509.09879

2. 🔎 **eBPF-Based Instrumentation for Generalisable Diagnosis of Performance
   Degradation.** arXiv:2505.13160 (2025).
   - **What:** 16 eBPF instrumentation metrics; quantifies that overhead depends
     on probe frequency + per-app kernel use (Cassandra/Kafka minimal; Redis/
     MySQL higher).
   - **Maps to ASTRA:** **[validation]** — gives defensible overhead figures for
     our "<1% telemetry overhead" claim and which probes to keep cheap.
   - https://arxiv.org/abs/2505.13160

3. 🔎 **FedMon: Federated eBPF Monitoring for Distributed Systems.**
   arXiv:2510.10126 (2025).
   - **Maps to ASTRA:** **[method]** — federated eBPF telemetry across nodes maps
     directly onto our multi-cluster telemetry aggregation (B5 overlap).
   - https://arxiv.org/abs/2510.10126

4. 🔎 **AgentSight: System-Level Observability for AI Agents Using eBPF.**
   arXiv:2508.02736 (2025). **< 3% overhead**, framework-agnostic.
   - **Maps to ASTRA:** **[validation]** — recent confirmation eBPF observability
     stays under a few % overhead even for opaque workloads.
   - https://arxiv.org/abs/2508.02736

> Note: peer-reviewed *academic* work coupling eBPF telemetry to a live scheduler
> feedback loop is scarce — most eBPF-scheduling work is industry (USENIX SREcon
> '24 Hodges; Linux `sched_ext` in 6.12). That scarcity is itself evidence the
> ASTRA telemetry→PPO loop is novel.

---

## B3 — LSTM / Predictive Prewarming

1. 🔎 **Hu, et al.** *Mitigating cold start problem in serverless computing using
   predictive pre-warming with machine learning.* *Computing* (Springer), 2025.
   DOI 10.1007/s00607-024-01382-y.
   - **What:** RNN predictor over workload history + a pre-warming scheduler that
     dynamically adjusts idle-container lifetimes. The journal version of the
     paradigm our LSTM prewarmer implements.
   - **Maps to ASTRA:** **[method]** — the canonical citation for our prewarming
     design.
   - https://link.springer.com/article/10.1007/s00607-024-01382-y

2. ✅ **Mouen, A.S.F.M., Zeutouo, J.L., Tchendji, V.K.** *Transformer-Based Model
   for Cold Start Mitigation in FaaS Architecture.* arXiv:2504.11338 (2025).
   - **What:** Transformer for cold-start prediction on the public **Azure**
     trace; reports up to **79% reduction** in cold-start times vs conventional
     methods.
   - **Maps to ASTRA:** **[improvement]** — the concrete LSTM→Transformer upgrade
     path for Udit's prewarmer; also gives us the Azure Functions trace as a real
     dataset instead of purely synthetic.
   - https://arxiv.org/abs/2504.11338

3. 🔎 **Taming Cold Starts: Proactive Serverless Scheduling with Model Predictive
   Control.** arXiv:2508.07640 (2025). Up to **85% lower tail latency**, **34%
   less resource** usage.
   - **Maps to ASTRA:** **[baseline]** — an MPC alternative to our ML predictor;
     good comparison point and tail-latency target.
   - https://arxiv.org/abs/2508.07640

4. 🔎 **LSTM-NB: LSTM-predicted negative-binomial prewarming.** ICA3PP 2023
   (proceedings 2024). **20.1%** average cold-start-rate reduction.
   - **Maps to ASTRA:** **[baseline]** — a directly comparable LSTM prewarming
     result to benchmark our F1/cold-start numbers against.

---

## B4 — Adaptive 3-Tier Sandboxing
(See also `01-adaptive-sandboxing.md` for the overhead + escape-vector basis.)

1. **Agache, A., Brooker, M., et al.** *Firecracker: Lightweight Virtualization
   for Serverless Applications.* USENIX **NSDI 2020**.
   - **[validation]** canonical microVM numbers: boot <125 ms, ≤5 MiB mem, >95%
     bare-metal CPU, 150 µVMs/s. https://www.usenix.org/conference/nsdi20/presentation/agache

2. *Performance and isolation analysis of RunC, gVisor and Kata Containers
   runtimes.* **Cluster Computing (Springer), 2022.** DOI 10.1007/s10586-021-03517-8.
   - **[validation]** peer-reviewed overhead ordering used for our tier thresholds.

3. ✅ **Fault-Tolerant Sandboxing for AI Coding Agents: A Transactional Approach
   to Safe Autonomous Execution.** arXiv:2512.12806 (2025).
   - **What:** **100%** interception of high-risk commands, 100% rollback of
     failed states, **14.5%** (~1.8 s) overhead per transaction.
   - **Maps to ASTRA:** **[method/validation]** — most on-point recent paper: it
     sandboxes *coding-agent-generated code*, exactly our threat model; supports
     risk-gated interception of dangerous operations.
   - https://arxiv.org/abs/2512.12806

4. 🔎 **Quantifying Frontier LLM Capabilities for Container Sandbox Escape.**
   arXiv:2603.02277 (2026). Taxonomy of escape mechanisms (misconfig, privilege,
   kernel, runtime) — grounds our escape-vector signature list.
   https://arxiv.org/abs/2603.02277

5. 🔎 **Ensemble of Random and Isolation Forests for Graph-Based Intrusion
   Detection in Containers.** arXiv:2306.14750 (2023).
   - **[improvement]** the ML path to replace our static syscall signature scan.
   - https://arxiv.org/abs/2306.14750

---

## B5 — Multi-Cluster Federation with Global AI Awareness

1. 🔎 **AI-Driven Cloud Resource Optimization for Multi-Cluster Environments.**
   arXiv:2512.24914 (Dec 2025). 4-layer ML framework: **+25% utilization**,
   latency **245 ms → 185 ms**.
   - **[baseline]** the headline multi-cluster improvement we benchmark against.
   - https://arxiv.org/abs/2512.24914

2. 🔎 **Task Scheduling in Geo-Distributed Computing: A Survey.** arXiv:2501.15504
   (Jan 2025).
   - **[method]** taxonomy + related work for the multi-cluster section; covers
     network-aware placement (Ge-kube model-based RL).
   - https://arxiv.org/abs/2501.15504

3. ✅ **AGMARL-DKS** (also B1, arXiv:2603.12031) — MARL across nodes generalizes
   to cross-cluster agents.

4. 🔎 **DCcluster-Opt: Benchmarking Dynamic Multi-Objective Optimization for
   Geo-Distributed Data Center Workloads.** arXiv:2511.00117 (2025).
   - **[baseline]** a benchmark suite for geo-distributed multi-objective
     scheduling — useful to standardize our evaluation.
   - https://arxiv.org/abs/2511.00117

---

## B6 — Carbon / Energy-Aware Scheduling

1. ✅ **Yang, J., Saad, Z., Wu, J., Niu, X., Leung, H., Drew, S.** *A Survey on
   Task Scheduling in Carbon-Aware Container Orchestration.* arXiv:2508.05949
   (Aug 2025).
   - **What:** systematic review of **Kubernetes** scheduling for sustainability;
     hardware- vs software-centric taxonomy by algorithm + sustainability
     objective.
   - **Maps to ASTRA:** **[method]** — the definitive related-work citation for
     our carbon dimension; situates our PPO-reward carbon term in the taxonomy.
   - https://arxiv.org/abs/2508.05949

2. 🔎 **Towards Carbon-Aware Container Orchestration: Predicting Workload Energy
   Consumption with Federated Learning.** arXiv:2510.03970 (2025).
   - **[improvement]** federated XGBoost energy prediction — a privacy-preserving
     way to estimate per-workload energy for our reward (vs our current proxy).
   - https://arxiv.org/abs/2510.03970

3. 🔎 **Carbon- and Precedence-Aware Scheduling for Data Processing Clusters.**
   arXiv:2502.09717 (2025).
   - **[method]** handles DAG precedence + carbon jointly — relevant if we add
     batch build/test pipelines.
   - https://arxiv.org/abs/2502.09717

4. 🔎 **Carbon-Aware Computing for Data Centers with Probabilistic Performance
   Guarantees.** arXiv:2410.21510 (2024).
   - **[validation]** formal guarantees while deferring to low-carbon windows —
     supports our batch-deferral policy. Industry refs: CarbonScaler reports up
     to **51%** emission reduction with K8s autoscaling + real-time carbon.
   - https://arxiv.org/abs/2410.21510

---

## B7 — CRDT Collaboration (+ LSP-aware sync)

1. ✅ **Gentle, J., Kleppmann, M.** *Collaborative Text Editing with Eg-walker:
   Better, Faster, Smaller.* **EuroSys 2025** (arXiv:2409.14252, Sep 2024).
   - **What:** Eg-walker hybridizes CRDT + OT strengths: **an order of magnitude
     less memory** in steady state than CRDTs like Yjs, **orders-of-magnitude
     faster** document load, and far faster long-branch merges than OT, while
     keeping worst-case merge comparable to CRDTs. Works peer-to-peer.
   - **Maps to ASTRA:** **[improvement]** — the most credible 2024/25 result that
     could replace/augment Yjs for lower memory at scale (Kleppmann is the
     Automerge author; EuroSys is top-tier). Cite as the state of the art our Yjs
     choice is measured against.
   - https://arxiv.org/abs/2409.14252

> Note: real-time **LSP-over-CRDT** integration is essentially unpublished in
> academia (LSP is an industry protocol; collaboration + LSP de-duplication is an
> engineering problem). This supports the BTP's "LSP+CRDT integration gap" claim —
> cite Eg-walker for the CRDT half and the official LSP spec for the protocol half.

---

## How to use this in the paper

- **Related Work:** group by the seven breakthroughs above; lead each with the
  survey (B6 §1, B5 §2) then the specific methods.
- **Baselines to implement & beat:** SDQN/SDQN-n (B1), MPC cold-start (B3),
  AI multi-cluster +25%/185ms (B5).
- **Improvement directions (future work / stretch):** GNN state encoder
  (AGMARL-DKS), Transformer prewarmer (B3 §2), ML escape detection (B4 §5),
  Eg-walker collaboration (B7), federated energy prediction (B6 §2).
- Pull full PDFs for the ✅/🔎 items on the campus network and convert these into
  formal IEEE-style citations for the bibliography.
