"""
B4 IDS benchmark — Paper 3 (Iacovazzi & Raza, IEEE CSR 2022) on REAL syscall
traces from ADFA-LD.

ADFA-LD is a single-workload host dataset (one "normal" behaviour class + 6
attack types), so this run exercises the paper's NOVEL Stage 1 (anonymous-walk
graph embedding of the syscall sequence) + Stage 3 (Isolation Forest anomaly
score, Eq. 1) on real data. The full 3-stage pipeline — including the Stage 2
multi-class RandomForest over multiple normal WORKLOAD classes — needs a
multi-scenario corpus and is reproduced separately on LID-DS-2021 (see README).
The 3-stage pipeline itself is unit-tested on synthetic multi-class data in
ml/anomaly_ids/test_ids.py.

We report TPR per attack type, FPR on held-out normal, and F1, and compare to
Paper 3's reported ranges (F1 0.78-0.99, FPR 0.024-0.071, with a documented TPR
floor ~0.49 on the hardest attacks).

    python eval_ids_adfa.py --root data/.../ADFA-LD [--cap 800] [--walks 500]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.anomaly_ids.embedding import anonymous_walk_embedding  # noqa: E402

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import roc_auc_score
except ImportError:
    sys.exit("scikit-learn + numpy required: pip install -r ml/requirements.txt")

# Paper 3 parameters
N_ESTIMATORS = 100
CONTAMINATION = 0.025


def _read_trace(path: Path) -> list[int]:
    toks = path.read_text(errors="replace").split()
    out = []
    for t in toks:
        try:
            out.append(int(t))
        except ValueError:
            pass
    return out


def _embed_dir(files: list[Path], walks: int, seed0: int) -> "np.ndarray":
    vecs = []
    for i, f in enumerate(files):
        seq = _read_trace(f)
        if len(seq) >= 2:
            vecs.append(anonymous_walk_embedding(seq, n_walks=walks, seed=seed0 + i))
    return np.asarray(vecs, dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path,
                    help="ADFA-LD root (contains Training_Data_Master, etc.)")
    ap.add_argument("--cap", type=int, default=800,
                    help="max traces per group (speed; 0 = all)")
    ap.add_argument("--walks", type=int, default=500, help="random walks per trace")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    def _files(sub: str) -> list[Path]:
        fs = sorted((args.root / sub).rglob("*.txt"))
        rng.shuffle(fs)
        return fs[:args.cap] if args.cap else fs

    normal = _files("Training_Data_Master") + _files("Validation_Data_Master")
    rng.shuffle(normal)
    attack_dirs = sorted(p for p in (args.root / "Attack_Data_Master").iterdir()
                         if p.is_dir())
    # ADFA-LD groups attacks as <Type>_<runid>; collapse to the attack TYPE.
    by_type: dict[str, list[Path]] = {}
    for d in attack_dirs:
        atype = d.name.rsplit("_", 1)[0]
        by_type.setdefault(atype, []).extend(sorted(d.glob("*.txt")))
    for k in by_type:
        rng.shuffle(by_type[k])
        if args.cap:
            by_type[k] = by_type[k][:args.cap]

    print(f"normal traces: {len(normal)}   attack types: "
          f"{ {k: len(v) for k, v in by_type.items()} }")
    print(f"embedding (walks={args.walks}/trace) ...")

    # 80/20 split of normal: train the detector on normal only (paper: no labelled
    # attacks at training time), hold out 20% normal to measure FPR.
    split = int(len(normal) * 0.8)
    Xtr = _embed_dir(normal[:split], args.walks, seed0=0)
    Xte_normal = _embed_dir(normal[split:], args.walks, seed0=100_000)

    iforest = IsolationForest(n_estimators=N_ESTIMATORS,
                              contamination=CONTAMINATION, random_state=args.seed)
    iforest.fit(Xtr)

    def _flag_rate(X: "np.ndarray") -> float:
        if len(X) == 0:
            return 0.0
        # decision_function < 0 => outlier (anomaly) for IsolationForest
        return float((iforest.decision_function(X) < 0).mean())

    fpr = _flag_rate(Xte_normal)
    # Anomaly score: higher = more anomalous (paper Eq.1 orientation).
    norm_scores = -iforest.decision_function(Xte_normal)

    print(f"\nFPR on held-out normal: {fpr:.3f}   (paper 0.024-0.071)")
    print("TPR by attack type (paper TPR floor ~0.49 on hardest):")
    tprs, all_tp, all_fn = [], 0, 0
    attack_scores = []
    for atype in sorted(by_type):
        Xa = _embed_dir(by_type[atype], args.walks, seed0=hash(atype) % 100_000)
        tpr = _flag_rate(Xa)
        attack_scores.append(-iforest.decision_function(Xa))
        tprs.append(tpr)
        all_tp += int(round(tpr * len(Xa)))
        all_fn += len(Xa) - int(round(tpr * len(Xa)))
        print(f"  {atype:18} n={len(Xa):4d}  TPR={tpr:.3f}")

    # ── Threshold-independent diagnosis: can the embedding separate at all? ──
    a_scores = np.concatenate(attack_scores)
    y = np.r_[np.zeros(len(norm_scores)), np.ones(len(a_scores))]
    s = np.r_[norm_scores, a_scores]
    auc = roc_auc_score(y, s)
    # TPR achievable at fixed benign FPR operating points (move the threshold).
    def _tpr_at_fpr(target: float) -> float:
        thr = np.quantile(norm_scores, 1 - target)  # score cutoff giving `target` FPR
        return float((a_scores >= thr).mean())
    print(f"\nROC-AUC (normal vs attack): {auc:.3f}   "
          f"(0.5 = embedding cannot separate; >0.8 = separable)")
    print(f"TPR @ FPR=0.05: {_tpr_at_fpr(0.05):.3f}    "
          f"TPR @ FPR=0.10: {_tpr_at_fpr(0.10):.3f}")

    # Aggregate F1 (treat all attack traces as positives, held-out normal as neg).
    n_norm = len(Xte_normal)
    fp = int(round(fpr * n_norm)); tn = n_norm - fp
    prec = all_tp / (all_tp + fp) if (all_tp + fp) else 0.0
    rec = all_tp / (all_tp + all_fn) if (all_tp + all_fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    print(f"\nAggregate: precision={prec:.3f}  recall(TPR)={rec:.3f}  "
          f"F1={f1:.3f}   mean per-type TPR={sum(tprs)/len(tprs):.3f}")
    print("Paper 3 reported F1 range: 0.78-0.99")


if __name__ == "__main__":
    main()
