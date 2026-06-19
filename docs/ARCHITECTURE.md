# Architecture

## System overview

```
┌──────────────────────┐     ┌──────────────────────┐
│  Browser (Next.js)   │◄───►│ y-websocket Collab   │  <— Yjs CRDT sync + awareness
│  Monaco + Yjs        │     │ Server               │
└──────────┬───────────┘     └──────────────────────┘
           │
           │ HTTP/JSON  (JWT auth)
           ▼
┌──────────────────────┐     ┌──────────────────────┐
│  Backend (FastAPI)   │◄───►│  PPO Scheduler       │
│  - Auth              │ gRPC│  - Gymnasium env     │
│  - Workspace CRUD    │     │  - eBPF telemetry    │
│  - Risk scorer       │     │  - Reward function   │
└──────────┬───────────┘     └──────────────────────┘
           │
           │ Kubernetes API
           ▼
┌──────────────────────┐     ┌──────────────────────┐
│  Karmada (multi-     │────►│  Workspace Pods      │
│  cluster control)    │     │  (runc/gvisor/FC)    │
└──────────────────────┘     └──────────────────────┘

┌──────────────────────┐     ┌──────────────────────┐
│  Tetragon (eBPF)     │────►│  Telemetry Daemon    │
│  - sched_switch      │     │  (Go, DaemonSet)     │
│  - syscalls          │     │  aggregates 500ms    │
│  - page faults       │     │  windows → gRPC      │
└──────────────────────┘     └──────────────────────┘
```

## Data flow on workspace creation

```
1. User POST /workspaces        →  Backend
2. Backend computes risk_score   →  selects sandbox tier
3. Backend asks Scheduler (gRPC) →  optimal node + cluster
4. Scheduler returns placement   →  Backend creates Pod manifest
5. Karmada propagates Pod        →  chosen cluster
6. Pod boots in selected runtime →  WebSocket terminal + Yjs editor ready
7. eBPF telemetry begins flowing →  feeds back into Scheduler state
```

## Component responsibilities

| Component | Owner | Tech |
|---|---|---|
| Frontend          | Person 3 | Next.js, Monaco, Yjs, y-monaco |
| Backend API       | Person 3 | FastAPI, SQLAlchemy, JWT |
| Collab Server     | Person 3 | Node.js, y-websocket |
| PPO Scheduler     | Person 1+2 | Python, Stable-Baselines3, Gymnasium |
| LSTM Prewarmer    | Person 2 | PyTorch |
| Risk Scorer       | Person 1 | Python (pure functions, fully tested) |
| eBPF Probes       | Person 1 | C (libbpf), Go aggregator |
| Karmada Config    | Person 1 | YAML |
| Helm Charts       | Person 1 | YAML, Helm |

See `README.md` (parent dir) for the full 7-week plan.
