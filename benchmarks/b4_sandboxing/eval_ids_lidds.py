"""
B4 IDS benchmark — FULL Paper 3 pipeline on LID-DS-2021 (the multi-class setting).

Paper 3 (Iacovazzi & Raza, IEEE CSR 2022) reports F1 0.78-0.99 on CloudSuite,
where several distinct WORKLOADS are highly separable and a Stage-2 multi-class
RandomForest exploits that separability. LID-DS-2021 gives the same structure:
each scenario is a different containerised application, so **scenarios map to
Paper 3's normal workload classes**. This harness therefore runs the *complete*
3-stage `ml/anomaly_ids.ContainerIDS` (anonymous-walk embedding → RF over
scenarios → ensemble of Isolation Forests), unlike the ADFA-LD run which is
single-workload.

LID-DS-2021 layout per scenario:
  <scenario>/training/<rec>.zip              normal
  <scenario>/validation/<rec>.zip            normal
  <scenario>/test/normal/<rec>.zip           normal  (held-out -> FPR)
  <scenario>/test/normal_and_attack/<rec>.zip attack (-> TPR)
Each recording holds a <name>.sc sysdig trace; we take the syscall name on every
enter ('>') event as the sequence. Recordings may be a .zip or a pre-extracted
dir — both are handled.

    python eval_ids_lidds.py --root data/lid-ds-2021/_extracted [--cap 200 --walks 300]
"""
from __future__ import annotations

import argparse
import io
import random
import sys
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.anomaly_ids.embedding import anonymous_walk_embedding  # noqa: E402
from ml.anomaly_ids.detector import ContainerIDS, Decision      # noqa: E402

try:
    import numpy as np
except ImportError:
    sys.exit("numpy + scikit-learn required: pip install -r ml/requirements.txt")


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
    """Slide a length-`size` window over the syscall stream (paper §III: the
    graph/embedding is built per window T, not over the whole trace — this is
    what localises a short attack burst inside a long normal recording).
    When capping to `maxwin`, spread the windows evenly across the WHOLE trace
    so a late attack burst is still covered (not just the front).
    `size <= 0` means whole-trace mode: one window per recording."""
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


def _train_windows(recs, vocab, walks, win, stride, maxlen, maxwin, seed0):
    """Flatten all normal windows -> training embeddings for one class."""
    vecs = []
    for i, r in enumerate(recs):
        seq = _read_recording(r, vocab, maxlen)
        for j, w in enumerate(_windows(seq, win, stride, maxwin)):
            vecs.append(anonymous_walk_embedding(w, n_walks=walks, seed=seed0 + i * 31 + j))
    return np.asarray(vecs, dtype=float)


def _recording_window_embs(recs, vocab, walks, win, stride, maxlen, maxwin, seed0):
    """Keep windows grouped per recording (for recording-level scoring)."""
    per_rec = []
    for i, r in enumerate(recs):
        seq = _read_recording(r, vocab, maxlen)
        wins = [anonymous_walk_embedding(w, n_walks=walks, seed=seed0 + i * 31 + j)
                for j, w in enumerate(_windows(seq, win, stride, maxwin))]
        if wins:
            per_rec.append(np.asarray(wins, dtype=float))
    return per_rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path,
                    help="dir containing the extracted <scenario>/ folders")
    ap.add_argument("--cap", type=int, default=150, help="max recordings per split")
    ap.add_argument("--walks", type=int, default=300)
    ap.add_argument("--maxlen", type=int, default=6000, help="syscalls read/trace")
    ap.add_argument("--window", type=int, default=500, help="syscalls per window")
    ap.add_argument("--stride", type=int, default=250)
    ap.add_argument("--maxwin", type=int, default=8, help="max windows per recording")
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="flag recording if frac-anomalous-windows > this (0 = any)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    vocab: dict = {}

    scenarios = sorted(p for p in args.root.iterdir()
                       if p.is_dir() and (p / "training").is_dir())
    if len(scenarios) < 2:
        sys.exit(f"Need >=2 scenarios (workload classes) under {args.root}; "
                 f"found {len(scenarios)}.")
    print(f"scenarios (workload classes): {[s.name for s in scenarios]}")
    print(f"windowed: window={args.window} stride={args.stride} maxwin={args.maxwin}")

    def _sample(folder: Path) -> list[Path]:
        recs = _recordings(folder)
        rng.shuffle(recs)
        return recs[:args.cap] if args.cap else recs

    W = dict(walks=args.walks, win=args.window, stride=args.stride,
             maxlen=args.maxlen, maxwin=args.maxwin)
    by_class, testnormal, attack = {}, {}, {}
    for s in scenarios:
        normal = _sample(s / "training") + _sample(s / "validation")
        print(f"  {s.name}: windowing {len(normal)} normal recordings ...")
        by_class[s.name] = _train_windows(normal, vocab, seed0=0, **W)
        testnormal[s.name] = _recording_window_embs(
            _sample(s / "test" / "normal"), vocab, seed0=50_000, **W)
        attack[s.name] = _recording_window_embs(
            _sample(s / "test" / "normal_and_attack"), vocab, seed0=90_000, **W)
    print(f"syscall vocabulary size: {len(vocab)}   "
          f"train windows/class: { {k: len(v) for k, v in by_class.items()} }")

    ids = ContainerIDS(seed=args.seed).fit(by_class)

    def _rec_score(rec_windows) -> float:
        """Recording anomaly score = fraction of its windows flagged ANOMALY."""
        n = len(rec_windows)
        if n == 0:
            return 0.0
        return sum(1 for v in rec_windows
                   if ids.predict(v).decision is Decision.ANOMALY) / n

    # Operating point: flag a recording if its fraction of anomalous windows
    # exceeds --threshold (0.5 = majority; for whole-trace --window 0 the score
    # is 0/1 so this is the direct per-recording decision). ROC-AUC is also
    # reported as the threshold-INDEPENDENT measure of separability.
    norm_scores = np.array([_rec_score(r) for s in scenarios for r in testnormal[s.name]])
    atk_scores = {s.name: np.array([_rec_score(r) for r in attack[s.name]])
                  for s in scenarios}
    thr = args.threshold
    fpr_all = float((norm_scores > thr).mean())

    print(f"\nOperating point: frac-anomalous-windows > {thr}")
    print("Per-scenario TPR on attack recordings:")
    tp = fn = 0
    for s in scenarios:
        a = atk_scores[s.name]
        tpr = float((a > thr).mean()) if len(a) else 0.0
        tp += int((a > thr).sum()); fn += int((a <= thr).sum())
        print(f"  {s.name:22} TPR={tpr:.3f}  (n={len(a)})")

    fp = int((norm_scores > thr).sum()); tn = int((norm_scores <= thr).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    all_atk = np.concatenate(list(atk_scores.values()))
    y = np.r_[np.zeros(len(norm_scores)), np.ones(len(all_atk))]
    sc = np.r_[norm_scores, all_atk]
    try:
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y, sc)
    except Exception:
        auc = float("nan")
    print(f"\nAggregate: precision={prec:.3f}  recall(TPR)={rec:.3f}  F1={f1:.3f}  "
          f"FPR={fpr_all:.3f}  ROC-AUC={auc:.3f}")
    print("Paper 3 reported: F1 0.78-0.99, FPR 0.024-0.071")


if __name__ == "__main__":
    main()
