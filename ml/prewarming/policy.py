"""
B3 Stage 2 — pre-warm policy + cold-start simulator.

Turns the forecaster's output into the two actions from the Transformer paper §V:
  (1) DEMAND  → size the pre-warm pool ahead of predicted spikes (cold-start *delay*);
  (2) IDLE    → adapt the keep-alive window to the predicted next inter-arrival
                (cold-start *frequency*), vs OpenWhisk's fixed 10-min window.

`simulate_cold_starts` replays a per-step invocation series through the standard
FaaS keep-alive model and counts cold starts, so we can compare policies:
  fixed-window (baseline)  vs  Shahrad hybrid-histogram  vs  adaptive (LSTM/oracle).
Paper Table III target: adaptive cuts cold starts ~50-80% vs the fixed window.
"""
from __future__ import annotations

import numpy as np

DEFAULT_WINDOW = 10          # OpenWhisk default keep-alive (minutes), paper §V-C


# ── Inter-arrival helpers ──────────────────────────────────────────────────────

def inter_arrival_gaps(counts) -> np.ndarray:
    """Gaps (in steps) between consecutive ACTIVE steps (count > 0)."""
    active = np.where(np.asarray(counts) > 0)[0]
    return np.diff(active) if len(active) >= 2 else np.array([], dtype=int)


def oracle_keep_alive(counts, default: int = DEFAULT_WINDOW) -> np.ndarray:
    """Perfect-foresight window: at each active step, keep alive exactly until the
    next active step. Upper bound on what any forecaster can achieve."""
    counts = np.asarray(counts)
    n = len(counts)
    ka = np.full(n, default, dtype=float)
    active = np.where(counts > 0)[0]
    for i, t in enumerate(active):
        ka[t] = (active[i + 1] - t) if i + 1 < len(active) else default
    return ka


def hybrid_histogram_keep_alive(counts, percentile: int = 95,
                                default: int = DEFAULT_WINDOW) -> np.ndarray:
    """
    Shahrad et al. (ATC'20) hybrid-histogram baseline: keep a per-function
    histogram of observed idle times and set the keep-alive window to a high
    percentile of the gaps seen *so far* (online). The window the histogram
    predicts is what we must beat.
    """
    counts = np.asarray(counts)
    n = len(counts)
    ka = np.full(n, default, dtype=float)
    gaps: list[int] = []
    last = None
    for t in range(n):
        if counts[t] > 0:
            if last is not None:
                gaps.append(t - last)
            last = t
            ka[t] = float(np.percentile(gaps, percentile)) if gaps else default
    return ka


def adaptive_keep_alive(predicted_gaps, margin: int = 1) -> np.ndarray:
    """Keep-alive window from the forecaster's predicted next inter-arrival."""
    return np.asarray(predicted_gaps, float) + margin


def prewarm_count(predicted_demand: float, capacity: int = 1) -> int:
    """Containers to pre-warm for a predicted concurrent demand (cold-start delay)."""
    return int(np.ceil(max(0.0, float(predicted_demand)) / max(1, capacity)))


# ── Cold-start simulator (standard FaaS keep-alive model) ──────────────────────

def simulate_cold_starts(counts, keep_alive, prewarm=None) -> dict:
    """
    Replay invocations; count cold starts. A container is warm at active step t
    if a previous invocation's keep-alive still covers t, or it was pre-warmed.

    counts     : per-step invocation counts (1D)
    keep_alive : scalar window, or per-step array (adaptive)
    prewarm    : optional bool per-step; True = a warm container is ready at t
    """
    counts = np.asarray(counts)
    n = len(counts)
    ka = keep_alive if np.ndim(keep_alive) else np.full(n, keep_alive)
    warm_until = -1.0
    cold = active = 0
    for t in range(n):
        if counts[t] <= 0:
            continue
        active += 1
        warm = (t <= warm_until) or (prewarm is not None and bool(prewarm[t]))
        if not warm:
            cold += 1
        warm_until = t + float(ka[t])
    return {"cold_starts": cold, "active": active,
            "rate": (cold / active) if active else 0.0}


def reduction_vs_fixed(counts, keep_alive, fixed_window: int = DEFAULT_WINDOW) -> float:
    """Cold-start reduction (%) of `keep_alive` vs the fixed-window baseline."""
    base = simulate_cold_starts(counts, fixed_window)["cold_starts"]
    new = simulate_cold_starts(counts, keep_alive)["cold_starts"]
    return 100.0 * (base - new) / base if base else 0.0
