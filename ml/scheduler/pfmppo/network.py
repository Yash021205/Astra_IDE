"""
PF-MPPO Neural Network architecture (paper Table 1).

5-hidden-layer shared network with separate Actor (Softmax) and Critic (value) heads.
Architecture: Input(100) -> 32 -> 64 -> 32 -> 16 -> [Actor: K, Critic: 1]
"""
from __future__ import annotations

import torch
import torch.nn as nn


class PFMPPONetwork(nn.Module):
    """
    Actor-Critic network for PF-MPPO.

    Shared backbone processes the state, then splits into:
    - Actor head: probability distribution over K task-VM pairs
    - Critic head: scalar state value estimate V(s)
    """

    def __init__(self, input_dim: int = 100, k_pairs: int = 10):
        super().__init__()
        self.input_dim = input_dim
        self.k_pairs = k_pairs

        self.shared = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
        )

        self.actor_head = nn.Linear(16, k_pairs)
        self.critic_head = nn.Linear(16, 1)

        self._init_weights()

    def _init_weights(self):
        for module in self.shared:
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                nn.init.zeros_(module.bias)
        nn.init.xavier_uniform_(self.actor_head.weight)
        nn.init.zeros_(self.actor_head.bias)
        nn.init.xavier_uniform_(self.critic_head.weight)
        nn.init.zeros_(self.critic_head.bias)

    def forward(
        self, state: torch.Tensor, valid_mask: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        Args:
            state: (batch, input_dim) tensor
            valid_mask: (batch, k_pairs) binary mask; 1 = valid action, 0 = invalid

        Returns:
            action_probs: (batch, k_pairs) probability distribution
            state_value: (batch, 1) value estimate
        """
        x = self.shared(state)

        logits = self.actor_head(x)

        # Action masking: set invalid actions to -inf before softmax
        if valid_mask is not None:
            logits = logits.masked_fill(valid_mask == 0, float('-inf'))

        action_probs = torch.softmax(logits, dim=-1)

        # Handle edge case: all actions masked (replace NaN with uniform)
        nan_mask = torch.isnan(action_probs).any(dim=-1, keepdim=True)
        if nan_mask.any():
            uniform = torch.ones_like(action_probs) / self.k_pairs
            action_probs = torch.where(nan_mask.expand_as(action_probs), uniform, action_probs)

        state_value = self.critic_head(x)

        return action_probs, state_value
