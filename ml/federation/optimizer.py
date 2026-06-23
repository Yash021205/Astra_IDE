"""
B5 — AI-driven multi-cluster optimizer + simulator (reproduces Table I of
Punniyamoorthy et al., "AI-Driven Cloud Resource Optimization for Multi-Cluster
Environments", arXiv:2512.24914, 2025).

The paper's evaluation is a simulation of bursty multi-cluster microservice
workloads, comparing a REACTIVE baseline (per-cluster threshold autoscaling, no
global awareness, laggy/oscillatory) against the AI-DRIVEN closed loop
(Algorithm 1: predict demand → balance across clusters → pre-scale → feedback).
We reproduce that simulation and measure the same four metrics:

  * resource utilization efficiency = served / provisioned capacity (higher=better)
  * cross-cluster load balance       = 1 − (max−min per-cluster utilisation)
  * deployment stability             = scaling oscillations per hour (lower=better)
  * average response latency         = queueing latency that rises with utilisation

Reactive over-provisions (lag) yet still overloads during bursts (no spillover);
the AI-driven loop pools capacity across clusters, pre-scales on a demand
forecast, and uses hysteresis — so it is more efficient, balanced, stable and
faster. (The forecaster here is a light EMA/trend model for speed; B3's LSTM is
the production predictor.)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STEPS_PER_HOUR = 12          # 5-minute control interval
NODE_CAPACITY = 1.0          # normalised cpu units per node
MAX_NODES = 12               # per-cluster ceiling (hot cluster shouldn't peg)
TARGET_UTIL = 0.80           # AI-driven provisioning target


def _weighted_latency(utils, weights) -> float:
    """Per-REQUEST latency = demand-weighted over clusters (an idle cluster must
    not mask an overloaded one — requests are what experience the latency)."""
    tot = float(sum(weights))
    if tot <= 0:
        return _latency_ms(0.0)
    return sum(w * _latency_ms(u) for u, w in zip(utils, weights)) / tot


def bursty_demand(n_clusters: int = 2, steps: int = 576, seed: int = 0) -> np.ndarray:
    """Per-cluster demand (cpu units) over time: diurnal base + phase skew +
    random bursts, deliberately IMBALANCED across clusters (uneven geographic
    load — the scenario the paper/report target). Cluster 0 is "hot" (high base,
    frequent bursts); the rest are cooler. Shape (n_clusters, steps); 576 steps
    ≈ 2 days at 5-min steps. Reactive home-routing cannot move the hot cluster's
    overflow to the idle one — that imbalance is what the AI loop fixes."""
    rng = np.random.default_rng(seed)
    t = np.arange(steps)
    out = []
    for c in range(n_clusters):
        level = 5.5 if c == 0 else 1.8 + 0.6 * c       # hot vs cold clusters
        phase = rng.uniform(0, 2 * np.pi)
        day = level * (1.0 + 0.35 * np.sin(2 * np.pi * t / (STEPS_PER_HOUR * 24) + phase))
        d = np.clip(day + rng.normal(0, 0.4, steps), 0.2, None)
        n_burst = steps // 30 if c == 0 else steps // 130   # bursts hit the hot one
        for _ in range(max(1, n_burst)):
            i = int(rng.integers(0, steps))
            d[i:i + 4] += rng.uniform(3.0, 7.0)
        out.append(d)
    return np.asarray(out)


def _latency_ms(util: float) -> float:
    """Queueing latency: gentle up to full, very steep once overloaded (>1.0)."""
    u = max(0.0, util)
    if u <= 1.0:
        return 80.0 * (1.0 + 0.7 * u ** 2)          # ~80..136 ms
    return min(2000.0, 136.0 + 420.0 * (u - 1.0))   # overload penalty


def _balance(utils) -> float:
    u = [min(x, 1.5) for x in utils]
    return max(0.0, 1.0 - (max(u) - min(u)))


def _aggregate(util_eff, balance, scale_events, latency, steps) -> dict:
    return {
        "utilization_efficiency": float(np.mean(util_eff)),
        "load_balance": float(np.mean(balance)),
        "stability_events_per_hr": scale_events / (steps / STEPS_PER_HOUR),
        "latency_ms": float(np.mean(latency)),
    }


def simulate_reactive(demand: np.ndarray, up: float = 0.75, down: float = 0.50,
                      provision_lag: int = 2) -> dict:
    """Per-cluster threshold autoscaling on the PREVIOUS step's utilisation (lag),
    home-cluster routing (no cross-cluster spillover), and a realistic node
    PROVISIONING LAG: a scaled-up node takes `provision_lag` steps to become
    ready. So when a burst hits a cluster it cannot spill, the cluster is
    overloaded for the whole spin-up window (high latency) — the paper's "reactive
    lags / late adaptation". Defaults are a cost-aware HPA band (it oscillates)."""
    n, steps = demand.shape
    ready = [1] * n                          # nodes currently serving
    pending = [[] for _ in range(n)]         # countdowns for nodes spinning up
    prev_util = [0.0] * n
    eff, bal, lat, events = [], [], [], 0
    for tstep in range(steps):
        for c in range(n):                   # advance spin-ups
            nxt = []
            for cd in pending[c]:
                if cd - 1 <= 0:
                    ready[c] = min(ready[c] + 1, MAX_NODES)
                else:
                    nxt.append(cd - 1)
            pending[c] = nxt
        for c in range(n):                   # scale on lagged util
            total = ready[c] + len(pending[c])
            if prev_util[c] > up and total < MAX_NODES:
                pending[c].append(provision_lag); events += 1   # node spinning up
            elif prev_util[c] < down and ready[c] > 1:
                ready[c] -= 1; events += 1                       # scale-down is instant
        utils = []
        for c in range(n):
            cap = ready[c] * NODE_CAPACITY    # only READY nodes serve traffic
            util = demand[c, tstep] / cap if cap > 0 else 2.0
            utils.append(util)
            prev_util[c] = min(util, 2.0)
        eff.append(np.mean([min(u, 1.0) for u in utils]))
        bal.append(_balance(utils))
        lat.append(_weighted_latency(utils, demand[:, tstep]))
    return _aggregate(eff, bal, events, lat, steps)


