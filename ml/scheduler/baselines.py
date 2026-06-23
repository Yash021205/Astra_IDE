"""
B1 — non-learning scheduler baselines to compare PPO against (report §6.1:
"compare vs kube-scheduler default, FIFO, Round-Robin, Best-Fit").

Each baseline is a callable `policy(env) -> action` for the SchedulerEnv's
MultiDiscrete action [node, sandbox_tier, prewarm, migrate]. They all pick the
sandbox tier from the job's risk (the same rule the risk scorer uses) and never
pre-warm/migrate — so the comparison isolates the PLACEMENT decision, which is
what PPO must learn to do better (jointly optimising utilisation, balance,
latency, SLA).
"""
from __future__ import annotations

import numpy as np


def _tier_from_risk(risk: float) -> int:
    return 0 if risk < 0.30 else (1 if risk < 0.70 else 2)   # runc / gvisor / firecracker


def _action(node: int, env) -> np.ndarray:
    return np.array([node, _tier_from_risk(env.pending_job.risk_score), 0, 0], dtype=int)


def round_robin():
    """FIFO/round-robin: cycle through nodes regardless of load (the naive default)."""
    ctr = {"i": 0}

    def pick(env):
        node = ctr["i"] % env.num_nodes
        ctr["i"] += 1
        return _action(node, env)
    return pick


def least_loaded(env):
    """Greedy: place on the node with the lowest current CPU utilisation."""
    return _action(int(np.argmin(env.state.cpu_util)), env)


def best_fit(env):
    """Bin-packing best-fit: the most-loaded node that still has room for the job
    (packs tightly; risks SLA breaches when it guesses wrong)."""
    need = env.pending_job.cpu_request / 4.0
    slack = 1.0 - env.state.cpu_util
    fits = np.where(slack >= need)[0]
    if len(fits) == 0:
        return _action(int(np.argmax(slack)), env)        # least-full if none fit
    # among fitting nodes, pick the one left with the least slack (tightest pack)
    node = fits[np.argmin(slack[fits] - need)]
    return _action(int(node), env)


def random_pick(seed: int = 0):
    rng = np.random.default_rng(seed)

    def pick(env):
        return _action(int(rng.integers(env.num_nodes)), env)
    return pick


def all_baselines(seed: int = 0) -> dict:
    return {
        "round_robin": round_robin(),
        "least_loaded": least_loaded,
        "best_fit": best_fit,
        "random": random_pick(seed),
    }
