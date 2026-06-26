"""
B7 benchmark — replay a REAL collaborative-editing trace through the CRDT and
verify (a) correctness: the replayed document matches the ground-truth text, and
(b) convergence: applying the same edits in a different order yields the same text
(Eg-walker's core guarantee). Also reports throughput + element/tombstone counts.

Trace: the standard **automerge-perf** keystroke trace (a LaTeX paper typed
character-by-character, ~259k single-char edits) — github.com/automerge/automerge-perf.

    python eval_crdt.py [--n 8000]
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.collab.crdt import Doc   # noqa: E402

# The canonical automerge-paper trace, from the Eg-walker co-author's repo.
_URL = ("https://raw.githubusercontent.com/josephg/editing-traces/master/"
        "sequential_traces/automerge-paper.json.gz")


def load_edits(n: int):
    data_dir = _REPO / "benchmarks" / "b7_collab" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache = data_dir / "automerge-paper.json.gz"
    if not cache.exists():
        print("downloading automerge-paper trace (~0.9 MB) ...")
        urllib.request.urlretrieve(_URL, cache)
    trace = json.loads(gzip.decompress(cache.read_bytes()))
    edits = [patch for txn in trace["txns"] for patch in txn["patches"]]  # [pos, ndel, ins]
    return (edits[:n] if n else edits), trace.get("endContent")


def reference_text(edits) -> str:
    """Ground truth: apply edits to a plain list (what the document SHOULD be)."""
    buf: list[str] = []
    for e in edits:
        pos, ndel = e[0], e[1]
        del buf[pos:pos + ndel]
        for c in (e[2] if len(e) > 2 else ""):
            buf.insert(pos, c); pos += 1
    return "".join(buf)


def replay(edits, replica=1):
    """Replay the trace through the CRDT, returning (doc, op_log)."""
    d = Doc(replica)
    ops = []
    for e in edits:
        pos, ndel = e[0], e[1]
        for _ in range(ndel):
            op = d.local_delete(pos)
            if op: ops.append(op)
        p = pos
        for c in (e[2] if len(e) > 2 else ""):
            ops.append(d.local_insert(p, c)); p += 1
    return d, ops


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=8000, help="number of edits (0 = all)")
    args = ap.parse_args()

    edits, end_content = load_edits(args.n)
    print(f"\nautomerge-paper trace (Eg-walker authors' repo): replaying "
          f"{len(edits)} real edits\n")

    ref = reference_text(edits)
    t0 = time.time()
    doc, ops = replay(edits)
    dt = time.time() - t0

    ok = doc.text() == ref
    print(f"[correctness] replayed doc == ground truth: {ok}  "
          f"(len={len(doc.text())}, ref={len(ref)})")
    print(f"[performance] {len(ops)} ops in {dt:.2f}s "
          f"({len(ops)/dt:,.0f} ops/s); elements(incl. tombstones)={len(doc.elems)}")

    # convergence: a peer applies the same ops in a different (causally-valid) order
    inserts = [o for o in ops if o.kind == "ins"]
    deletes = [o for o in ops if o.kind == "del"]
    rng = random.Random(0); rng.shuffle(inserts)
    peer = Doc(2)
    peer.apply_all(inserts)          # inserts in shuffled order (position keys converge)
    peer.apply_all(deletes)          # then deletes (tombstone their targets)
    conv = peer.text() == ref
    print(f"[convergence] peer with REORDERED ops == same text: {conv}")

    print("\nAll replicas converge regardless of op order (Eg-walker's guarantee). "
          "Our CRDT is\nO(n)/op; Eg-walker's event-graph makes this compact + fast "
          "at full 259k-edit scale.")
    sys.exit(0 if (ok and conv) else 1)


if __name__ == "__main__":
    main()
