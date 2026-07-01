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


# ── Per-length anonymous-walk vocabularies (built + cached on first use) ──────
# NOTE: previously the module hardcoded the length-4 vocabulary, so passing
# length != 4 to anonymous_walk_embedding silently produced an all-zero vector.
# We now key the vocabulary by length so multi-scale embeddings work correctly.
_WALK_VOCAB: Dict[int, Dict[Tuple[int, ...], int]] = {}


def _walk_index(length: int) -> Dict[Tuple[int, ...], int]:
    """Index map {anonymous-walk pattern -> feature position} for `length`.
    Size = Bell number B_length (len 3 -> 5, 4 -> 15, 5 -> 52)."""
    idx = _WALK_VOCAB.get(length)
    if idx is None:
        idx = {w: i for i, w in enumerate(generate_anonymous_walks(length))}
        _WALK_VOCAB[length] = idx
    return idx


# Length-4 (paper default) kept as module constants for backward compatibility.
_ANON_INDEX = _walk_index(WALK_LENGTH)
EMBED_DIM = len(_ANON_INDEX)                    # == 15 for length 4


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
    `n_walks` random walks weighted by edge counts. Returns a Bell(length)-dim
    vector (15 for length 4) that sums to 1 (or all-zeros for a degenerate graph).
    """
    index = _walk_index(length)
    dim = len(index)
    adj = build_syscall_graph(seq)
    nodes = list(adj.keys())
    counts = [0] * dim
    if not nodes:
        return [0.0] * dim

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
        i = index.get(_anonymize(walk))
        if i is not None:
            counts[i] += 1
            total += 1

    if total == 0:
        return [0.0] * dim
    return [c / total for c in counts]


# ── Multi-scale rich embedding (the accuracy lever for the harder attacks) ────

def graph_stats(seq: Sequence[int]) -> List[float]:
    """Fixed-size, vocab-order-independent structural/content features of the
    syscall bigram graph — complements the walk distributions with 'how the
    syscalls are used' rather than just the shape. 8 features, each ~[0,1]."""
    import math
    adj = build_syscall_graph(seq)
    n = len(seq)
    if n < 2 or not adj:
        return [0.0] * 8
    nodes = list(adj.keys())
    edge_weights = [w for nbrs in adj.values() for w in nbrs.values()]
    n_nodes = len(nodes)
    n_edges = len(edge_weights)
    total_w = sum(edge_weights) or 1
    self_loops = sum(adj[v].get(v, 0) for v in nodes)
    probs = [w / total_w for w in edge_weights]
    ent = -sum(p * math.log(p) for p in probs if p > 0)
    ent_norm = ent / math.log(n_edges) if n_edges > 1 else 0.0
    return [
        min(1.0, n_nodes / 50.0),                 # vocabulary richness
        min(1.0, n_edges / 200.0),                # transition richness
        n_edges / (n_nodes * n_nodes),            # graph density
        self_loops / total_w,                     # tight-loop ratio
        ent_norm,                                 # transition entropy
        max(edge_weights) / total_w,              # busiest-transition dominance
        min(1.0, (n_edges / n_nodes) / 10.0),     # average fan-out
        n_edges / total_w,                        # unique-bigram ratio (inverse repetition)
    ]


def _hashed_freq(seq: Sequence[int], buckets: int) -> List[float]:
    """Normalized syscall-frequency histogram hashed into a fixed number of buckets
    (which syscalls run, independent of graph structure). Buckets keep it fixed-size
    for an unbounded/streaming syscall vocabulary."""
    v = [0.0] * buckets
    for s in seq:
        v[int(s) % buckets] += 1.0
    tot = sum(v) or 1.0
    return [x / tot for x in v]


RICH_LENGTHS = (3, 4, 5)          # Bell: 5 + 15 + 52 = 72
RICH_FREQ_BUCKETS = 32            # + 8 graph stats + 32 freq = 112 dims total


def rich_embedding(
    seq: Sequence[int],
    lengths: Tuple[int, ...] = RICH_LENGTHS,
    n_walks: int = N_WALKS,
    seed: int = 0,
    freq_buckets: int = RICH_FREQ_BUCKETS,
) -> List[float]:
    """Multi-signal window feature: anonymous-walk distributions at several lengths
    (multi-scale STRUCTURE) + graph statistics + a hashed syscall-frequency
    histogram (CONTENT). Combining structure and content is the lever for subtle
    attacks whose graph shape barely differs from normal, and it strictly subsumes
    the frequency-only baseline. Deterministic given `seed`."""
    feats: List[float] = []
    for L in lengths:
        feats.extend(anonymous_walk_embedding(seq, length=L, n_walks=n_walks, seed=seed + L))
    feats.extend(graph_stats(seq))
    feats.extend(_hashed_freq(seq, freq_buckets))
    return feats


def rich_embed_dim(lengths: Tuple[int, ...] = RICH_LENGTHS,
                   freq_buckets: int = RICH_FREQ_BUCKETS) -> int:
    """Dimensionality of rich_embedding."""
    return sum(len(_walk_index(L)) for L in lengths) + 8 + freq_buckets
