# B7 Collaborative Editing (CRDT) — Benchmark Evaluation

Reproduces the **convergence guarantee** of Eg-walker (Kleppmann et al.,
*Collaborative Text Editing with Eg-walker: Better, Faster, Smaller*, EuroSys'25)
— all replicas converge to the same text regardless of operation order — on the
**real automerge-paper editing trace** (a LaTeX paper typed character-by-character).

## Data — the Eg-walker authors' own trace
`automerge-paper.json.gz` from **josephg/editing-traces** (Joseph Gentle, an
Eg-walker co-author). It's the canonical sequential trace the paper itself uses.
Downloaded automatically (~0.9 MB, gitignored).

## Reproduce
```bash
python eval_crdt.py --n 8000      # or --n 0 for the full trace
```

## Results (8000 real edits)
```
  [correctness]  replayed doc == ground truth : True   (len 5386)
  [performance]  8000 ops in 1.11s (7,180 ops/s); elements incl. tombstones = 6693
  [convergence]  peer with REORDERED ops == same text : True
```

- **Correctness:** replaying the real keystroke trace through the CRDT yields
  *exactly* the ground-truth document.
- **Convergence (the Eg-walker guarantee):** a second replica applying the same
  operations in a **shuffled order** ends with the identical text.

The unit tests (`ml/collab/test_crdt.py`) additionally prove convergence for
**concurrent** edits — two replicas inserting at the same position, and concurrent
insert+delete — both converge.

## How it works / honest scope
- `ml/collab/crdt.py` is a **dense position-identifier sequence CRDT** (the
  Logoot/LSEQ family that Yjs, Automerge, and Eg-walker all build on): each
  inserted character gets an immutable, totally-ordered position key, so applying
  ops in any order yields the same document; deletes are tombstones.
- Our implementation is **O(n) per op** (a sorted-list insert). **Eg-walker's
  contribution is exactly making this fast and compact at full scale** (259k edits,
  orders-of-magnitude less steady-state memory via its event-graph + internal-state
  walking) — we reproduce the *guarantee* and verify it on real data; the
  full-scale performance optimization is the paper's advanced algorithm.
- ASTRA's frontend uses **Yjs + Monaco** in production (a battle-tested CRDT); this
  module is the algorithmic reproduction for the thesis.
