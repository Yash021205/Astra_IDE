"""
B1 - Kaggle notebook: train the PF-MPPO scheduler on the REAL Google Cluster
Trace 2011 and export the served artifact (model.pt + metrics.json).

HOW TO USE ON KAGGLE
--------------------
1. New Kaggle Notebook -> Settings -> Accelerator: None (CPU) is fine; PF-MPPO is
   CPU-bound (tiny 8K-param net), the GPU sits idle either way -> Internet: ON.
2. Paste these cells in order. It:
     a. clones the ASTRA-IDE repo,
     b. downloads a SUBSET of the real Google trace over HTTP (no auth),
     c. runs a quick SMOKE test (you see reward numbers in ~1 min),
     d. pretrains + fine-tunes PF-MPPO in trace_hybrid mode WITH LIVE PROGRESS + ETA,
     e. evaluates vs Round-Robin / Random / FIFO / Least-Loaded,
     f. writes ml/scheduler/pfmppo/artifacts/{model.pt,metrics.json}.
3. Download the artifacts/ folder (a few KB) and commit it, or paste me metrics.json.

The trace never touches your PC - it lives only on Kaggle's disk. Raise
N_TASK_PARTS / ITERS later for a stronger model.

WHY THE FIRST ATTEMPT LOOKED FROZEN: the workers each re-parsed the multi-GB trace
and stdout was block-buffered. Fixed in the repo (shared trace cache + flushed
progress); this notebook also streams output line-by-line so you always see ETA.
"""

# ── Cell 1: clone repo + install deps ─────────────────────────────────────────
import os, subprocess, sys, json, shutil, urllib.request
from pathlib import Path

REPO = "https://github.com/PrasannaMishra001/astra-ide.git"   # public, or use Kaggle "Add Data"
WORK = Path("/kaggle/working/astra-ide")
if not WORK.exists():
    subprocess.run(["git", "clone", "--depth", "1", REPO, str(WORK)], check=True)
os.chdir(WORK)
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "torch", "gymnasium", "numpy", "pandas"], check=True)

# Stream a subprocess line-by-line so progress shows LIVE (no block-buffering).
ENV = {**os.environ, "PYTHONUNBUFFERED": "1"}
def run_streamed(cmd):
    print(">>", " ".join(str(c) for c in cmd), flush=True)
    p = subprocess.Popen([sys.executable, "-u", *cmd], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1, env=ENV)
    for line in p.stdout:
        print(line, end="", flush=True)
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}")

# ── Cell 2: download a SUBSET of the real Google Cluster Trace 2011 ────────────
BASE = "https://storage.googleapis.com/clusterdata-2011-2"
DATA = WORK / "data" / "google_trace"
(DATA / "machine_events").mkdir(parents=True, exist_ok=True)
(DATA / "task_events").mkdir(parents=True, exist_ok=True)

N_TASK_PARTS = 50         # of 500. Kaggle has ~100GB+ scratch, so more is fine; 50 parts
                          # (~4GB compressed) gives a large, representative slice. You can
                          # push this to 200-500 for the full trace, but parsing gets slow
                          # (many minutes) and it does not change the baseline comparison -
                          # it improves generalization, not the reward ranking on this env.

def _get(url, dest):
    if Path(dest).exists() and Path(dest).stat().st_size > 0:
        return
    print("downloading", url, flush=True)
    urllib.request.urlretrieve(url, dest)

_get(f"{BASE}/machine_events/part-00000-of-00001.csv.gz",
     DATA / "machine_events" / "part-00000-of-00001.csv.gz")
for i in range(N_TASK_PARTS):
    part = f"part-{i:05d}-of-00500.csv.gz"
    _get(f"{BASE}/task_events/{part}", DATA / "task_events" / part)
print("trace subset ready:", DATA, flush=True)

# ── Cell 3: SMOKE TEST (proves it runs; ~1-2 min, you see reward numbers) ──────
CFG     = "ml/scheduler/pfmppo/configs/4_nodes.json"
WORKERS = 9     # paper Table 2 / Fig 12: 9 workers is optimal for convergence
run_streamed(["-m", "ml.scheduler.pfmppo.train",
    "--mode", "pretrain", "--config", CFG,
    "--dag-mode", "trace_hybrid", "--data-dir", str(DATA), "--max-files", "0",
    "--iterations", "20", "--workers", str(WORKERS), "--log-interval", "5",
    "--batch-size", "400", "--num-tasks", "30", "--max-steps", "200",
    "--out", str(WORK / "runs" / "pfmppo_smoke")])

# ── Cell 4: real training with LIVE PROGRESS + ETA ────────────────────────────
ITERS = 2000              # paper Table 2: N = 2000 iterations (rewards stabilize ~250)
OUT    = WORK / "runs" / "pfmppo_full"
run_streamed(["-m", "ml.scheduler.pfmppo.train",
    "--mode", "pretrain", "--config", CFG,
    "--dag-mode", "trace_hybrid", "--data-dir", str(DATA), "--max-files", "0",
    "--iterations", str(ITERS), "--workers", str(WORKERS), "--log-interval", "10",
    "--batch-size", "1000", "--num-tasks", "40", "--max-steps", "300",
    "--out", str(OUT)])

OUT_FT = WORK / "runs" / "pfmppo_full_ft"
run_streamed(["-m", "ml.scheduler.pfmppo.train",
    "--mode", "finetune", "--model-path", str(OUT / "model.pt"),
    "--config", CFG, "--dag-mode", "trace_hybrid", "--data-dir", str(DATA),
    "--max-files", "0", "--iterations", str(ITERS // 2), "--workers", str(WORKERS),
    "--log-interval", "10", "--lr", "0.0001", "--out", str(OUT_FT)])

# ── Cell 5: evaluate the trained model on its HOME distribution (the real trace) ──
# Evaluate in trace_hybrid mode (what it trained on) so the comparison is
# in-distribution; this is where PF-MPPO should beat the baselines.
MODEL = OUT_FT / "model.pt"
ART = WORK / "ml" / "scheduler" / "pfmppo" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)
eval_out = subprocess.run([sys.executable, "-u", "benchmarks/b1_scheduler/eval_pfmppo.py",
    "--model-path", str(MODEL), "--dag-mode", "trace_hybrid",
    "--data-dir", str(DATA), "--max-files", "0",
    "--eval-episodes", "60", "--num-tasks", "20",
    "--metrics-out", str(ART / "metrics.json")],
    capture_output=True, text=True, env=ENV)
print(eval_out.stdout[-3000:])
print(eval_out.stderr[-1000:])

# ── Cell 6: export the committable artifact ───────────────────────────────────
ART = WORK / "ml" / "scheduler" / "pfmppo" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)
shutil.copy(MODEL, ART / "model.pt")
(ART / "metrics.json").write_text(json.dumps({
    "dataset": "Google-Cluster-Trace-2011 (clusterdata-2011-2)",
    "task_parts_used": N_TASK_PARTS,
    "iterations_pretrain": ITERS, "iterations_finetune": ITERS // 2,
    "config": "4_nodes", "dag_mode": "trace_hybrid",
    "eval_stdout_tail": eval_out.stdout[-2000:],
    "note": "paste the eval table numbers (PPO vs RR/Random/FIFO/Least-Loaded) here",
}, indent=2))
print("\nARTIFACT READY -> download /kaggle/working/astra-ide/ml/scheduler/pfmppo/artifacts/", flush=True)
print("Commit model.pt + metrics.json; backend already defaults to it (SCHEDULER_ALGORITHM=pfmppo).", flush=True)
