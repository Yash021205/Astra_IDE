"""
B7 — convergent sequence CRDT for collaborative editing (Eg-walker family).
Guarantees replicas converge to the same text regardless of operation order.
"""
from ml.collab.crdt import Doc, Op, Elem, alloc_between

__all__ = ["Doc", "Op", "Elem", "alloc_between"]
