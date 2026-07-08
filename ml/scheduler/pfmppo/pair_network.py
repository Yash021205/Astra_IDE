"""
Permutation-equivariant scoring network for (task, VM) pair selection.

`PFMPPONetwork` flattens the K pairs into one vector and maps it through a dense
MLP to K logits. That architecture ties every output to a fixed slot, so the
network has to relearn the same comparison separately for each position and
cannot express a rule as simple as "choose the pair with the smallest estimated
finish time" without memorising it K times over.

This network instead scores each pair independently with one shared MLP and takes
a softmax across pairs. Selection rules of the form `argmin/argmax over pairs of
f(features)` become directly representable, which is exactly the family the
list-scheduling heuristics belong to, so cloning an expert needs far fewer
demonstrations and the policy generalises across K.
"""
from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn as nn


class PairScoringNetwork(nn.Module):
    """Actor-critic over a variable set of candidate pairs.

    Args:
        features_per_pair: width of one pair's feature block.
        k_pairs: number of candidate slots (the action-space size).
        hidden: width of the shared scoring trunk.
    """

    def __init__(self, features_per_pair: int = 16, k_pairs: int = 24, hidden: int = 64):
        super().__init__()
        self.features_per_pair = features_per_pair
        self.k_pairs = k_pairs

        self.encoder = nn.Sequential(
            nn.Linear(features_per_pair, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.score_head = nn.Linear(hidden, 1)
        self.critic_head = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                nn.init.zeros_(module.bias)

    def forward(
        self,
        state: torch.Tensor,
        valid_mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns (action probabilities over K pairs, state value)."""
        if state.dim() == 1:
            state = state.unsqueeze(0)
        batch = state.shape[0]

        pairs = state.view(batch, self.k_pairs, self.features_per_pair)
        embedded = self.encoder(pairs)                      # (B, K, hidden)
        logits = self.score_head(embedded).squeeze(-1)      # (B, K)

        if valid_mask is not None:
            if valid_mask.dim() == 1:
                valid_mask = valid_mask.unsqueeze(0)
            logits = logits.masked_fill(valid_mask == 0, float("-inf"))

        probs = torch.softmax(logits, dim=-1)
        # An all-masked state has no legal action; fall back to uniform so the
        # distribution stays well defined rather than producing NaNs.
        degenerate = torch.isnan(probs).any(dim=-1, keepdim=True)
        if bool(degenerate.any()):
            probs = torch.where(degenerate, torch.full_like(probs, 1.0 / self.k_pairs), probs)

        # Value from the masked mean of pair embeddings, so padding slots and the
        # ordering of candidates do not shift the estimate.
        if valid_mask is not None:
            weights = valid_mask.unsqueeze(-1)
            pooled = (embedded * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)
        else:
            pooled = embedded.mean(dim=1)
        value = self.critic_head(pooled)                    # (B, 1)

        return probs, value
