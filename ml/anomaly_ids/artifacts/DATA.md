# B4 Anomaly-IDS artifact provenance

The trained detector + real metrics live here. Produced by the B4 Kaggle notebook
(see `docs-private/make-it-real/01-kaggle-notebooks.md`, NB-B4). Datasets stay OUT of the repo;
only the small fitted model + metrics are committed.

## Files (populated by the training run)
- `ids.joblib` — `ContainerIDS.save()` output: fitted Stage-2 RandomForest + per-class
  Stage-3 Isolation Forests + thresholds + metadata.
- `metrics.json` — real evaluation numbers (the ones to quote).

## Datasets used (fill in exact versions when you run it)
- **ADFA-LD** — host syscall traces, 1 normal class + 6 attack types. Source: UNSW ADFA-LD.
- **LID-DS 2021** — multi-scenario with real CVE exploit traces (e.g. CVE-2014-0160 Heartbleed).
  Source: LID-DS 2021 release.

## Preprocessing
- Each trace → integer syscall-ID sequence → `anonymous_walk_embedding(seq, n_walks=500)` (15-dim,
  length-4 anonymous walks, Bell B4=15).
- Train on NORMAL only (no labelled attacks at fit time); hold out 20% normal for FPR.

## Real target ranges (from the benchmark's own asserts / Paper 3, Iacovazzi & Raza CSR'22)
- ADFA-LD: F1 **0.78–0.99**, FPR **0.024–0.071**, ROC-AUC **> 0.8**.
- LID-DS: full 3-stage detection across normal workload classes.

## How it's served
`ContainerIDS.load("ml/anomaly_ids/artifacts/ids.joblib")` → `.predict(embedding)` in the live IDS
loop (post-Tetragon, B2). If the file is absent, the live loop is disabled and the eval falls back
to fitting on the fly.