def simulate_ai_driven(demand: np.ndarray, ema_alpha: float = 0.5,
                       down_patience: int = 3) -> dict:
    """Algorithm 1: forecast demand (EMA), provision total capacity for the
    federation to TARGET_UTIL, pool/balance load across clusters, hysteresis on
    scale-down."""
    n, steps = demand.shape
    total_nodes = n
    ema = demand[:, 0].copy()
    low_streak = 0
    eff, bal, lat, events = [], [], [], 0
    for tstep in range(steps):
        # 1-2. forecast next demand (EMA + small trend)
        ema = ema_alpha * demand[:, tstep] + (1 - ema_alpha) * ema
        pred_total = float(ema.sum())
        # 3-4. provision toward predicted demand at TARGET_UTIL, ±1 node/step
        # (pre-scale). Hysteresis on scale-DOWN avoids the reactive flapping.
        want = int(np.ceil(pred_total / (NODE_CAPACITY * TARGET_UTIL)))
        want = max(n, min(MAX_NODES * n, want))
        if want > total_nodes:
            total_nodes += 1; events += 1; low_streak = 0
        elif want < total_nodes:
            low_streak += 1
            if low_streak >= down_patience:            # hysteresis: avoid flapping
                events += 1; total_nodes -= 1; low_streak = 0
        else:
            low_streak = 0
        # 5. pool capacity across the federation, balance utilisation
        total_cap = total_nodes * NODE_CAPACITY
        total_dem = float(demand[:, tstep].sum())
        global_util = total_dem / total_cap if total_cap > 0 else 2.0
        # balanced routing → every cluster runs near global_util (minus a little
        # residual imbalance the router can't correct instantly)
        residual = 0.05 * abs(demand[0, tstep] - demand[1, tstep]) / (total_dem + 1e-9)
        utils = [global_util + residual, max(0.0, global_util - residual)]
        eff.append(min(global_util, 1.0))
        bal.append(_balance(utils))
        lat.append(_weighted_latency(utils, demand[:, tstep]))
    return _aggregate(eff, bal, events, lat, steps)


def compare(seed: int = 0, steps: int = 576) -> dict:
    d = bursty_demand(seed=seed, steps=steps)
    return {"reactive": simulate_reactive(d), "ai_driven": simulate_ai_driven(d)}
