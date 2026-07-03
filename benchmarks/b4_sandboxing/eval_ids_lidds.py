"""
B4 IDS benchmark — FULL Paper 3 pipeline on LID-DS-2021, with a rich multi-scale
graph embedding and head-to-head baselines.

Paper 3 (Iacovazzi & Raza, IEEE CSR 2022) reports F1 0.78-0.99 on CloudSuite,
where distinct WORKLOADS are separable and a Stage-2 multi-class RandomForest
exploits that. LID-DS-2021 gives the same structure: each scenario is a different
containerised application, so **scenarios map to Paper 3's normal workload
classes** and we run the complete 3-stage `ml/anomaly_ids.ContainerIDS`.

Improvements over the plain length-4 embedding (the accuracy lever for subtle
memory-disclosure CVEs like Heartbleed, whose syscall structure barely differs
from normal):
  * `rich_embedding` — anonymous-walk distributions at lengths {3,4,5} (72 dims)
    + 8 graph statistics = 80-dim feature;
  * per-recording MAX-pool of a continuous window anomaly score, so a short attack
    burst inside a long normal recording is not averaged away;
  * best-F1 operating point chosen on the scores (+ ROC-AUC as the threshold-free
    measure), reported next to two standard baselines:
      - STIDE (Forrest et al.): normal k-gram database, window score = mismatch rate;
      - Frequency + IsolationForest: hashed syscall-frequency vector per window.

    python eval_ids_lidds.py --root data/lid-ds-2021/_extracted \
        [--cap 120 --walks 120 --window 350] \
        [--save-artifact ml/anomaly_ids/artifacts/ids.joblib \
         --metrics-out ml/anomaly_ids/artifacts/metrics.json]
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.anomaly_ids.embedding import rich_embedding, RICH_LENGTHS  # noqa: E402
from ml.anomaly_ids.detector import ContainerIDS, Decision          # noqa: E402

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import roc_auc_score
except ImportError:
    sys.exit("numpy + scikit-learn required: pip install -r ml/requirements.txt")


# ── LID-DS trace parsing ─────────────────────────────────────────────────────

def _syscalls(lines, vocab: dict, maxlen: int) -> list[int]:
    seq = []
    for line in lines:
        p = line.split()
        if len(p) >= 7 and p[6] == ">":          # enter event; p[5] = syscall name
            seq.append(vocab.setdefault(p[5], len(vocab) + 1))
            if maxlen and len(seq) >= maxlen:
                break
    return seq


def _read_recording(path: Path, vocab: dict, maxlen: int) -> list[int]:
    if path.suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as zf:
                sc = [n for n in zf.namelist() if n.endswith(".sc")]
                if not sc:
                    return []
                with zf.open(sc[0]) as f:
                    return _syscalls(io.TextIOWrapper(f, errors="replace"), vocab, maxlen)
        except (zipfile.BadZipFile, OSError):
            return []
    sc = list(path.glob("*.sc"))
    if not sc:
        return []
    with open(sc[0], errors="replace") as f:
        return _syscalls(f, vocab, maxlen)


def _windows(seq: list[int], size: int, stride: int, maxwin: int) -> list[list[int]]:
    """Slide a length-`size` window over the syscall stream (paper §III: the graph
    is built per window T). Cap to `maxwin` windows spread evenly across the WHOLE
    trace so a late attack burst is still covered. size<=0 => whole-trace mode."""
    if size <= 0 or len(seq) <= size:
        return [seq] if len(seq) >= 2 else []
    starts = list(range(0, len(seq) - size + 1, stride))
    if maxwin and len(starts) > maxwin:
        idx = sorted(set(np.linspace(0, len(starts) - 1, maxwin).round().astype(int)))
        starts = [starts[i] for i in idx]
    return [seq[s:s + size] for s in starts]


def _recordings(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if p.suffix == ".zip":
            out.append(p)
        elif p.is_dir() and any(p.glob("*.sc")):
            out.append(p)
    return out


# ── Raw windows (shared by our IDS and the baselines) ────────────────────────

def _raw_windows_per_rec(recs, vocab, win, stride, maxlen, maxwin):
    """Per recording -> list of raw syscall-id windows."""
    out = []
    for r in recs:
        seq = _read_recording(r, vocab, maxlen)
        w = _windows(seq, win, stride, maxwin)
        if w:
            out.append(w)
    return out


def _embed_windows(raw_per_rec, walks, seed0):
    """Embed each window with the rich multi-scale embedding, keeping per-rec grouping."""
    out = []
    for i, rec in enumerate(raw_per_rec):
        out.append([rich_embedding(w, n_walks=walks, seed=seed0 + i * 31 + j)
                    for j, w in enumerate(rec)])
    return out


# ── Scoring: continuous per-recording score + best-F1 operating point ────────

def _best_f1(norm_scores: np.ndarray, atk_scores: np.ndarray) -> dict:
    """Sweep the decision threshold; return metrics at the max-F1 operating point."""
    all_s = np.unique(np.r_[norm_scores, atk_scores])
    best = {"f1": -1.0}
    for thr in all_s:
        tp = int((atk_scores > thr).sum()); fn = int((atk_scores <= thr).sum())
        fp = int((norm_scores > thr).sum()); tn = int((norm_scores <= thr).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best["f1"]:
            best = {"f1": f1, "precision": prec, "recall": rec,
                    "fpr": fp / (fp + tn) if (fp + tn) else 0.0, "threshold": float(thr)}
    y = np.r_[np.zeros(len(norm_scores)), np.ones(len(atk_scores))]
    s = np.r_[norm_scores, atk_scores]
    try:
        best["roc_auc"] = float(roc_auc_score(y, s))
    except Exception:
        best["roc_auc"] = float("nan")
    return best


def _ids_rec_scores(ids: ContainerIDS, emb_per_rec, pct: int = 90) -> np.ndarray:
    """Recording score = a high percentile of per-window anomaly scores, where a
    window's score is how anomalous the RF-PREDICTED class's Isolation Forest finds
    it (paper §IV-B: Stage-2 RF routes to the matching Stage-3 detector). Using the
    routed class (not min-over-all) avoids the false spikes a wrong class produces;
    a high percentile (not max) is robust to a single noisy window."""
    out = []
    for rec in emb_per_rec:
        if not rec:
            out.append(0.0); continue
        ws = []
        for v in rec:
            r = ids.predict(v)
            ws.append(r.class_scores.get(r.rf_class, max(r.class_scores.values())))
        out.append(float(np.percentile(ws, pct)))
    return np.asarray(out, dtype=float)


def _stide_rec_scores(train_norm_raw, test_raw_per_rec, k: int = 5) -> np.ndarray:
    """STIDE baseline: build the normal k-gram set; window score = fraction of its
    k-grams NOT seen in normal; recording = max window mismatch."""
    db = set()
    for w in train_norm_raw:
        for i in range(len(w) - k + 1):
            db.add(tuple(w[i:i + k]))

    def win_mismatch(w):
        grams = [tuple(w[i:i + k]) for i in range(len(w) - k + 1)]
        return sum(1 for g in grams if g not in db) / len(grams) if grams else 0.0

    return np.asarray([max((win_mismatch(w) for w in rec), default=0.0)
                       for rec in test_raw_per_rec], dtype=float)


def _freq_vec(w, buckets: int = 64):
    v = np.zeros(buckets)
    for s in w:
        v[s % buckets] += 1.0
    tot = v.sum() or 1.0
    return v / tot


def _freqif_rec_scores(train_norm_raw, test_raw_per_rec, seed: int) -> np.ndarray:
    """Frequency+IsolationForest baseline: hashed syscall-frequency vector per window."""
    X = np.asarray([_freq_vec(w) for w in train_norm_raw])
    iso = IsolationForest(n_estimators=100, contamination=0.025, random_state=seed).fit(X)

    def rec_score(rec):
        if not rec:
            return 0.0
        s = -iso.decision_function(np.asarray([_freq_vec(w) for w in rec]))
        return float(s.max())

    return np.asarray([rec_score(rec) for rec in test_raw_per_rec], dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--cap", type=int, default=120, help="max recordings per split")
    ap.add_argument("--walks", type=int, default=120)
    ap.add_argument("--maxlen", type=int, default=8000)
    ap.add_argument("--window", type=int, default=350)
    ap.add_argument("--stride", type=int, default=175)
    ap.add_argument("--maxwin", type=int, default=8)
    ap.add_argument("--stide-k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--save-artifact", type=Path, default=None)
    ap.add_argument("--metrics-out", type=Path, default=None)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    vocab: dict = {}

    scenarios = sorted(p for p in args.root.iterdir()
                       if p.is_dir() and (p / "training").is_dir())
    if len(scenarios) < 2:
        sys.exit(f"Need >=2 scenarios under {args.root}; found {len(scenarios)}.")
    print(f"scenarios (workload classes): {[s.name for s in scenarios]}")
    print(f"rich embedding: walk-lengths {RICH_LENGTHS} + 8 graph stats  |  "
          f"window={args.window} stride={args.stride} maxwin={args.maxwin} walks={args.walks}")

    def _sample(folder: Path) -> list[Path]:
        recs = _recordings(folder)
        rng.shuffle(recs)
        return recs[:args.cap] if args.cap else recs

    W = dict(win=args.window, stride=args.stride, maxlen=args.maxlen, maxwin=args.maxwin)

    # Collect raw windows (for baselines) + embed (for our IDS), per split.
    by_class_emb, train_norm_raw = {}, []
    testnormal_raw, attack_raw = [], []
    for s in scenarios:
        normal = _sample(s / "training") + _sample(s / "validation")
        print(f"  {s.name}: windowing {len(normal)} normal recordings ...")
        norm_raw = _raw_windows_per_rec(normal, vocab, **W)
        flat = [w for rec in norm_raw for w in rec]
        train_norm_raw.extend(flat)
        by_class_emb[s.name] = np.asarray(
            [rich_embedding(w, n_walks=args.walks, seed=i)
             for i, w in enumerate(flat)], dtype=float)
        testnormal_raw += _raw_windows_per_rec(_sample(s / "test" / "normal"), vocab, **W)
        attack_raw += _raw_windows_per_rec(_sample(s / "test" / "normal_and_attack"), vocab, **W)

    print(f"syscall vocab={len(vocab)}  train windows/class="
          f"{ {k: len(v) for k, v in by_class_emb.items()} }  "
          f"test-normal recs={len(testnormal_raw)}  attack recs={len(attack_raw)}")

    # ── Our method: 3-stage ContainerIDS on the rich embedding ───────────────
    ids = ContainerIDS(seed=args.seed).fit(by_class_emb)
    tn_emb = _embed_windows(testnormal_raw, args.walks, seed0=500_000)
    at_emb = _embed_windows(attack_raw, args.walks, seed0=900_000)
    ids_norm = _ids_rec_scores(ids, tn_emb)
    ids_atk = _ids_rec_scores(ids, at_emb)
    ours = _best_f1(ids_norm, ids_atk)

    # ── Baselines ────────────────────────────────────────────────────────────
    stide = _best_f1(_stide_rec_scores(train_norm_raw, testnormal_raw, args.stide_k),
                     _stide_rec_scores(train_norm_raw, attack_raw, args.stide_k))
    freqif = _best_f1(_freqif_rec_scores(train_norm_raw, testnormal_raw, args.seed),
                      _freqif_rec_scores(train_norm_raw, attack_raw, args.seed))

    def _row(name, m):
        print(f"  {name:22} F1={m['f1']:.3f}  P={m['precision']:.3f}  "
              f"R={m['recall']:.3f}  FPR={m['fpr']:.3f}  AUC={m['roc_auc']:.3f}")

    print("\nMethod comparison (best-F1 operating point; paper F1 0.78-0.99, FPR 0.024-0.071):")
    _row("ASTRA rich-graph IDS", ours)
    _row("STIDE (k-gram)", stide)
    _row("Frequency + IForest", freqif)
    best_other = max(stide["f1"], freqif["f1"])
    print(f"\nASTRA IDS F1 {ours['f1']:.3f} vs best baseline {best_other:.3f} "
          f"(+{ours['f1'] - best_other:+.3f})   ROC-AUC {ours['roc_auc']:.3f}")

    # ── Persist artifact + metrics ───────────────────────────────────────────
    if args.save_artifact:
        args.save_artifact.parent.mkdir(parents=True, exist_ok=True)
        ids.embed_config = {"kind": "rich", "lengths": list(RICH_LENGTHS),
                            "walks": args.walks, "window": args.window,
                            "stride": args.stride, "maxwin": args.maxwin}
        ids.save(str(args.save_artifact))
        print(f"\nsaved fitted IDS -> {args.save_artifact}")
    if args.metrics_out:
        metrics = {
            "dataset": "LID-DS-2021",
            "scenarios": [s.name for s in scenarios],
            "vocab_size": len(vocab),
            "embedding": {"kind": "rich-multiscale-graph",
                          "walk_lengths": list(RICH_LENGTHS), "dim": 80,
                          "walks": args.walks, "window": args.window},
            "astra_ids": {k: (None if ours[k] != ours[k] else round(ours[k], 4)) for k in ours},
            "baselines": {
                "stide": {k: (None if stide[k] != stide[k] else round(stide[k], 4)) for k in stide},
                "frequency_iforest": {k: (None if freqif[k] != freqif[k] else round(freqif[k], 4))
                                      for k in freqif},
            },
            "astra_vs_best_baseline_f1_gain": round(ours["f1"] - best_other, 4),
            "paper_reference": {"source": "Iacovazzi & Raza, IEEE CSR 2022",
                                "f1_range": [0.78, 0.99], "fpr_range": [0.024, 0.071]},
        }
        args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_out.write_text(json.dumps(metrics, indent=2))
        print(f"wrote metrics -> {args.metrics_out}")


if __name__ == "__main__":
    main()
