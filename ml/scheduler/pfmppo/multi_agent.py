"""
Multi-Agent CTDE (Centralized Training, Decentralized Execution) for PF-MPPO.

Architecture: 1 Global PPO node + N Worker agents.
Workers collect trajectories in parallel using ThreadPoolExecutor (Windows-compatible).
Global node aggregates trajectories and performs PPO update.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import numpy as np
import torch

from ml.scheduler.pfmppo.env import PFMPPOEnv
from ml.scheduler.pfmppo.network import PFMPPONetwork
from ml.scheduler.pfmppo.ppo_agent import PPOAgent, RolloutBuffer


class WorkerAgent:
    """
    A worker that collects trajectories from its own environment instance.
    Uses the shared policy weights for action selection.
    """

    def __init__(
        self,
        worker_id: int,
        env_config: Dict,
        network: PFMPPONetwork,
        gamma: float = 0.9,
        device: torch.device = torch.device("cpu"),
    ):
        self.worker_id = worker_id
        self.device = device
        self.network = copy.deepcopy(network).to(device)
        self.network.eval()
        self.gamma = gamma

        env_seed = env_config.get("seed", 42) + worker_id * 1000
        self.env = PFMPPOEnv(
            num_tasks=env_config.get("num_tasks", 20),
            num_vms=env_config.get("num_vms", 4),
            k_pairs=env_config.get("k_pairs", 10),
            max_steps=env_config.get("max_steps", 200),
            max_deps_per_task=env_config.get("max_deps_per_task", 3),
            vm_configs=env_config.get("vm_configs"),
            seed=env_seed,
            # Thread the workload-source settings through so --dag-mode / --data-dir
            # / template / full-dataset options actually reach training.
            dag_mode=env_config.get("dag_mode", "random"),
            num_workspaces=env_config.get("num_workspaces", (3, 8)),
            template_ratio=env_config.get("template_ratio", 0.7),
            data_dir=env_config.get("data_dir"),
            max_files=env_config.get("max_files", 10),
            reward_mode=env_config.get("reward_mode", "paper"),
            feature_mode=env_config.get("feature_mode", "paper"),
            max_tasks_in_window=env_config.get("max_tasks_in_window"),
        )

    def collect_trajectory(self, steps: int) -> RolloutBuffer:
        """Collect `steps` transitions using current policy."""
        buffer = RolloutBuffer()
        obs, info = self.env.reset()
        valid_mask = info.get("valid_mask", np.ones(self.env.k_pairs, dtype=np.float32))

        for _ in range(steps):
            action, log_prob, value = self._select_action(obs, valid_mask)

            next_obs, reward, terminated, truncated, info = self.env.step(action)
            done = terminated or truncated
            next_valid_mask = info.get("valid_mask", np.ones(self.env.k_pairs, dtype=np.float32))

            buffer.add(obs, action, log_prob, reward, value, done, valid_mask)

            if done:
                obs, info = self.env.reset()
                valid_mask = info.get("valid_mask", np.ones(self.env.k_pairs, dtype=np.float32))
            else:
                obs = next_obs
                valid_mask = next_valid_mask

        return buffer

    def sync_weights(self, state_dict: Dict[str, torch.Tensor]) -> None:
        """Update this worker's network from the global weights."""
        self.network.load_state_dict(state_dict)

    def _select_action(self, state: np.ndarray, valid_mask: np.ndarray):
        """Select action using weighted random sampling (Algorithm 4)."""
        state_t = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        mask_t = torch.tensor(valid_mask, dtype=torch.float32, device=self.device).unsqueeze(0)

        with torch.no_grad():
            action_probs, value = self.network(state_t, mask_t)

        probs = action_probs.squeeze(0).cpu().numpy()
        value_scalar = value.squeeze().item()

        # Algorithm 4: CDF-based sampling
        mu = np.random.uniform(0, 1)
        cdf = np.cumsum(probs)
        action = int(np.searchsorted(cdf, mu))
        action = min(action, len(probs) - 1)

        log_prob = float(np.log(max(probs[action], 1e-8)))
        return action, log_prob, value_scalar


