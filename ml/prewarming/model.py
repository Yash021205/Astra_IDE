"""
LSTM-based session-start predictor.

Architecture (from Section 6.2 of the spec):
  Input  : sequence of (hour_sin, hour_cos, day_of_week, language_id) per past session
  Layer 1: LSTM(128, return_sequences=True)
  Layer 2: LSTM(64)
  Dense  : Linear(32) → ReLU
  Output : Linear(1)  → Sigmoid → P(session_start in next 15 min)

Targets:
  Precision/Recall/F1 > 0.75 on held-out users (per spec Week 7).

This module defines the model; training is in train.py, data prep in dataset.py.
"""
from __future__ import annotations

import sys


try:
    import torch
    from torch import nn
    _TORCH = True
except ImportError:
    _TORCH = False
    torch = None  # type: ignore[assignment]
    nn    = None  # type: ignore[assignment]


if _TORCH:

    class PrewarmingLSTM(nn.Module):
        def __init__(
            self,
            input_size:    int = 4,
            hidden_size_1: int = 128,
            hidden_size_2: int = 64,
            dense_size:    int = 32,
            dropout:       float = 0.2,
        ):
            super().__init__()
            self.lstm1 = nn.LSTM(input_size,    hidden_size_1, batch_first=True)
            self.lstm2 = nn.LSTM(hidden_size_1, hidden_size_2, batch_first=True)
            self.dropout = nn.Dropout(dropout)
            self.fc1   = nn.Linear(hidden_size_2, dense_size)
            self.relu  = nn.ReLU()
            self.fc2   = nn.Linear(dense_size, 1)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # x: (batch, seq_len, input_size)
            out, _ = self.lstm1(x)
            out, _ = self.lstm2(out)
            out    = out[:, -1, :]            # take final time step
            out    = self.dropout(out)
            out    = self.relu(self.fc1(out))
            return self.sigmoid(self.fc2(out)).squeeze(-1)   # (batch,)


    def build_model(**kwargs) -> PrewarmingLSTM:
        return PrewarmingLSTM(**kwargs)

else:

    class PrewarmingLSTM:  # type: ignore[no-redef]
        def __init__(self, *a, **k):
            raise ImportError("PyTorch is not installed. Install: pip install -r ml/requirements.txt")

    def build_model(**kwargs):
        raise ImportError("PyTorch is not installed. Install: pip install -r ml/requirements.txt")
