"""
B2 — HashPipe sketch for per-PID Top-K resource monitoring (eHashPipe, Dai et
al.). HashPipe (Sivaraman et al., SIGCOMM'17) is a multi-stage table sketch that
retains heavy hitters in O(d·m) memory regardless of the number of distinct keys;
eHashPipe runs it in-kernel via eBPF to find the Top-K CPU/memory processes.

This is the pure algorithm (the eBPF in-kernel version lives in ebpf/tetragon/);
it reproduces the paper's Top-K precision: ~100% for small k, degrading as k grows.

Algorithm (per incoming (key, weight)):
  * Stage 1: hash key → slot. Same key → add weight. Else insert (key, weight)
    and CARRY the evicted (key, count) downstream.
  * Stages 2..d: hash carried key → slot. Same key → merge. Else keep the
    LARGER-count item in the slot and carry the SMALLER on. After the last stage
    the carried (smaller) item is dropped.
Heavy hitters accumulate large counts and survive; light keys are dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


def _h(key: int, stage: int, m: int) -> int:
    # Deterministic per-stage hash (NOT Python's salted hash(), which varies per
    # process and would make Top-K non-reproducible). Knuth multiplicative mix.
    x = (int(key) * 2654435761 + stage * 0x9E3779B1) & 0xFFFFFFFF
    x ^= (x >> 16)
    x = (x * 0x45D9F3B) & 0xFFFFFFFF
    x ^= (x >> 16)
    return x % m


@dataclass
class HashPipe:
    stages: int = 4          # d
    slots: int = 64          # m per stage  → tracks ~ stages*slots keys
    _tables: list = None     # list[stage] of dict slot-> [key, count]

    def __post_init__(self):
        self._tables = [dict() for _ in range(self.stages)]

    def update(self, key: int, weight: float = 1.0) -> None:
        # Stage 1: always claim the slot for the new key; carry the evicted one.
        s0 = _h(key, 0, self.slots)
        slot = self._tables[0].get(s0)
        if slot is not None and slot[0] == key:
            slot[1] += weight
            return
        carried = slot                       # (key, count) evicted, or None
        self._tables[0][s0] = [key, weight]

        # Stages 2..d: keep larger, carry smaller; drop after last stage.
        for st in range(1, self.stages):
            if carried is None:
                return
            si = _h(carried[0], st, self.slots)
            slot = self._tables[st].get(si)
            if slot is not None and slot[0] == carried[0]:
                slot[1] += carried[1]
                return
            if slot is None:
                self._tables[st][si] = carried
                return
            if carried[1] > slot[1]:          # keep larger in table, carry smaller
                self._tables[st][si] = carried
                carried = slot
            # else: carried stays the smaller, continue to next stage
        # carried (smallest) dropped after the last stage

    def items(self) -> List[Tuple[int, float]]:
        """All (key, count) currently retained, de-duplicated to the max count."""
        best: dict = {}
        for tbl in self._tables:
            for key, cnt in tbl.values():
                if key not in best or cnt > best[key]:
                    best[key] = cnt
        return list(best.items())

    def top_k(self, k: int) -> List[Tuple[int, float]]:
        return sorted(self.items(), key=lambda kc: kc[1], reverse=True)[:k]

    def memory_slots(self) -> int:
        return self.stages * self.slots


def topk_precision(estimated: List[Tuple[int, float]], true_topk: List[int]) -> float:
    """Fraction of the estimator's Top-K keys that are in the true Top-K."""
    if not estimated:
        return 0.0
    est_keys = {k for k, _ in estimated}
    hits = len(est_keys & set(true_topk))
    return hits / len(estimated)
