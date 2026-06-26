# Replacing synthetic data with REAL data (B1 scheduler + B5 federation)

Goal: stop using made-up workloads for the **DRL-PPO scheduler (B1)** and the
**multi-cluster federation (B5)**, and instead drive both from a **real cloud
cluster trace**. This is what reviewers expect and makes the results credible.

---

## 1. How it works RIGHT NOW (in very simple terms)

### B1 — the DRL-PPO scheduler
Think of the scheduler as a **waiter** seating guests (jobs) at tables (servers/nodes).
- **Today:** we *invent* fake guests with random numbers — "this job needs 0.5 CPU, 512 MB, runs for a while." The PPO agent practises seating thousands of these invented guests and learns a good seating strategy (don't overload one table, keep tables balanced, prefer the greener room).
- **Analogy:** it's like training a chess AI on board positions you made up yourself. It *does* learn — but a reviewer trusts it far more if you train it on **real recorded games**.
- **The fix:** feed it **real jobs** from an actual datacenter trace (each row = a real job that really ran, with its real CPU/memory/duration/arrival time), instead of random numbers. The PPO code doesn't change — only the *source of the jobs* changes.

### B5 — the multi-cluster federation
Think of 4 restaurants (clusters) in 4 cities, and one manager (the federation
optimizer) deciding which restaurant each booking goes to.
- **Today:** we *invent* demand — "city A is busy, city C is quiet" — and check the manager balances them.
- **The fix:** take a **real trace**, split its machines into 4 groups (= 4 clusters/regions), replay the **real bookings** (jobs) as they actually arrived, and let the manager route them. Add **real carbon data** per region (we already have the UK Carbon API in B6).

So: **one real trace can feed BOTH B1 and B5.** That's the whole plan.

---

## 2. The real datasets to use (with links)

These are the standard datacenter/cluster traces used in scheduling research:

| Dataset | What's inside | Size | Link |
|---|---|---|---|
| **Alibaba Cluster Trace 2018** ⭐ | Real jobs + machines, batch + online services co-located, 8 days, 4000 machines | ~270 GB full (use a **sample**) | github.com/alibaba/clusterdata |
| **Google Borg Trace 2011** ⭐ | Real tasks, resource requests, machine events, 29 days | ~40 GB | github.com/google/cluster-data |
| **Google Borg Trace 2019** | Newer, much bigger | ~2.4 TB (BigQuery only — query a slice) | github.com/google/cluster-data |
| **Azure VM Trace (v2)** | VM creations, CPU readings, lifetimes | ~large (use a slice) | github.com/Azure/AzurePublicDataset |
| **Microsoft Philly Traces** | GPU/deep-learning job scheduling | moderate | github.com/msr-fiddle/philly-traces |

**Recommendation:** use **Alibaba 2018** or **Google 2011**. They're the most-cited for DRL scheduling, and you only need a **small slice** (e.g. the first day, or the first ~50–100k tasks) — do **not** download the whole thing.

> ⚠️ These are huge. Always work with a **subset/sample** (one day file, or first N rows). Many published papers use exactly a slice, not the full trace.

---

## 3. How to FIND datasets yourself (the method)

So you're not dependent on this list next time:

1. **Copy the paper.** Find a recent DRL-scheduling paper (we already cite **Xu 2024, arXiv:2403.07905**). Look in its "Evaluation/Dataset" section — use the **same dataset they used**. This is the academic gold standard ("same method, same data").
2. **Papers With Code** — paperswithcode.com → search "cluster scheduling" or "resource management" → each task lists the datasets used.
3. **The big-3 cloud GitHub repos** — Google (`google/cluster-data`), Alibaba (`alibaba/clusterdata`), Azure (`Azure/AzurePublicDataset`). These are *the* sources.
4. **Search terms that work:** "cluster scheduling trace dataset", "datacenter job trace", "Borg trace", "Alibaba cluster trace", "Kubernetes workload trace", "VM scheduling dataset".
5. **Repositories:** Zenodo, IEEE DataPort, Kaggle, the Grid/Parallel Workloads Archive (HPC `.swf` traces).

---

## 4. The concrete plan (what to actually build)

### Step 1 — a trace loader (the only new code)
Write `ml/scheduler/trace_loader.py`:
- Reads a slice of the Alibaba/Google CSV.
- Converts each row into the **same job shape** the env already expects
  (`cpu_req`, `mem_req`, `duration`, `arrival_time`, and we map a `risk` from the job type).
- Yields jobs in arrival order.

Add a flag so we can switch: `--source synthetic` (old) vs `--source alibaba` (new).
Nothing else in the PPO/env code needs to change — we just swap the job source.

### Step 2 — retrain + re-evaluate B1
Train the PPO on the real jobs, evaluate against the same baselines on the same real slice.
Report the new numbers (these replace the synthetic ones in the report).

### Step 3 — feed B5 from the same trace
In `ml/federation/optimizer.py`, split the trace's machines into **4 clusters** and
replay real arrivals; attach real per-region carbon (electricityMaps/UK API).
Re-run the Table I comparison with real demand across 4 clusters.

### Step 4 — keep synthetic only as a fast fallback
Leave the synthetic generator for the *live website* simulator (it needs to run
instantly in the browser), but the **research numbers come from the real trace.**

---

## 5. Guide for Udit — tasks, training, and pushing code

### His tasks (in order)
1. **Build `ml/scheduler/trace_loader.py`** (Alibaba 2018 slice → job objects).
2. **Retrain PPO** on real jobs; run `benchmarks/b1_scheduler/eval_scheduler.py` → new numbers.
3. **Extend `ml/federation/optimizer.py`** to 4 clusters fed by the real trace.
4. Produce **plots** (reward curve, latency/utilization bars) for the report.

### How he downloads a dataset (example — Alibaba)
```bash
# clone the trace repo (it's mostly docs + download scripts)
git clone https://github.com/alibaba/clusterdata.git
# follow cluster-trace-v2018/ README to fetch ONE file (e.g. batch_task.csv sample)
# put the CSV under ml/scheduler/data/  (this folder is gitignored)
```

### How he trains
```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -r ml/requirements.txt
# after writing the loader:
python ml/scheduler/train.py --source alibaba --timesteps 1000000
python benchmarks/b1_scheduler/eval_scheduler.py --source alibaba
```

### How he pushes code (team rules)
```bash
git checkout -b udit/real-trace
git add ml/scheduler/trace_loader.py ml/scheduler/train.py benchmarks/ docs/
# DO NOT add the dataset CSVs — they're huge and gitignored
git commit -m "b1: drive scheduler from real Alibaba 2018 trace, reward 195 vs 84 baseline"
git push origin udit/real-trace
# open a PR; Prasanna reviews and merges to main
```

### Rules to repeat to him
- **Never commit datasets or model weights** — they're gitignored. Commit **code + result numbers + plots** only.
- Always work on a **branch**, never push to `main` directly.
- Terse commit messages, **no "Claude/AI" attribution**.
- To compare with the old synthetic numbers, run **the same eval script** so it's apples-to-apples.

---

## TL;DR
- Right now B1 and B5 use **made-up jobs**. Replace that with a **real cluster trace** (Alibaba 2018 or Google Borg 2011) via a small `trace_loader.py` — the AI code stays the same, only the data source changes.
- One trace feeds **both** B1 (scheduling) and B5 (4-cluster federation).
- Use a **slice**, not the whole TB-scale dataset.
- Keep synthetic only for the instant in-browser demo; research numbers come from real data.
