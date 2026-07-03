# %% [markdown]
# # B4 — Anomaly IDS: train on REAL syscall datasets (Kaggle)
#
# Produces the committable artifact `ml/anomaly_ids/artifacts/{ids.joblib, metrics.json}`
# by running the repo's real evals on **ADFA-LD** and **LID-DS 2021**.
#
# ## How to run on Kaggle
# 1. New Notebook → **Add Data**: attach the public datasets
#    - **ADFA-LD** (host syscall traces) and
#    - **LID-DS 2021** (multi-scenario CVE traces).
#    (Search Kaggle Datasets; if a version isn't there, upload the official release as a
#    private dataset once.)
# 2. **Add Data → GitHub / or upload** the `astra-ide` repo (or just the `ml/` + `benchmarks/`
#    folders) so the code is importable. Set `REPO` below to its path.
# 3. Set `ADFA_ROOT` and `LIDDS_ROOT` to the attached dataset paths under `/kaggle/input/...`.
# 4. Run all. Download `ml/anomaly_ids/artifacts/` from the output and **commit it**.
#
# CPU is fine (sklearn); no GPU needed. Runtime ~minutes with the default caps.

# %%
import subprocess, sys, os, shutil, json
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "numpy", "scikit-learn", "joblib"], check=True)

# %%
# --- Point these at your Kaggle paths -------------------------------------------------
REPO       = Path("/kaggle/input/astra-ide")          # repo root (has ml/ and benchmarks/)
ADFA_ROOT  = Path("/kaggle/input/adfa-ld/ADFA-LD")    # contains Training_Data_Master, etc.
LIDDS_ROOT = Path("/kaggle/input/lid-ds-2021/_extracted")  # contains <scenario>/ folders
OUT        = Path("/kaggle/working/artifacts")         # where we drop the artifact to download
# --------------------------------------------------------------------------------------
assert (REPO / "ml" / "anomaly_ids" / "detector.py").exists(), f"repo not found at {REPO}"
sys.path.insert(0, str(REPO))
OUT.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## LID-DS 2021 — full 3-stage pipeline → the committed artifact
# Fits `ContainerIDS` (RF over scenarios + ensemble of Isolation Forests) on real normal
# behaviour and evaluates on held-out normal + real CVE-attack recordings.

# %%
lidds = subprocess.run([
    sys.executable, str(REPO / "benchmarks/b4_sandboxing/eval_ids_lidds.py"),
    "--root", str(LIDDS_ROOT),
    "--cap", "150", "--walks", "300", "--window", "500", "--stride", "250", "--maxwin", "8",
    "--save-artifact", str(REPO / "ml/anomaly_ids/artifacts/ids.joblib"),
    "--metrics-out",   str(REPO / "ml/anomaly_ids/artifacts/metrics.json"),
], text=True)
print("LID-DS eval exit:", lidds.returncode)

# %% [markdown]
# ## ADFA-LD — single-workload separability sanity check (Stage 1 + Stage 3)

# %%
subprocess.run([
    sys.executable, str(REPO / "benchmarks/b4_sandboxing/eval_ids_adfa.py"),
    "--root", str(ADFA_ROOT), "--cap", "800", "--walks", "500",
], text=True)

# %% [markdown]
# ## Collect the artifact for download + commit

# %%
art_dir = REPO / "ml/anomaly_ids/artifacts"
for f in ("ids.joblib", "metrics.json"):
    src = art_dir / f
    if src.exists():
        shutil.copy(src, OUT / f)
        print("ready to download:", OUT / f, f"({src.stat().st_size} bytes)")

metrics_path = art_dir / "metrics.json"
if metrics_path.exists():
    m = json.loads(metrics_path.read_text())
    print("\n=== REAL metrics (quote these to the panel) ===")
    print(json.dumps({k: m[k] for k in ("f1", "fpr", "roc_auc", "recall_tpr") if k in m}, indent=2))

# %% [markdown]
# ### After the run
# Download `/kaggle/working/artifacts/{ids.joblib, metrics.json}`, drop them into
# `ml/anomaly_ids/artifacts/` in your local repo, and commit (the `.gitignore` already
# whitelists `ml/**/artifacts/`). The live IDS loop loads `ids.joblib` via
# `ContainerIDS.load(...)`.
