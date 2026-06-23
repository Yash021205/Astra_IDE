"""
B6 — carbon-aware scheduling (PCAPS-style temporal shifting).

Anchor: Lechowicz et al., "Carbon- and Precedence-Aware Scheduling for Data
Processing Clusters" (PCAPS) — reduces carbon footprint by up to 32.9% by running
deferrable work in low-carbon windows, with a configurable knob trading carbon
savings against completion time.

For ASTRA, latency-sensitive interactive workspaces run immediately, but
deferrable batch work (CI builds, test runs, nightly jobs) can be shifted within
its slack to the lowest-carbon period. This module:
  * `carbon_agnostic` — run every job at arrival (the baseline);
  * `carbon_aware`    — shift each job to the min-carbon window within its slack;
  * carbon accounting over a real/synthetic gCO2/kWh time series.
The slack budget is the PCAPS knob: more slack → more carbon saved, more delay.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Job:
    arrival: int        # step index when the job is ready
    duration: int       # steps of compute
    power_kw: float = 0.2   # avg power draw while running


def _window_carbon(trace: np.ndarray, start: int, duration: int) -> float:
    seg = trace[start:start + duration]
    return float(seg.mean()) if len(seg) else float(trace[-1])


def carbon_agnostic(jobs, trace: np.ndarray) -> list[int]:
    """Baseline: start each job the moment it arrives."""
    return [min(j.arrival, len(trace) - 1) for j in jobs]


def carbon_aware(jobs, trace: np.ndarray, slack: int) -> list[int]:
    """Start each job at the lowest-average-carbon window within
    [arrival, arrival + slack] (bounded so it still finishes within the trace)."""
    starts = []
    n = len(trace)
    for j in jobs:
        latest = min(j.arrival + slack, n - j.duration)
        latest = max(latest, j.arrival)
        best_s, best_c = j.arrival, float("inf")
        for s in range(j.arrival, latest + 1):
            c = _window_carbon(trace, s, j.duration)
            if c < best_c:
                best_c, best_s = c, s
        starts.append(best_s)
    return starts


def total_carbon(jobs, starts, trace: np.ndarray, step_hours: float = 0.5) -> float:
    """gCO2 emitted = Σ power(kW) · carbon(gCO2/kWh) · hours, over each job's run."""
    g = 0.0
    for j, s in zip(jobs, starts):
        for t in range(s, min(s + j.duration, len(trace))):
            g += j.power_kw * trace[t] * step_hours
    return g


def mean_delay(jobs, starts) -> float:
    """Average completion-time delay (steps) the policy introduced."""
    return float(np.mean([s - j.arrival for j, s in zip(jobs, starts)])) if jobs else 0.0


def evaluate(jobs, trace: np.ndarray, slack: int, step_hours: float = 0.5) -> dict:
    a = carbon_agnostic(jobs, trace)
    w = carbon_aware(jobs, trace, slack)
    ca, cw = total_carbon(jobs, a, trace, step_hours), total_carbon(jobs, w, trace, step_hours)
    return {
        "carbon_agnostic_g": ca,
        "carbon_aware_g": cw,
        "carbon_reduction_pct": 100.0 * (ca - cw) / ca if ca else 0.0,
        "mean_delay_steps": mean_delay(jobs, w),
    }


# ── Synthetic diurnal carbon trace (for tests; the benchmark uses real data) ──

def diurnal_trace(days: int = 2, steps_per_day: int = 48, seed: int = 0) -> np.ndarray:
    """gCO2/kWh with a daily shape: low overnight + midday (solar), high at the
    morning/evening peaks — the structure real grids show."""
    rng = np.random.default_rng(seed)
    t = np.arange(days * steps_per_day)
    h = (t % steps_per_day) / steps_per_day * 24.0
    base = (300
            + 120 * np.sin(2 * np.pi * (h - 18) / 24)      # evening peak
            - 80 * np.exp(-((h - 13) ** 2) / 6))           # midday solar dip
    return np.clip(base + rng.normal(0, 12, len(t)), 50, None)
