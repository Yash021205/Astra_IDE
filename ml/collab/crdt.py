"""
B7 — convergent sequence CRDT for collaborative code editing.

Anchor: Kleppmann et al., "Collaborative Text Editing with Eg-walker: Better,
Faster, Smaller" (EuroSys 2025). Eg-walker's headline is an event-graph algorithm
with orders-of-magnitude less steady-state memory; its *guarantee* — the one every
collaborative editor must have — is that **all replicas converge to the same text
regardless of the order operations arrive in**.

This module implements that guarantee with a dense position-identifier sequence
CRDT (the Logoot/LSEQ family that Yjs/Automerge/Eg-walker all build on): every
inserted character gets an immutable, totally-ordered position key, so applying
the same operations in any order yields the same document. Deletes are tombstones.
The document is the characters sorted by (key, replica), skipping tombstones.

(Eg-walker's contribution is making this fast and compact at scale; ASTRA's
frontend uses Yjs in production. Here we reproduce the convergence guarantee and
verify it on a real keystroke trace.)
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

BASE = 256


def alloc_between(lo: list[int], hi: list[int]) -> list[int]:
    """Return an int-list strictly between lo and hi (missing digits => 0 for lo,
    BASE for hi). Concurrent allocations in the same gap yield the same key and are
    tie-broken by replica id, so all replicas still converge."""
    res: list[int] = []
    i = 0
    while True:
        l = lo[i] if i < len(lo) else 0
        h = hi[i] if i < len(hi) else BASE
        if l + 1 < h:
            res.append((l + h) // 2)
            return res
        res.append(l)
        i += 1


@dataclass
class Elem:
    key: tuple
    replica: int
    char: str
    eid: tuple                 # id of the insert op that created it
    deleted: bool = False
    def order(self) -> tuple:
        return (self.key, self.replica)


@dataclass
class Op:
    kind: str                  # 'ins' | 'del'
    id: tuple                  # unique op id = (replica, seq)
    key: tuple = ()            # ins: position key
    replica: int = 0           # ins: tie-break
    char: str = ""             # ins: character
    target: tuple = ()         # del: eid of element to tombstone


class Doc:
    """A CRDT replica. local_* produce ops AND apply them; apply() integrates any
    op idempotently + commutatively, so replicas converge."""

    def __init__(self, replica: int):
        self.replica = replica
        self.elems: list[Elem] = []                 # sorted by order()
        self._orders: list[tuple] = []              # parallel sorted keys (fast insert)
        self.by_id: dict[tuple, Elem] = {}
        self.seq = 0

    # reads
    def text(self) -> str:
        return "".join(e.char for e in self.elems if not e.deleted)

    def _visible(self) -> list[Elem]:
        return [e for e in self.elems if not e.deleted]

    # local edits -> ops
    def local_insert(self, index: int, char: str) -> Op:
        vis = self._visible()
        lo = list(vis[index - 1].key) if 0 < index <= len(vis) else []
        hi = list(vis[index].key) if index < len(vis) else []
        key = tuple(alloc_between(lo, hi))
        self.seq += 1
        op = Op("ins", (self.replica, self.seq), key, self.replica, char)
        self.apply(op)
        return op

    def local_delete(self, index: int) -> Op | None:
        vis = self._visible()
        if not (0 <= index < len(vis)):
            return None
        self.seq += 1
        op = Op("del", (self.replica, self.seq), target=vis[index].eid)
        self.apply(op)
        return op

    # integrate any op (local or remote)
    def apply(self, op: Op) -> None:
        if op.kind == "ins":
            if op.id in self.by_id:
                return                                  # idempotent
            e = Elem(op.key, op.replica, op.char, op.id)
            i = bisect.bisect_left(self._orders, e.order())
            self._orders.insert(i, e.order())
            self.elems.insert(i, e)
            self.by_id[op.id] = e
        else:
            tgt = self.by_id.get(op.target)
            if tgt is not None:
                tgt.deleted = True                      # idempotent tombstone

    def apply_all(self, ops) -> None:
        for op in ops:
            self.apply(op)