class CTDETrainer:
    """
    Centralized Training Decentralized Execution trainer.

    1 Global PPO agent + N workers collecting trajectories in parallel.
    Training loop:
    1. Broadcast weights to workers
    2. Workers collect trajectories in parallel
    3. Aggregate buffers
    4. Global PPO update
    5. Repeat
    """

    def __init__(
        self,
        num_workers: int = 9,
        env_config: Optional[Dict] = None,
        k_pairs: int = 10,
        lr: float = 0.001,
        gamma: float = 0.9,
        epsilon: float = 0.2,
        batch_size: int = 1000,
        update_epochs: int = 4,
        mini_batch_size: int = 64,
        device: Optional[torch.device] = None,
    ):
        self.num_workers = num_workers
        self.batch_size = batch_size
        self.device = device or torch.device("cpu")

        env_config = env_config or {}
        env_config.setdefault("k_pairs", k_pairs)
        self.env_config = env_config

        from ml.scheduler.pfmppo.env import features_per_pair
        input_dim = k_pairs * features_per_pair(env_config.get("feature_mode", "paper"))
        self.network = PFMPPONetwork(input_dim=input_dim, k_pairs=k_pairs)

        self.global_agent = PPOAgent(
            network=self.network,
            lr=lr,
            gamma=gamma,
            epsilon=epsilon,
            update_epochs=update_epochs,
            mini_batch_size=mini_batch_size,
            device=self.device,
        )

        self.workers: List[WorkerAgent] = []
        for i in range(num_workers):
            worker = WorkerAgent(
                worker_id=i,
                env_config=env_config,
                network=self.network,
                gamma=gamma,
                device=self.device,
            )
            self.workers.append(worker)

        self.training_history: List[Dict[str, float]] = []

    def train(self, iterations: int = 2000, log_interval: int = 100) -> Dict[str, List[float]]:
        """
        Run the CTDE training loop.

        Returns training metrics history.
        """
        import time
        steps_per_worker = max(1, self.batch_size // self.num_workers)
        metrics_history = {"actor_loss": [], "critic_loss": [], "entropy": [], "mean_reward": []}
        t_start = time.time()

        for iteration in range(1, iterations + 1):
            # Broadcast current weights
            global_weights = self.global_agent.get_weights()
            for worker in self.workers:
                worker.sync_weights(global_weights)

            # Collect trajectories in parallel
            buffers = self._collect_all(steps_per_worker)

            # Aggregate into single buffer
            aggregated = RolloutBuffer()
            total_reward = 0.0
            total_steps = 0
            for buf in buffers:
                for t in buf.transitions:
                    aggregated.add(t.state, t.action, t.log_prob, t.reward, t.value, t.done, t.valid_mask)
                    total_reward += t.reward
                    total_steps += 1

            # PPO update
            metrics = self.global_agent.update(aggregated)
            mean_reward = total_reward / max(total_steps, 1)
            metrics["mean_reward"] = mean_reward

            for key in metrics_history:
                metrics_history[key].append(metrics.get(key, 0.0))

            self.training_history.append(metrics)

            # Progress: log the first few iterations (so the run is visibly alive
            # within seconds), then every `log_interval`, always with an ETA. flush
            # so it streams in notebooks/CI where stdout is block-buffered.
            if iteration <= 5 or iteration % log_interval == 0 or iteration == iterations:
                elapsed = time.time() - t_start
                per_it = elapsed / iteration
                eta_s = per_it * (iterations - iteration)
                print(
                    f"[Iter {iteration}/{iterations}] "
                    f"reward={mean_reward:.4f} "
                    f"actor_loss={metrics['actor_loss']:.4f} "
                    f"critic_loss={metrics['critic_loss']:.4f} "
                    f"entropy={metrics['entropy']:.4f} "
                    f"| {per_it:.2f}s/it  ETA {eta_s/60:.1f} min",
                    flush=True,
                )

        return metrics_history

    def _collect_all(self, steps_per_worker: int) -> List[RolloutBuffer]:
        """Collect trajectories from all workers using ThreadPoolExecutor."""
        buffers: List[RolloutBuffer] = []

        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {
                executor.submit(worker.collect_trajectory, steps_per_worker): worker
                for worker in self.workers
            }
            for future in as_completed(futures):
                buffers.append(future.result())

        return buffers

    def save(self, path: str) -> None:
        """Save the global agent model."""
        self.global_agent.save(path)

    def load(self, path: str) -> None:
        """Load the global agent model."""
        self.global_agent.load(path)

    def get_agent(self) -> PPOAgent:
        """Return the trained global agent."""
        return self.global_agent
