"""
B5 — Multi-cluster federation with AI-driven optimization.

Reproduces the closed-loop optimizer of Punniyamoorthy et al.
(arXiv:2512.24914, 2025): predict cross-cluster demand → balance load → pre-scale
→ feedback, beating a reactive per-cluster autoscaler on utilisation, load
balance, stability and latency (paper Table I). The real federation control plane
is Karmada (see k8s/karmada/ + its runbook).
"""
from ml.federation.optimizer import (
    bursty_demand, simulate_reactive, simulate_ai_driven, compare,
    STEPS_PER_HOUR, TARGET_UTIL,
)

__all__ = [
    "bursty_demand", "simulate_reactive", "simulate_ai_driven", "compare",
    "STEPS_PER_HOUR", "TARGET_UTIL",
]
