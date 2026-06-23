"""
PPO Agent for PF-MPPO with Algorithm 4 (Weighted Random Sampling).

Custom PPO implementation supporting:
- Action masking for invalid (task, VM) pairs
- Weighted random sampling (CDF-based) for exploration
- Clipped surrogate objective (Eq 36)
- Value function loss (Eq 33)
- Entropy bonus for exploration
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from ml.scheduler.pfmppo.network import PFMPPONetwork


@dataclass
class Transition:
    state: np.ndarray
    action: int
    log_prob: float
    reward: float
    value: float
    done: bool
    valid_mask: np.ndarray


class RolloutBuffer:
    """Stores trajectory data for PPO updates."""

    def __init__(self):
        self.transitions: List[Transition] = []

    def add(
        self,
        state: np.ndarray,
        action: int,
        log_prob: float,
        reward: float,
        value: float,
        done: bool,
        valid_mask: np.ndarray,
    ) -> None:
        self.transitions.append(Transition(state, action, log_prob, reward, value, done, valid_mask))

    def clear(self) -> None:
        self.transitions = []

    def __len__(self) -> int:
        return len(self.transitions)

    def get_tensors(self, device: torch.device) -> Dict[str, torch.Tensor]:
        """Convert buffer to tensors for PPO update."""
        states = torch.tensor(
            np.array([t.state for t in self.transitions]), dtype=torch.float32, device=device
        )
        actions = torch.tensor(
            [t.action for t in self.transitions], dtype=torch.long, device=device
        )
        old_log_probs = torch.tensor(
            [t.log_prob for t in self.transitions], dtype=torch.float32, device=device
        )
        rewards = torch.tensor(
            [t.reward for t in self.transitions], dtype=torch.float32, device=device
        )
        values = torch.tensor(
            [t.value for t in self.transitions], dtype=torch.float32, device=device
        )
        dones = torch.tensor(
            [t.done for t in self.transitions], dtype=torch.float32, device=device
        )
        valid_masks = torch.tensor(
            np.array([t.valid_mask for t in self.transitions]), dtype=torch.float32, device=device
        )
        return {
            "states": states,
            "actions": actions,
            "old_log_probs": old_log_probs,
            "rewards": rewards,
            "values": values,
            "dones": dones,
            "valid_masks": valid_masks,
        }


class PPOAgent:
    """
    PPO agent implementing the PF-MPPO training algorithm.

    Supports:
    - Weighted random sampling (Algorithm 4) for action selection
    - Clipped surrogate objective (Eq 36)
    - Advantage estimation (TD(0))
    """

    def __init__(
        self,
        network: PFMPPONetwork,
        lr: float = 0.001,
        gamma: float = 0.9,
        epsilon: float = 0.2,
        value_coeff: float = 0.5,
        entropy_coeff: float = 0.01,
        max_grad_norm: float = 0.5,
        update_epochs: int = 4,
        mini_batch_size: int = 64,
        device: Optional[torch.device] = None,
    ):
        self.network = network
        self.gamma = gamma
        self.epsilon = epsilon
        self.value_coeff = value_coeff
        self.entropy_coeff = entropy_coeff
        self.max_grad_norm = max_grad_norm
        self.update_epochs = update_epochs
        self.mini_batch_size = mini_batch_size
        self.device = device or torch.device("cpu")

        self.network.to(self.device)
        self.optimizer = optim.Adam(self.network.parameters(), lr=lr)

    def select_action(
        self,
        state: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        deterministic: bool = False,
    ) -> Tuple[int, float, float]:
        """
        Select action using Algorithm 4 (Weighted Random Sampling).

        Returns: (action_index, log_probability, state_value)
        """
        state_t = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        mask_t = None
        if valid_mask is not None:
            mask_t = torch.tensor(valid_mask, dtype=torch.float32, device=self.device).unsqueeze(0)

        with torch.no_grad():
            action_probs, value = self.network(state_t, mask_t)

        probs = action_probs.squeeze(0).cpu().numpy()
        value_scalar = value.squeeze().item()

        if deterministic:
            action = int(np.argmax(probs))
        else:
            # Algorithm 4: Weighted Random Sampling via CDF
            action = _weighted_random_sampling(probs)

        log_prob = float(np.log(max(probs[action], 1e-8)))
        return action, log_prob, value_scalar

    def compute_advantages(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
        dones: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute TD advantages: A_t = R_t + gamma * V(S_{t+1}) - V(S_t)
        and discounted returns for value target.
        """
        n = len(rewards)
        advantages = torch.zeros(n, device=self.device)
        returns = torch.zeros(n, device=self.device)

        next_value = 0.0
        for t in reversed(range(n)):
            if t == n - 1:
                next_val = 0.0
            else:
                next_val = values[t + 1].item() * (1.0 - dones[t + 1].item())

            returns[t] = rewards[t] + self.gamma * next_val * (1.0 - dones[t])
            advantages[t] = returns[t] - values[t]

        # Normalize advantages
        if advantages.std() > 1e-8:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        return advantages, returns

    def update(self, buffer: RolloutBuffer) -> Dict[str, float]:
        """
        PPO clipped update (Eq 36 actor loss + Eq 33 critic loss + entropy).

        Returns dict of loss metrics for logging.
        """
        data = buffer.get_tensors(self.device)
        states = data["states"]
        actions = data["actions"]
        old_log_probs = data["old_log_probs"]
        rewards = data["rewards"]
        values = data["values"]
        dones = data["dones"]
        valid_masks = data["valid_masks"]

        advantages, returns = self.compute_advantages(rewards, values, dones)

        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_entropy = 0.0
        num_updates = 0

        n = len(states)
        for _ in range(self.update_epochs):
            indices = np.random.permutation(n)
            for start in range(0, n, self.mini_batch_size):
                end = min(start + self.mini_batch_size, n)
                batch_idx = indices[start:end]

                batch_states = states[batch_idx]
                batch_actions = actions[batch_idx]
                batch_old_log_probs = old_log_probs[batch_idx]
                batch_advantages = advantages[batch_idx]
                batch_returns = returns[batch_idx]
                batch_masks = valid_masks[batch_idx]

                # Forward pass
                action_probs, state_values = self.network(batch_states, batch_masks)
                state_values = state_values.squeeze(-1)

                # Log probabilities of taken actions
                dist = torch.distributions.Categorical(action_probs)
                new_log_probs = dist.log_prob(batch_actions)
                entropy = dist.entropy().mean()

                # Probability ratio (Eq 36)
                ratio = torch.exp(new_log_probs - batch_old_log_probs)

                # Clipped surrogate objective
                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1.0 - self.epsilon, 1.0 + self.epsilon) * batch_advantages
                actor_loss = -torch.min(surr1, surr2).mean()

                # Critic loss (Eq 33)
                critic_loss = nn.functional.mse_loss(state_values, batch_returns)

                # Total loss
                loss = actor_loss + self.value_coeff * critic_loss - self.entropy_coeff * entropy

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.network.parameters(), self.max_grad_norm)
                self.optimizer.step()

                total_actor_loss += actor_loss.item()
                total_critic_loss += critic_loss.item()
                total_entropy += entropy.item()
                num_updates += 1

        num_updates = max(num_updates, 1)
        return {
            "actor_loss": total_actor_loss / num_updates,
            "critic_loss": total_critic_loss / num_updates,
            "entropy": total_entropy / num_updates,
        }

    def get_weights(self) -> Dict[str, torch.Tensor]:
        """Get network parameters as state dict."""
        return {k: v.clone() for k, v in self.network.state_dict().items()}

    def set_weights(self, state_dict: Dict[str, torch.Tensor]) -> None:
        """Load network parameters from state dict."""
        self.network.load_state_dict(state_dict)

    def save(self, path: str) -> None:
        """Save model and optimizer state."""
        torch.save({
            "network": self.network.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }, path)

    def load(self, path: str) -> None:
        """Load model and optimizer state."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=True)
        self.network.load_state_dict(checkpoint["network"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])


def _weighted_random_sampling(probs: np.ndarray) -> int:
    """
    Algorithm 4: Weighted Random Sampling via CDF.

    1. Generate random mu ~ U(0, 1)
    2. Compute CDF = cumulative sum of probs
    3. Return index where CDF >= mu (binary search)
    """
    mu = np.random.uniform(0, 1)
    cdf = np.cumsum(probs)
    action = int(np.searchsorted(cdf, mu))
    return min(action, len(probs) - 1)
