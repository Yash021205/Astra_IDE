# Datasets — what we used, where, and how to get them again

Authoritative list (reconstructed from `benchmarks/*/README.md` + the eval scripts).
**Important distinction:**
- The **live product** (the website) does **NOT** use any of these datasets at runtime. Workspaces, scheduling decisions, and the live `/benchmarks` page all run on **simulated/synthetic** data generated on the fly.
- These datasets are used **offline**, in the `benchmarks/` folder, to **validate each breakthrough against its paper** on real data. That's the research evidence.

---

## Dataset per breakthrough

| # | Breakthrough | Dataset | Real or synthetic | Where to get it |
|---|---|---|---|---|
| **B1** | DRL-PPO scheduler | **None** — RL self-play in our simulated cluster (`ml/scheduler/env.py`) | Synthetic (Gymnasium env) | No download; the env generates jobs + cluster state |
| **B2** | eBPF telemetry (HashPipe) | Synthetic per-PID streams **+ our first-party Tetragon corpus** (171k kernel events) | Mixed | First-party corpus captured on the GCP VM via `scripts/gcp/tetragon-corpus.sh` |
| **B3** | LSTM prewarming | **Azure Functions 2019 trace** (Shahrad et al., Microsoft) | Real | github.com/Azure/AzurePublicDataset (143 MB) — see command below |
| **B4** | Adaptive sandboxing — policy gate | **NL2Bash** (10.6k real developer bash commands) + SandboxEscapeBench | Real | github.com/TellinaTool/nl2bash (auto-downloaded by `make_policy_gate_set.py`) |
| **B4** | Adaptive sandboxing — IDS | **ADFA-LD** (UNSW Canberra) + **LID-DS-2021** (Leipzig) + our **Tetragon 171k corpus** | Real | ADFA-LD vendored in `benchmarks/b4_sandboxing/data/`; LID-DS-2021 downloaded manually |
| **B5** | Multi-cluster federation | **None** — simulated multi-cluster demand (hot/cold clusters) | Synthetic | No download; simulator in `ml/federation/optimizer.py` |
| **B6** | Carbon-aware scheduling | **UK Carbon Intensity API** (live gCO2/kWh grid trace) | Real | api.carbonintensity.org.uk — free, no key, fetched live by `eval_carbon.py` |
| **B7** | CRDT collaboration | **automerge-paper editing trace** (josephg/editing-traces) | Real | github.com/josephg/editing-traces (`automerge-paper.json.gz`) |

---

## How to download the two that need manual fetch

### B3 — Azure Functions 2019 trace (the main training dataset)
```bash
cd benchmarks/b3_prewarming
mkdir -p data/_extracted
# 143 MB download, then extract one day file:
curl -sL https://github.com/Azure/AzurePublicDataset/releases/download/dataset-functions-2019/azurefunctions_dataset2019_azurefunctions-dataset2019.tar.xz -o data/azure2019.tar.xz
tar -xJf data/azure2019.tar.xz -C data/_extracted invocations_per_function_md.anon.d01.csv
```

### B4 — LID-DS-2021 (multi-class IDS)
Downloaded manually from the LID-DS-2021 release (we used the 3 smallest scenarios, ~2.3 GB). ADFA-LD is already vendored in the repo under `benchmarks/b4_sandboxing/data/`.

---

## For Udit: training longer

**B1 (PPO scheduler) — no dataset, just train more steps.**
The PPO learns by self-play in the simulated cluster, so "more data" = "more timesteps."
```bash
pip install -r ml/requirements.txt
# Open ml/scheduler/train.py and raise total_timesteps (e.g. 200_000 -> 1_000_000),
# optionally enable GPU. Then:
python ml/scheduler/train.py
# Evaluate against baselines on the SAME harness so results are comparable:
python benchmarks/b1_scheduler/eval_scheduler.py
```
Our committed number to beat: **PPO reward 177 (+112% vs least-loaded), 0.57% SLA violations.**

**B3 (LSTM prewarming) — real dataset, train on more of it.**
We only used **day 1** (`d01.csv`). For more training data, extract more day files from the same Azure tarball and pass them, or train more epochs:
```bash
# extract several days
tar -xJf data/azure2019.tar.xz -C data/_extracted \
  invocations_per_function_md.anon.d01.csv \
  invocations_per_function_md.anon.d02.csv \
  invocations_per_function_md.anon.d03.csv
python benchmarks/b3_prewarming/eval_azure_global.py \
  --csv data/_extracted/invocations_per_function_md.anon.d01.csv --n-functions 150
```
Our committed number to beat: **median N-RMSE 0.085** (beats the paper's per-function LSTM).

**Rule for comparing his results to ours:** run his model through **our** eval script with the **same seed/dataset**. Only then are the numbers comparable. If he used a different env/dataset, align first, then compare, then keep the better model and update the report.

---

## What the live `/benchmarks` page actually is (and why it reruns)

The website's Benchmarks page is a **fast in-browser simulator**, NOT the dataset benchmarks above.

- It generates **N synthetic jobs** (you pick 50–1000) and replays them against a **live snapshot** of the (simulated) cluster telemetry, once per scheduling policy (ASTRA PPO vs Round-Robin / Random / FIFO / Least-Loaded).
- **Why the numbers change each run:** unless you keep the **same seed**, a different random workload is generated each time → different jobs → slightly different results. Same seed = identical, reproducible run.
- **Why the deltas look small:** this is a lightweight *sanity-check replay*, not the full RL training. The headline research result (**PPO +112% reward**) comes from the offline training on the datasets above, not from this quick replay. The page proves "the policy is sensibly better under live conditions"; the offline benchmarks prove "by how much, on real data, vs the paper."
- **What each metric means:** see the "How these numbers are computed" panel on the page (startup latency, utilization, balance score, energy proxy, SLA breaches).
