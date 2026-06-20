"""
Reward function for the PPO scheduler.

The reward is a weighted sum of five normalized signals; weights default to
the values listed in Section 6.1 of the project spec and can be overridden
for ablation experiments.

  R = α · (1 / startup_latency)
    + β · resource_utilization
    + γ · cluster_balance
    + δ · (1 / energy_cost)
    + ε · (1 / carbon_intensity)
    + ζ · co_location_synergy
    - SLA_PENALTY · sla_violated

All inputs are expected in their natural units; this module normalizes them
internally so the reward is roughly in [-10, 10].
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RewardWeights:
    latency:        float = 0.35
    utilization:    float = 0.25
    balance:        float = 0.15
    energy:         float = 0.10
    carbon:         float = 0.10
    co_location:    float = 0.05
    sla_penalty:    float = 10.0   # subtracted when SLA breached


def _safe_inv(x: float, eps: float = 1e-3) -> float:
    """Bounded reciprocal — avoids exploding reward when denominator is near zero."""
    return 1.0 / max(x, eps)


def compute_reward(
    *,
    startup_latency_seconds: float,
    resource_utilization:    float,        # [0, 1]
    cluster_balance:         float,        # [0, 1]  (1 = perfectly balanced)
    energy_cost_kwh:         float,
    carbon_intensity_gco2:   float,
    co_location_synergy:     float = 0.0,  # [0, 1]
    sla_violated:            bool  = False,
    weights:                 RewardWeights | None = None,
) -> float:
    if weights is None:
        weights = RewardWeights()

    # Normalize latency: cap at 30s so reward stays bounded
    latency_norm = min(startup_latency_seconds, 30.0)
    energy_norm  = max(energy_cost_kwh, 0.0)
    carbon_norm  = max(carbon_intensity_gco2, 0.0)

    r  = weights.latency       * _safe_inv(latency_norm)
    r += weights.utilization   * resource_utilization
    r += weights.balance       * cluster_balance
    r += weights.energy        * _safe_inv(energy_norm + 1.0)   # +1 so r ≤ weight
    r += weights.carbon        * _safe_inv(carbon_norm + 1.0)
    r += weights.co_location   * co_location_synergy

    if sla_violated:
        r -= weights.sla_penalty

    return float(r)
