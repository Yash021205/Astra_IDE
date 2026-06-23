"""
Gymnasium environment that simulates a multi-node Kubernetes cluster for PPO training.

Observation space (40-dim float vector, all values normalized to [0, 1]):
  [0:NUM_NODES*4]              Per-node: cpu_util, mem_util, run_queue_len, network_load
  [NUM_NODES*4 : ...]          Pending job: cpu_request, mem_request, language_id,
                               risk_score, network_access, fs_write
  next                         Cluster-wide: carbon_intensity, time_of_day_sin,
                               time_of_day_cos, num_warm_pods

Action space (MultiDiscrete):
  [0] node_index            (NUM_NODES)
  [1] sandbox_tier          (3 — runc / gvisor / firecracker)
  [2] prewarm_decision      (2 — no / yes)
  [3] cross_cluster_migrate (2 — no / yes)

Reward — see reward.py.

In production the env's `step` would call the real Kubernetes API; in this
simulator we use simple in-memory state so training can run in seconds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except ImportError:  # gymnasium not yet installed (CI image without ML deps)
    _GYM_AVAILABLE = False
    gym = None       # type: ignore[assignment]
    spaces = None    # type: ignore[assignment]

from ml.scheduler.reward import compute_reward, RewardWeights


# ── Constants ────────────────────────────────────────────────────────────────
NUM_NODES_DEFAULT  = 4
NODE_FEATURES      = 4   # cpu, mem, rq_len, net_load
JOB_FEATURES       = 6   # cpu_req, mem_req, lang_id, risk, net, fs_write
CLUSTER_FEATURES   = 4   # carbon, tod_sin, tod_cos, warm_pool_count

LANG_VOCAB = {"python": 0, "javascript": 1, "go": 2, "rust": 3, "java": 4, "cpp": 5, "bash": 6}


@dataclass
class WorkloadJob:
    cpu_request:    float
    memory_request: float
    language_id:    int
    risk_score:     float
    network_access: bool
    fs_write:       bool


@dataclass
class ClusterState:
    num_nodes:        int
    cpu_util:         np.ndarray            # shape (N,)
    memory_util:      np.ndarray            # shape (N,)
    run_queue_len:    np.ndarray            # shape (N,)
    network_load:     np.ndarray            # shape (N,)
    warm_pool_count:  int = 0
    carbon_intensity: float = 0.4           # normalized [0, 1]

    @classmethod
    def empty(cls, num_nodes: int) -> "ClusterState":
        return cls(
            num_nodes=num_nodes,
            cpu_util=np.zeros(num_nodes,      dtype=np.float32),
            memory_util=np.zeros(num_nodes,   dtype=np.float32),
            run_queue_len=np.zeros(num_nodes, dtype=np.float32),
            network_load=np.zeros(num_nodes,  dtype=np.float32),
        )


# ── Internal pure functions (no Gym dependency) ─────────────────────────────

def encode_observation(state: ClusterState, job: WorkloadJob, time_of_day_h: float) -> np.ndarray:
    """Flatten cluster + job + cluster-wide features into the obs vector."""
    parts: list[np.ndarray] = []
    for n in range(state.num_nodes):
        parts.append(np.array([
            state.cpu_util[n],
            state.memory_util[n],
            state.run_queue_len[n],
            state.network_load[n],
        ], dtype=np.float32))

    parts.append(np.array([
        np.clip(job.cpu_request    / 4.0,    0, 1),  # normalize: 4 cores max
        np.clip(job.memory_request / 8192.0, 0, 1),  # normalize: 8GB  max
        job.language_id    / max(1, len(LANG_VOCAB) - 1),
        job.risk_score,
        float(job.network_access),
        float(job.fs_write),
    ], dtype=np.float32))

    tod_rad = 2 * np.pi * (time_of_day_h / 24.0)
    parts.append(np.array([
        state.carbon_intensity,
        (np.sin(tod_rad) + 1) / 2.0,
        (np.cos(tod_rad) + 1) / 2.0,
        np.clip(state.warm_pool_count / 10.0, 0, 1),
    ], dtype=np.float32))

    return np.concatenate(parts)


def compute_balance(cpu_util: np.ndarray) -> float:
    """Cluster balance score: 1 = perfectly balanced, 0 = one node carries all load."""
    if cpu_util.size <= 1 or cpu_util.sum() == 0:
        return 1.0
    return float(1.0 - cpu_util.std() / (cpu_util.mean() + 1e-3))


# ── Gymnasium environment ────────────────────────────────────────────────────

if _GYM_AVAILABLE:

    class SchedulerEnv(gym.Env):  # type: ignore[misc]
        """Simulated Kubernetes scheduling environment for PPO training."""

        metadata = {"render_modes": ["ansi"]}

        def __init__(
            self,
            num_nodes:           int   = NUM_NODES_DEFAULT,
            max_steps:           int   = 200,
            reward_weights:      Optional[RewardWeights] = None,
            seed:                Optional[int] = None,
            arrival_rate_lambda: float = 1.0,
        ):
            super().__init__()
            self.num_nodes           = num_nodes
            self.max_steps           = max_steps
            self.reward_weights      = reward_weights or RewardWeights()
            self.arrival_rate_lambda = arrival_rate_lambda

            obs_dim = num_nodes * NODE_FEATURES + JOB_FEATURES + CLUSTER_FEATURES
            self.observation_space = spaces.Box(
                low=0.0, high=1.0, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.MultiDiscrete([num_nodes, 3, 2, 2])

            self._rng         = np.random.default_rng(seed)
            self.state:       ClusterState = ClusterState.empty(num_nodes)
            self.pending_job: WorkloadJob  = self._sample_job()
            self.step_count   = 0
            self.time_of_day  = 0.0

        # ── Gymnasium API ────────────────────────────────────────────────

        def reset(self, *, seed: Optional[int] = None, options=None):
            super().reset(seed=seed)
            if seed is not None:
                self._rng = np.random.default_rng(seed)
            self.state        = ClusterState.empty(self.num_nodes)
            self.pending_job  = self._sample_job()
            self.step_count   = 0
            self.time_of_day  = float(self._rng.uniform(0, 24))
            return self._obs(), {}

        def step(self, action):
            node_idx, sandbox_tier, prewarm, cross_cluster = (
                int(action[0]), int(action[1]), int(action[2]), int(action[3])
            )
            self._apply_placement(node_idx, sandbox_tier, prewarm, cross_cluster)

            sla_violated = self.state.cpu_util[node_idx] > 0.95

            reward = compute_reward(
                startup_latency_seconds=self._estimate_latency(sandbox_tier, prewarm),
                resource_utilization=float(self.state.cpu_util.mean()),
                cluster_balance=compute_balance(self.state.cpu_util),
                energy_cost_kwh=float(self.state.cpu_util.sum() * 0.1),
                carbon_intensity_gco2=self.state.carbon_intensity * 500.0,
                co_location_synergy=0.0,
                sla_violated=sla_violated,
                weights=self.reward_weights,
            )

            # Sandbox-security penalty (report §6.1 ζ term; couples B1↔B4): a job
            # whose risk needs a stronger sandbox than the chosen tier is
            # under-isolated. Without this the agent would just pick runc (lowest
            # latency) for everything. required tier = risk band (cf. risk_scorer).
            risk = self.pending_job.risk_score
            required_tier = 0 if risk < 0.30 else (1 if risk < 0.70 else 2)
            if sandbox_tier < required_tier:
                reward -= 3.0

            self._decay_load()
            self.step_count  += 1
            self.time_of_day = (self.time_of_day + 0.25) % 24.0
            self.pending_job = self._sample_job()

            terminated = False
            truncated  = self.step_count >= self.max_steps
            return self._obs(), reward, terminated, truncated, {"sla_violated": sla_violated}

        def render(self):
            return (
                f"step={self.step_count} cpu_util={self.state.cpu_util.round(2)} "
                f"warm={self.state.warm_pool_count} carbon={self.state.carbon_intensity:.2f}"
            )

        # ── Internals ─────────────────────────────────────────────────────

        def _obs(self) -> np.ndarray:
            return encode_observation(self.state, self.pending_job, self.time_of_day)

        def _sample_job(self) -> WorkloadJob:
            return WorkloadJob(
                cpu_request    = float(self._rng.uniform(0.1, 2.0)),
                memory_request = float(self._rng.uniform(128, 4096)),
                language_id    = int(self._rng.integers(0, len(LANG_VOCAB))),
                risk_score     = float(self._rng.uniform(0, 1)),
                network_access = bool(self._rng.random() < 0.5),
                fs_write       = bool(self._rng.random() < 0.7),
            )

        def _apply_placement(self, node: int, tier: int, prewarm: int, cross_cluster: int):
            # Increase utilization on the chosen node by job's resource share
            cpu_inc = self.pending_job.cpu_request / 4.0
            mem_inc = self.pending_job.memory_request / 8192.0
            self.state.cpu_util[node]      = float(np.clip(self.state.cpu_util[node] + cpu_inc, 0, 1))
            self.state.memory_util[node]   = float(np.clip(self.state.memory_util[node] + mem_inc, 0, 1))
            self.state.run_queue_len[node] = float(np.clip(self.state.run_queue_len[node] + 0.05, 0, 1))

            if prewarm:
                self.state.warm_pool_count = min(self.state.warm_pool_count + 1, 10)

            # Carbon shifts slowly throughout the day
            self.state.carbon_intensity = float(np.clip(
                self.state.carbon_intensity + self._rng.normal(0, 0.02), 0.05, 0.95
            ))

        def _decay_load(self):
            # Jobs complete and free resources. Decay must roughly match the mean
            # per-step arrival (~1 job × cpu_req/4) so that GOOD load-balancing
            # keeps the cluster healthy while piling onto one node saturates it —
            # otherwise every policy saturates and placement quality is invisible.
            self.state.cpu_util       = np.clip(self.state.cpu_util       - 0.07, 0, 1)
            self.state.memory_util    = np.clip(self.state.memory_util    - 0.05, 0, 1)
            self.state.run_queue_len  = np.clip(self.state.run_queue_len  - 0.05, 0, 1)
            self.state.network_load   = np.clip(self.state.network_load   - 0.02, 0, 1)
            if self.state.warm_pool_count > 0 and self._rng.random() < 0.3:
                self.state.warm_pool_count -= 1

        def _estimate_latency(self, sandbox_tier: int, prewarm: int) -> float:
            base_latency = {0: 0.1, 1: 0.5, 2: 2.0}.get(sandbox_tier, 1.0)  # runc / gvisor / fc
            if prewarm and self.state.warm_pool_count > 0:
                return 0.5  # warm-pool hit
            return base_latency + float(self.state.cpu_util.mean()) * 5.0
else:

    class SchedulerEnv:  # type: ignore[no-redef]
        """Stub raised when gymnasium is not installed."""
        def __init__(self, *args: Any, **kwargs: Any):
            raise ImportError(
                "gymnasium is not installed. Install ML extras: pip install -r ml/requirements.txt"
            )
