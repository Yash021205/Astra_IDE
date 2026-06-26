# ASTRA-IDE — User Walkthrough

How a developer uses ASTRA-IDE end to end, and which research breakthrough powers
each step. Local URLs: **frontend http://localhost:3000**, backend API docs
**http://localhost:8000/api/v1/docs** (Swagger). On the LAN, replace `localhost`
with the host IP (e.g. `http://10.127.3.228:3000`).

## 0. Start the platform (3 processes)
```bash
# 1) backend (FastAPI, SQLite)         — port 8000
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
# 2) frontend (Next.js, proxies /api → backend)  — port 3000
cd frontend && BACKEND_URL=http://127.0.0.1:8000 npm run dev
# 3) collab server (Yjs websocket, for live editing) — port 1234
cd collab-server && node server.js
```
Open **http://localhost:3000**.

## 1. Sign up / log in
Click **Register** → email, username, password. You get a JWT and land on the
**Dashboard**. (Passwords are hashed with pbkdf2_sha256.)

## 2. Create a workspace — *this is where B4 + B5 fire*
**Dashboard → New Workspace.** Pick a name, language, and toggles
(network access, filesystem write). When you create it:
- **B4 (Adaptive Sandboxing)** reads your settings + any initial code, computes a
  **risk score**, and assigns a **sandbox tier**:
  - low risk (e.g. a Python notebook) → **runc** (fast)
  - medium (network + filesystem) → **gVisor**
  - high (shell + Docker socket / escape patterns) → **Firecracker** (micro-VM)
- **B5 (Multi-Cluster)** places the workspace on the best **cluster + node** (load-
  balanced, lowest-carbon). You'll see e.g. `firecracker on cluster-a/node-a-1`.

> **"I have a random GitHub repo I want to use"** — today you bring code in by
> pasting it / creating files in the editor (step 4). A one-field **git-clone-on-
> create** (paste a GitHub URL → the workspace clones it on first boot) is the
> natural next addition; the workspace pod already has a writable volume for it.

## 3. See the global picture — *B2 + B5 + B6*
**Clusters page** shows the live federation:
- per-node **CPU / memory / run-queue / network** — the **B2 eBPF telemetry** feed
  (500 ms resolution in production).
- each cluster's **carbon intensity** (gCO2/kWh) from **B6** — Denmark ~58 (wind),
  India ~628 (coal), France ~10 (nuclear), live from the carbon API.
- the **B5** view of which workspaces run where.

## 4. Open the workspace — write & run code — *B4 policy gate*
Click a workspace → the **Monaco editor** opens.
- Type code, hit **RUN**. Output appears in the panel.
- **B4's policy gate** screens every run: benign code executes; **destructive /
  escape commands are blocked before they run** — try `rm -rf /`, a fork bomb, or
  `cat /proc/self/exe` and you'll get **"Policy Violation"** instead of damage.

## 5. Collaborate live — *B7 CRDT*
Share the workspace (**Share** → a teammate's username). Both of you edit the same
file simultaneously; the **B7 CRDT (Yjs)** merges concurrent edits so everyone
converges to the same document — no lost keystrokes, no central lock.

## 6. Fast starts — *B3 pre-warming*
When you (or your team) tend to open workspaces, **B3's LSTM** predicts demand and
**pre-warms** a pod ahead of time, so opening is near-instant instead of a cold
start. The workspace card shows a **PREWARM** indicator when a warm pod was used.

## 7. Smart scheduling under the hood — *B1 + B6*
Every placement is scored by **B1's reward** (utilisation, balance, latency,
energy, carbon, minus SLA + sandbox-mismatch penalties). Deferrable batch work
(CI, tests, nightly jobs) is shifted by **B6** to low-carbon time windows. The
**Benchmarks page** shows the learned scheduler vs baselines.

## The 7 breakthroughs, as the user feels them
| You do… | Powered by |
|---|---|
| Create a workspace → it gets the right security cage | **B4** adaptive sandboxing |
| …placed on the best cluster/node | **B5** multi-cluster + **B1** RL scheduler |
| Open it instantly | **B3** LSTM pre-warming |
| Run code safely (bad code blocked) | **B4** policy gate |
| Edit together live | **B7** CRDT collaboration |
| See live cluster health + carbon | **B2** eBPF telemetry + **B6** carbon-aware |

Each is grounded in a 2022–2026 paper and benchmarked against the recognized
dataset (see `benchmarks/*/README.md`).
