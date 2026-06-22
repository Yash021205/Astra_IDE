"""
B3 improvement — a GLOBAL LSTM forecaster trained on windows pooled across MANY
functions, instead of one model per function.

Why: a per-function LSTM on a sparse function sees only ~30 inter-arrival gaps —
too few to learn, so a simple histogram beats it. A single model trained on
thousands of functions learns shared demand/idle patterns and transfers to any
function (including sparse and unseen ones). Each series is z-scored by its OWN
mean/std before pooling, so the model learns scale-free shape, not magnitudes.

Device-aware: uses CUDA automatically if available (e.g. the college GPU box) —
the same script just runs faster there. Mini-batched so it scales to many
functions × many days.
"""
from __future__ import annotations

import numpy as np

from ml.prewarming.forecaster import make_windows, all_metrics

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader
    from ml.prewarming.forecaster import _LSTM
    _TORCH = True
except ImportError:  # pragma: no cover
    _TORCH = False


def _zscore(s):
    s = np.asarray(s, float)
    mu, sd = float(s.mean()), float(s.std() or 1.0)
    return (s - mu) / sd, mu, sd


class GlobalForecaster:
    def __init__(self, input_len: int = 60, hidden: int = 32, layers: int = 2,
                 horizon: int = 1, epochs: int = 30, lr: float = 1e-3,
                 batch_size: int = 256, seed: int = 0, device: str | None = None):
        if not _TORCH:
            raise ImportError("PyTorch required: pip install -r ml/requirements.txt")
        self.input_len = input_len
        self.hidden = hidden
        self.layers = layers
        self.horizon = horizon
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.seed = seed
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None

    def fit(self, series_list, log=False) -> "GlobalForecaster":
        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        Xs, Ys = [], []
        for s in series_list:
            z, _, _ = _zscore(s)
            X, Y = make_windows(z, self.input_len, self.horizon)
            if len(X):
                Xs.append(X); Ys.append(Y)
        if not Xs:
            raise ValueError("no trainable windows across the given series")
        X = np.vstack(Xs); Y = np.vstack(Ys)
        Xt = torch.tensor(X, dtype=torch.float32).unsqueeze(-1)
        Yt = torch.tensor(Y, dtype=torch.float32)
        dl = DataLoader(TensorDataset(Xt, Yt), batch_size=self.batch_size, shuffle=True)
        self.model = _LSTM(self.hidden, self.layers, self.horizon).to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        loss_fn = nn.MSELoss()
        self.model.train()
        for ep in range(self.epochs):
            tot = 0.0
            for xb, yb in dl:
                xb, yb = xb.to(self.device), yb.to(self.device)
                opt.zero_grad()
                loss = loss_fn(self.model(xb), yb)
                loss.backward(); opt.step()
                tot += loss.item()
            if log and (ep % max(1, self.epochs // 5) == 0 or ep == self.epochs - 1):
                print(f"    epoch {ep:3d}  loss={tot / len(dl):.4f}  "
                      f"[{len(X)} windows, device={self.device}]")
        return self

    def _predict_z(self, Xz):
        self.model.eval()
        with torch.no_grad():
            xt = torch.tensor(Xz, dtype=torch.float32).unsqueeze(-1).to(self.device)
            return self.model(xt).cpu().numpy()

    def walk_forward(self, series):
        s = np.asarray(series, float)
        z, mu, sd = _zscore(s)
        X, _ = make_windows(z, self.input_len, self.horizon)
        if len(X) == 0:
            return np.array([])
        return self._predict_z(X)[:, 0] * sd + mu

    def evaluate(self, series) -> dict:
        s = np.asarray(series, float)
        y = s[self.input_len:len(s) - self.horizon + 1]
        yhat = self.walk_forward(s)
        n = min(len(y), len(yhat))
        return all_metrics(y[:n], yhat[:n]) if n else {"smape": 0, "rmse": 0,
                                                       "n_rmse": 0, "r2": 0}
