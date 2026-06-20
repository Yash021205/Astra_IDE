# ASTRA-IDE

**Adaptive Scheduling & Telemetry-driven Resource-aware Cloud IDE**

A cloud development environment combining **DRL-PPO scheduling**, **eBPF observability**,
**adaptive sandboxing** (runc / gVisor / Firecracker), **LSTM-based predictive prewarming**,
**multi-cluster Karmada federation**, **carbon-aware scheduling**, and **Yjs CRDT
collaboration** in one open research platform.

Live demo: **http://34.47.224.18:3000**

---
## Contribution
Developed as part of a collaborative project; repository reflects my implementation of project and ongoing experimentation.

## Repository layout

```
astra-ide/
├── backend/            FastAPI service: auth, workspace API, scheduler, events, metrics
├── frontend/           Next.js 14 + Monaco + Yjs + Aceternity-style components
├── collab-server/      y-websocket relay for collaborative editing
├── ml/
│   ├── scheduler/      PPO agent + Gymnasium env + reward function
│   ├── prewarming/     LSTM session-start predictor + synthetic dataset
│   └── risk_scorer/    Workload risk -> sandbox tier selector
├── ebpf/               libbpf probes + Go telemetry aggregator (planned)
├── k8s/                Helm charts, manifests, Karmada policies, RuntimeClasses
├── deploy/             docker-compose for local + prod
├── docs/
│   ├── LEARNING_AND_TASKS.md   role-specific stack to learn + concrete tickets
│   ├── TEAM_GUIDE.md           week-by-week task split, ops runbook
│   ├── ARCHITECTURE.md         system diagram + data flow
│   ├── API.md                  REST API reference
│   ├── ML.md                   PPO / LSTM training docs
│   ├── DEPLOY.md               production deploy guide
│   └── DEVELOPMENT.md          contributor conventions
└── .github/workflows/  CI tests + Docker image build
```

---

## Quick start (everyone reads this first)

### 1. Prerequisites

- **Git** + a GitHub account (added as collaborator on this private repo)
- **Docker Desktop** (Mac/Windows) or Docker Engine + Compose (Linux)
- **Python 3.12+** and **Node 20+** if you want to run backend/frontend natively
- An IDE (VS Code recommended)

### 2. Clone

```bash
git clone https://github.com/PrasannaMishra001/astra-ide.git
cd astra-ide
```

### 3. Quickest path — full stack via Docker Compose (5 min)

```bash
cp backend/.env.example backend/.env
# Edit backend/.env: paste your electricityMaps token (or leave blank for fallback)

cd deploy
docker compose up -d --build
```

Open:
- Frontend: <http://localhost:3000>
- Backend Swagger: <http://localhost:8000/api/v1/docs>
- Collab WS health: <http://localhost:1234/healthz>

Stop: `docker compose down`.

### 4. Native dev (faster iteration, hot reload)

Run only the data plane in Docker, then code natively:

```bash
# Data plane (Postgres + Redis + MinIO + collab server)
docker compose -f deploy/docker-compose.dev.yml up -d
```

Backend:
```bash
cd backend
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # edit with your tokens
uvicorn app.main:app --reload --port 8000
```

Frontend (in a separate shell):
```bash
cd frontend
npm install --legacy-peer-deps
cp .env.local.example .env.local    # if it exists
npm run dev                          # http://localhost:3000
```

### 5. Run the test suites

```bash
# ML tests (no extra deps required)
python -m unittest \
  ml.risk_scorer.test_scorer \
  ml.scheduler.test_env \
  ml.prewarming.test_dataset -v

# Backend tests
cd backend && python -m unittest discover -s tests -v

# Frontend type-check + build
cd frontend && npx tsc --noEmit && npm run build
```

---

## Tech stack at a glance

| Layer | Stack |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind, Monaco Editor, Yjs + y-monaco, Framer Motion, Zustand, Axios |
| Backend  | FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL / SQLite, Redis, JWT, asyncio |
| Collab   | Node.js + `y-websocket` |
| ML       | PyTorch, Stable-Baselines3 (PPO), Gymnasium, NumPy, pandas |
| Infra    | Docker, k3s, Karmada, Helm, KEDA, Tetragon (eBPF), Prometheus, Grafana, MinIO |
| Sandbox  | runc, gVisor (runsc), Firecracker (via Kata Containers) |
| CI       | GitHub Actions, GHCR for container images |
| External | electricityMaps API (carbon intensity) |

For learning paths organized by role, see [`docs/LEARNING_AND_TASKS.md`](docs/LEARNING_AND_TASKS.md).
For week-by-week task split, see [`docs/TEAM_GUIDE.md`](docs/TEAM_GUIDE.md).

---

## What's working today

- Risk-scored adaptive sandboxing (runc / gvisor / firecracker assignment)
- PPO-style placement scheduler with cluster_state + reward function
- Live electricityMaps carbon API + fallback table
- Persistent SchedulerEvent log + activity feed (polled by frontend)
- Live cluster metrics endpoint, polled by `/clusters` page
- Benchmarks page with PPO vs Round-Robin / Random / FIFO / Least-Loaded
- Workspace CRUD with sharing, role-based access
- Code execution (Python, C++, JavaScript, Bash) with 5s timeout
- Yjs CRDT collaboration in Monaco (multi-cursor, awareness, multi-tab sync)
- VS Code-style editor UI (status bar, keybindings cheatsheet, command palette,
  tabbed bottom panel — output / problems / terminal)
- Toast notifications, workspace templates, 3D card effects, interactive globe

## What's not yet wired (see `docs/LEARNING_AND_TASKS.md` Part C)

- Trained PPO model file checked in
- Trained LSTM weights checked in
- Live K8s cluster (currently using in-memory mock)
- Tetragon eBPF actually deployed
- gVisor + Firecracker on a real node
- Second cluster + Karmada
- xterm.js terminal panel
- LSP autocomplete
- MinIO workspace persistence

---

## Deployment

For deploying to a real Kubernetes cluster (Phase 3+), see [`docs/DEPLOY.md`](docs/DEPLOY.md).

Current production deployment lives on a GCP VM (`asia-south1`, e2-standard-2)
behind public IP `34.47.224.18`. Docker Compose stack restarts automatically
on VM reboot.

---

## License

Research project — license TBD before final submission.
