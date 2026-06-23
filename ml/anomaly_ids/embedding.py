"""
Stage 1 — graph representation + anonymous-walk embedding (paper §III-C, §IV-B-1).

A sequence of syscall IDs over a window T is turned into a weighted directed
graph where edge (v_i, v_j) weight = count of the bigram (v_i, v_j). We then
embed the graph as the probability distribution over all anonymous walks of
length L (Ivanov & Burnaev). The paper uses L=4, which yields exactly
15 features (Bell number B4 = 15).
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

WALK_LENGTH = 4          # paper: anonymous walks of length 4
N_WALKS     = 1000       # random walks sampled per graph to estimate the distribution


def generate_anonymous_walks(length: int) -> List[Tuple[int, ...]]:
    """
    All valid anonymous walks of a given length = restricted growth strings
    starting at 1 (a[0]=1, a[i] <= max(a[:i])+1). Count = Bell number B_length.
    For length 4 this returns 15 patterns.
    """
    results: List[Tuple[int, ...]] = []

    def rec(seq: List[int], cur_max: int):
        if len(seq) == length:
            results.append(tuple(seq))
            return
        for nxt in range(1, cur_max + 2):       # 1..max+1 (RGS rule)
            seq.append(nxt)
            rec(seq, max(cur_max, nxt))
            seq.pop()

    rec([1], 1)
    return results


# Precompute the length-4 anonymous-walk vocabulary (15 patterns) and an index.
_ANON_WALKS = generate_anonymous_walks(WALK_LENGTH)
_ANON_INDEX: Dict[Tuple[int, ...], int] = {w: i for i, w in enumerate(_ANON_WALKS)}
EMBED_DIM = len(_ANON_WALKS)                    # == 15 for length 4


def build_syscall_graph(seq: Sequence[int]) -> Dict[int, Dict[int, int]]:
    """
    Bigram-weighted directed graph: adj[v_i][v_j] = #occurrences of bigram
    (v_i -> v_j) in the syscall-ID sequence (paper §IV-B-1).
    """
    adj: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for a, b in zip(seq, seq[1:]):
        adj[a][b] += 1
    return adj


def _anonymize(walk: Sequence[int]) -> Tuple[int, ...]:
    """Map a node walk to its anonymous form (index of first occurrence)."""
    seen: Dict[int, int] = {}
    out: List[int] = []
    for node in walk:
        if node not in seen:
            seen[node] = len(seen) + 1
        out.append(seen[node])
    return tuple(out)


def anonymous_walk_embedding(
    seq: Sequence[int],
    length: int = WALK_LENGTH,
    n_walks: int = N_WALKS,
    seed: int = 0,
) -> List[float]:
    """
    Estimate the distribution over anonymous walks of `length` by sampling
    `n_walks` random walks weighted by edge counts. Returns a 15-dim vector
    (for length 4) that sums to 1 (or all-zeros for an empty/degenerate graph).
    """
    adj = build_syscall_graph(seq)
    nodes = list(adj.keys())
    counts = [0] * EMBED_DIM
    if not nodes:
        return [0.0] * EMBED_DIM

    rng = random.Random(seed)
    # Precompute weighted out-neighbours per node
    out_lists: Dict[int, Tuple[List[int], List[int]]] = {}
    for v, nbrs in adj.items():
        out_lists[v] = (list(nbrs.keys()), list(nbrs.values()))

    total = 0
    for _ in range(n_walks):
        start = rng.choice(nodes)
        walk = [start]
        cur = start
        for _ in range(length - 1):
            nb = out_lists.get(cur)
            if not nb or not nb[0]:
                break                            # dead end — drop short walk
            cur = rng.choices(nb[0], weights=nb[1], k=1)[0]
            walk.append(cur)
        if len(walk) != length:
            continue
        idx = _ANON_INDEX.get(_anonymize(walk))
        if idx is not None:
            counts[idx] += 1
            total += 1

    if total == 0:
        return [0.0] * EMBED_DIM
    return [c / total for c in counts]
