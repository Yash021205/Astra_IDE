# PF-MPPO — training runbook

How to train the PF-MPPO scheduler and deploy the trained model into the backend.
Two workload sources: **synthetic** (no data needed) and the **real Google cluster
trace** (download required, best on GPU/Colab — see `notebooks/pfmppo_training.ipynb`).

---

## 0. Setup
```bash
pip install -r ml/requirements.txt
# train as a module from the repo root:
#   python -m ml.scheduler.pfmppo.train ...
```

## 1. Quick baseline (synthetic IDE workloads, no dataset, CPU-ok)
```bash
python -m ml.scheduler.pfmppo.train --mode pretrain \
  --config ml/scheduler/pfmppo/configs/4_nodes.json \
  --dag-mode hybrid --iterations 500 --workers 4 --batch-size 600 \
  --num-tasks 30 --num-workspaces-max 12 --out runs/pfmppo/baseline
# → runs/pfmppo/baseline/model.pt
```

## 2. FULL run on the real Google cluster trace (Udit's notes: full dataset + more iterations)

### a. Get the data (Google Cluster Trace 2011, "clusterdata-2011-2")
Put `machine_events/*.csv.gz` and `task_events/*.csv.gz` under a `data/` dir:
```bash
# follow https://github.com/google/cluster-data (ClusterData2011_2)
# resulting layout:
#   data/google_trace/machine_events/part-*.csv.gz
#   data/google_trace/task_events/part-*.csv.gz
```

### b. Pretrain (Stage 1) — full dataset, high iterations
`--max-files 0` loads the **whole** trace; bump `--iterations` (and `--workers`
to your core count). On GPU this is fast; on CPU expect it to run long.
```bash
python -m ml.scheduler.pfmppo.train --mode pretrain \
  --config ml/scheduler/pfmppo/configs/8_nodes.json \
  --dag-mode trace_hybrid --data-dir data/google_trace --max-files 0 \
  --iterations 5000 --workers 9 --batch-size 1000 \
  --num-tasks 40 --max-steps 300 \
  --out runs/pfmppo/full
```

### c. Fine-tune (Stage 2) — lower LR, continue from Stage 1
```bash
python -m ml.scheduler.pfmppo.train --mode finetune \
  --model-path runs/pfmppo/full/model.pt \
  --config ml/scheduler/pfmppo/configs/8_nodes.json \
  --dag-mode trace_hybrid --data-dir data/google_trace --max-files 0 \
  --iterations 3000 --workers 9 --out runs/pfmppo/full_ft
```

> **GPU / Colab:** use `notebooks/pfmppo_training.ipynb` — same params, just runs on
> a GPU runtime. Upload the trace (or a subset) and run cells top-to-bottom.

## 3. Evaluate
```bash
python benchmarks/b1_scheduler/eval_pfmppo.py --model-path runs/pfmppo/full_ft/model.pt
```

## 4. Deploy the trained model into the live backend
The backend uses the model only when the feature flag is on (otherwise it falls
back to the heuristic scorer — see `backend/app/services/pfmppo_inference.py`).
```bash
# set in backend/.env or the compose backend environment:
SCHEDULER_ALGORITHM=pfmppo
PFMPPO_MODEL_PATH=/app/models/pfmppo.pt
PFMPPO_K_PAIRS=10
# place model.pt at that path (bind-mount or COPY), then restart the backend.
```
If the model is missing or inference errors, placement silently falls back to the
heuristic — so enabling the flag is safe.

## Notes / params (from Udit)
- **Dataset range:** `--max-files 0` = full trace; raise `--num-tasks` / `--max-steps`
  for bigger episodes.
- **Iterations:** raise `--iterations` (Stage 1 + Stage 2). More = better policy.
- **Workers:** set to CPU cores (or leave 9 on GPU).
- A bug was fixed so `--dag-mode` / `--data-dir` / `--template-ratio` / `--max-files`
  now actually reach the training env (previously ignored).
