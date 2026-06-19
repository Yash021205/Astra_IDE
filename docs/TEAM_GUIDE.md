# Team Guide — ASTRA-IDE

> Technical reference: who owns what, what to ship each week, how to share VM
> access + secrets, how to recover prod. For setup steps see the root `README.md`.
> For learning paths + concrete tickets see `docs/LEARNING_AND_TASKS.md`.

---

## 1. Roles and code ownership

Sorted by roll number, matching BTP report Section 11.

| Person | Role | Primary domains |
|---|---|---|
| **Prasanna Mishra** (2023IMT-059, lead) | Infrastructure & Scheduler | Kubernetes, DRL-PPO scheduler, eBPF, multi-cluster, Karmada, Helm, CI/CD |
| **Udit Srivastava** (2023IMT-084) | AI / ML | DRL training, LSTM prewarming, reward engineering, benchmarks, notebooks |
| **Yash Wani** (2023IMT-087) | IDE Frontend + Backend API | Next.js, Monaco, Yjs CRDT, FastAPI, WebSocket, xterm.js, MinIO |

Code ownership (which files each person should land changes in):

```
backend/app/api/auth.py                Yash
backend/app/api/workspaces.py          Yash + Prasanna
backend/app/api/events.py              Prasanna
backend/app/api/metrics.py             Prasanna
backend/app/api/benchmarks.py          Udit
backend/app/api/carbon.py              Prasanna
backend/app/services/scheduler_*       Prasanna
backend/app/services/telemetry_*       Prasanna
backend/app/services/cluster_*         Prasanna
backend/app/services/executor_*        Yash
backend/app/services/sharing_*         Yash
backend/app/services/workspace_*       Yash + Prasanna
backend/app/services/carbon_service.py Prasanna
ml/scheduler/                          Udit
ml/prewarming/                         Udit
ml/risk_scorer/                        Udit + Prasanna
collab-server/                         Yash
frontend/                              Yash
ebpf/                                  Prasanna
k8s/                                   Prasanna
.github/workflows/                     Prasanna
docs/                                  Everyone
```

Lock conventions:
- Push directly to `main` is fine (no protection rule); use a feature branch when
  the change is risky or you want pre-merge eyes.
- When two of us touch the same file in the same week, the slower PR rebases on
  the faster one.

---

## 2. Week-by-week task split

(See BTP report Sections 10–11 for the source-of-truth plan.)

### Week 2 (May 13–19) — IDE polish + CRDT

| Person | Tickets |
|---|---|
| Prasanna | Wire eBPF probes (Tetragon Helm chart on local k3s). Write gRPC schema for telemetry → PPO state. |
| Udit     | Run `python -m ml.scheduler.train --timesteps 100000` against the simulated env. Save model, write `ml/scheduler/EVAL.md`. |
| Yash     | xterm.js terminal panel in editor. File tree component (multi-file workspaces). |

### Week 3 (May 20–26) — Sandboxing + scheduler skeleton

| Person | Tickets |
|---|---|
| Prasanna | Install gVisor + Kata on a local k3s node. Validate `kubectl apply` with each `runtimeClassName`. |
| Udit     | Tune PPO hyperparameters. Add carbon to reward function. First comparison chart for the report. |
| Yash     | Workspace persistence — save buffer to MinIO on shutdown, restore on start. |

### Week 4 (May 27–Jun 2) — eBPF live + PPO online

| Person | Tickets |
|---|---|
| Prasanna | Custom libbpf probe for `sched_switch`. Go DaemonSet aggregator → gRPC server. |
| Udit     | Online fine-tuning loop: feed real telemetry into PPO via gRPC client. |
| Yash     | LSP sidecars (pylsp for Python, clangd for C++). Monaco autocomplete integration. |

### Week 5 (Jun 3–9) — LSTM + multi-cluster

| Person | Tickets |
|---|---|
| Prasanna | Provision second GCP VM (or Oracle if card works). Install k3s + Karmada. Register both clusters. |
| Udit     | Train LSTM on synthetic dataset. Wire prediction into warm-pool controller. |
| Yash     | Workspace sharing polish. User profile page. |

### Week 6 (Jun 10–16) — Energy + integration

| Person | Tickets |
|---|---|
| Prasanna | KEDA ScaledObject for workspace queue. Carbon dimension in deployed scheduler. |
| Udit     | Ablation study: PPO with/without carbon, with/without eBPF. Write comparison section of paper. |
| Yash     | End-to-end demo recording: register → create → collab → run → share. Polish error states. |

### Week 7 (Jun 17–23) — Testing + paper

| Person | Tickets |
|---|---|
| Prasanna | Locust load test. Security probe in gVisor tier. |
| Udit     | Final PPO benchmark. All charts for paper. |
| Yash     | CRDT stress test (10 simulated clients). Demo video edit. |

---

## 3. Sharing access to the GCP VM

The VM at `34.47.224.18` stays on Prasanna's GCP billing. Give SSH access without
sharing the gcloud account.

In GCP Console → IAM → grant each teammate's Google email:
- **Compute OS Login** (SSH access via their own Google account)
- **Compute Instance Admin (v1)** (can start/stop/edit the VM)

OR just **Editor** in one click (broader, works fine for a 3-person project).

After granting, they can:
```bash
gcloud compute ssh astra-cluster-a --zone=asia-south1-a
# (or click SSH in the GCP Console)
```

Deploy flow stays the same once SSH'd in:
```bash
cd ~/astra-ide
git pull origin main
cd deploy
export PUBLIC_HOST=34.47.224.18
docker compose build --no-cache backend frontend
docker compose up -d
```

---

## 4. Sharing secrets between teammates

Never put secrets in the repo. Current secrets:

- `JWT_SECRET` — backend signing key (regenerate per-deploy is fine)
- `ELECTRICITY_MAPS_TOKEN` — carbon API key

Distribution options, in order of preference:

1. **GitHub Secrets** (best for CI) — settings → secrets → actions. Add
   `ELECTRICITY_MAPS_TOKEN` so the Docker workflow can use it.
2. **Shared Bitwarden / 1Password vault** (best for human use) — free tier
   supports a 3-person org.
3. **Each teammate generates their own electricityMaps free key** (5 min) and
   stores it in their own local `backend/.env` — no sharing required. This is
   the path I'd recommend until we deploy multi-cluster.

---

## 5. If something is broken on prod

```bash
# SSH into the VM (Compute Engine → SSH button works)
cd ~/astra-ide/deploy
docker compose ps                       # which container is unhealthy?
docker compose logs --tail=80 backend   # see recent errors
docker compose restart backend          # quick recovery
```

If a deploy regression:
```bash
git revert HEAD && git push origin main
ssh into VM
cd ~/astra-ide && git pull && cd deploy && docker compose up -d
```

To roll all the way back to a known-good commit:
```bash
git log --oneline -20                    # find the SHA
git revert SHA..HEAD                     # creates revert commits
git push origin main
```

---

## 6. CI status

GitHub Actions runs on every push to `main`:

- `CI` workflow (`.github/workflows/ci.yml`) — runs backend tests, ml tests,
  frontend build, collab server smoke test. ~1.5 min.
- `Build & push images` (`.github/workflows/docker.yml`) — pushes 3 images
  to GHCR (backend, frontend, collab-server). ~5 min.

Latest runs: https://github.com/PrasannaMishra001/astra-ide/actions

If CI is red on `main`, that's blocking — fix or revert before the next push.
