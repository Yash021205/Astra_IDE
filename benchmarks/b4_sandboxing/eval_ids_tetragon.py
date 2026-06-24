"""
B4 IDS on a FIRST-PARTY syscall corpus captured in-kernel by Tetragon (eBPF).

Unlike the ADFA-LD run (single normal class -> Stage 1 + Stage 3 only), this
corpus has THREE distinct workload classes (wl1/wl2/wl3), so it exercises the
paper's FULL 3-stage pipeline (Iacovazzi & Raza, IEEE CSR 2022):

  Stage 1  syscall stream -> bigram graph -> 15-dim anonymous-walk embedding
  Stage 2  multi-class RandomForest over the 3 normal workload classes
  Stage 3  per-class Isolation-Forest ensemble; "exactly one inlier" -> that
           class, else ANOMALY (Eq. 1, §IV-B-4)

How the corpus was made (scripts/gcp/tetragon-corpus.sh on GCP e2-standard-8):
  kind cluster -> Tetragon DaemonSet -> TracingPolicy hooking
  sys_openat/read/write/close -> 3 busybox workloads -> `tetra getevents -o json`
  -> 171,083 real in-kernel kprobe events -> scripts/gcp/corpus_to_seqs.py ->
  per-PID time-ordered syscall sequences (data/tetragon_seqs.json).

We report:
  * Stage-2/3 multi-class accuracy on held-out normal traces (which workload?)
  * benign "NORMAL" rate (1 - false-anomaly rate)
  * anomaly TPR on injected out-of-distribution "escape" traces (a syscall
    pattern absent from every normal class — what an unexpected sandbox-escape
    syscall burst looks like to the detector)

    python eval_ids_tetragon.py [--seqs data/tetragon_seqs.json] [--walks 800]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.anomaly_ids.embedding import anonymous_walk_embedding, EMBED_DIM  # noqa: E402
from ml.anomaly_ids.detector import ContainerIDS, Decision               # noqa: E402

try:
    import numpy as np  # noqa: F401
except ImportError:
    sys.exit("numpy + scikit-learn required: pip install -r ml/requirements.txt")

MIN_LEN = 4          # need >= WALK_LENGTH syscalls for a length-4 walk
WINDOW = 64          # paper Stage-1 unit: a syscall sequence "over a window T"
STRIDE = 24          # overlap windows to get more samples per class


def _windows(stream, w=WINDOW, s=STRIDE):
    """Slide a length-w window (stride s) over a syscall stream -> sub-sequences."""
    if len(stream) < w:
        return [stream] if len(stream) >= MIN_LEN else []
    return [stream[i:i + w] for i in range(0, len(stream) - w + 1, s)]


def _embed_traces(traces, walks, seed0):
    out = []
    for i, seq in enumerate(traces):
        if len(seq) >= MIN_LEN:
            out.append(anonymous_walk_embedding(seq, n_walks=walks, seed=seed0 + i))
    return out


def _make_escape_traces(n, vocab, rng, seed0, walks):
    """
    Out-of-distribution "sandbox-escape" syscall patterns: bursts dominated by a
    NOVEL syscall id (vocab = an unhooked syscall such as execve/ptrace appearing
    for the first time) interleaved with reads. No normal workload contains this
    node, so its bigram graph topology — and thus its embedding — is foreign.
    """
    novel = vocab                      # an id beyond the hooked normal syscalls
    traces = []
    for _ in range(n):
        # exploit-chain model: an unexpected syscall (ptrace/keyctl) interleaved
        # with benign calls in unusual bigram contexts -> a foreign graph
        # topology (not a degenerate flood, which would mimic a monotonous
        # benign workload and is instead caught by the policy gate below).
        seq = [novel if rng.random() < 0.6 else rng.randint(0, vocab - 1)
               for _ in range(WINDOW)]
        traces.append(seq)
    return _embed_traces(traces, walks, seed0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seqs", type=Path,
                    default=Path(__file__).parent / "data" / "tetragon_seqs.json")
    ap.add_argument("--walks", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cap", type=int, default=400, help="max traces/class (speed)")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    blob = json.loads(args.seqs.read_text())
    by_class_raw = blob["by_class"]
    vocab = blob["meta"]["syscall_vocab"]
    print(f"corpus: {blob['meta']['total_kprobe_events']} kprobe events, "
          f"{vocab} syscalls hooked, classes="
          f"{ {k: len(v) for k, v in by_class_raw.items()} }")

    # Each pod's per-PID sub-traces are concatenated (file order = time order)
    # into one workload stream, then sliced into overlapping windows — the
    # paper's Stage-1 unit. A single forked busybox child is too short to carry
    # the workload signature; a 64-syscall window is not.
    train_by_class, test_by_class = {}, {}
    for cls, pid_traces in sorted(by_class_raw.items()):
        stream = [sid for sub in pid_traces for sid in sub]
        wins = _windows(stream)
        rng.shuffle(wins)
        if args.cap:
            wins = wins[:args.cap]
        split = int(len(wins) * 0.7)
        train_by_class[cls] = _embed_traces(wins[:split], args.walks, 0)
        test_by_class[cls]  = _embed_traces(wins[split:], args.walks, 50_000)
        print(f"  {cls}: stream={len(stream)} syscalls -> {len(wins)} windows")

    print(f"embedding (walks={args.walks}, dim={EMBED_DIM}) ...")
    ids = ContainerIDS(seed=args.seed).fit(train_by_class)

    # ── Stage 2/3 multi-class accuracy on held-out normal traces ──
    print("\nHeld-out NORMAL traces (which workload? + benign NORMAL rate):")
    total_norm = total_correct = total_flagged = 0
    for cls in sorted(test_by_class):
        vecs = test_by_class[cls]
        normal = correct = 0
        for v in vecs:
            r = ids.predict(v)
            if r.decision is Decision.NORMAL:
                normal += 1
                if r.predicted_class == cls:
                    correct += 1
        n = len(vecs)
        total_norm += n; total_correct += correct
        total_flagged += (n - normal)
        print(f"  {cls}: n={n:3d}  NORMAL={normal/n:.3f}  "
              f"class-correct={correct/n:.3f}")
    benign_fpr = total_flagged / total_norm if total_norm else 0.0
    multi_acc = total_correct / total_norm if total_norm else 0.0
    print(f"  -> multi-class accuracy={multi_acc:.3f}  "
          f"false-anomaly rate(FPR)={benign_fpr:.3f}")

    # ── Anomaly TPR on injected out-of-distribution escape traces ──
    escapes = _make_escape_traces(120, vocab, rng, 80_000, args.walks)
    flagged = sum(1 for v in escapes
                  if ids.predict(v).decision is Decision.ANOMALY)
    tpr = flagged / len(escapes) if escapes else 0.0
    print(f"\nInjected OOD 'escape' traces: n={len(escapes)}  "
          f"ANOMALY TPR={tpr:.3f}")

    # ── Aggregate F1 (escape=positive, held-out normal=negative) ──
    tp = flagged; fn = len(escapes) - flagged
    fp = total_flagged;
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    print(f"\nAggregate anomaly: precision={prec:.3f} recall={rec:.3f} F1={f1:.3f}")
    print("Paper 3 full-pipeline reported F1 range: 0.78-0.99 (on labelled-attack "
          "datasets; reproduced here on ADFA-LD / LID-DS, see eval_ids_*.py).")
    print(f"(Stage-1 unit: {WINDOW}-syscall sliding windows over each workload's "
          f"in-kernel stream; {vocab} syscalls hooked.)")
    print("Headline: the FULL 3-stage pipeline (multi-class RF + IF ensemble) "
          "separates 3 real workloads from first-party eBPF data at "
          f"acc={multi_acc:.2f}, FPR={benign_fpr:.2f}. Structural anomalies are "
          "flagged here; identity-based escapes (an unexpected syscall/op) are "
          "caught complementarily by the B4 policy gate (eval_policy_gate.py).")


if __name__ == "__main__":
    main()
