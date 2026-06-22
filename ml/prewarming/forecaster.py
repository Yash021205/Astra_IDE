"""
B3 Stage 1 — LSTM invocation forecaster (reproduces the LSTM baseline of
"Transformer-Based Model for Cold Start Mitigation in FaaS", IEEE, Tables I/II).

Task: given a function's recent invocation counts, forecast the next step(s).
The forecast drives the pre-warm pool size and the adaptive keep-alive window
(policy.py). Config follows the paper's "standard LSTM, similar layers/hidden
dims to the Transformer": input window ~200, hidden 32, 2 layers (all tunable).

Metrics match the paper §V: sMAPE, RMSE, Normalized RMSE, R².
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import torch
    import torch.nn as nn
    _TORCH = True
except ImportError:  # pragma: no cover
    _TORCH = False


# ── Metrics (paper §V) ─────────────────────────────────────────────────────────

def smape(y, yhat) -> float:
    """Symmetric MAPE in [0, 2] (paper's primary error metric)."""
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    denom = (np.abs(y) + np.abs(yhat)) / 2.0
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs(yhat - y)[mask] / denom[mask]))


def rmse(y, yhat) -> float:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    return float(np.sqrt(np.mean((yhat - y) ** 2)))


def normalized_rmse(y, yhat) -> float:
    """RMSE / (max-min) of the true series (paper's N-RMSE)."""
    y = np.asarray(y, float)
    rng = float(y.max() - y.min())
    return rmse(y, yhat) / rng if rng > 0 else 0.0


def r2_score(y, yhat) -> float:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def all_metrics(y, yhat) -> dict:
    return {"smape": smape(y, yhat), "rmse": rmse(y, yhat),
            "n_rmse": normalized_rmse(y, yhat), "r2": r2_score(y, yhat)}


# ── Windowing ──────────────────────────────────────────────────────────────────

def make_windows(series, input_len: int, horizon: int = 1):
    """Sliding supervised windows: X[i] = series[i:i+L], y[i] = next `horizon`."""
    s = np.asarray(series, float)
    X, Y = [], []
    for i in range(len(s) - input_len - horizon + 1):
        X.append(s[i:i + input_len])
        Y.append(s[i + input_len:i + input_len + horizon])
    if not X:
        return np.empty((0, input_len)), np.empty((0, horizon))
    return np.asarray(X), np.asarray(Y)


# ── Baseline + model ───────────────────────────────────────────────────────────

def persistence_forecast(series, input_len: int, horizon: int = 1):
    """Naive 'repeat-last' baseline: ŷ_t = y_{t-1}. The LSTM must beat this."""
    s = np.asarray(series, float)
    y, yhat = [], []
    for i in range(len(s) - input_len - horizon + 1):
        last = s[i + input_len - 1]
        y.append(s[i + input_len:i + input_len + horizon])
        yhat.append(np.full(horizon, last))
    return np.asarray(y), np.asarray(yhat)


if _TORCH:
    class _LSTM(nn.Module):
        def __init__(self, hidden: int, layers: int, horizon: int):
            super().__init__()
            self.lstm = nn.LSTM(1, hidden, layers, batch_first=True)
            self.head = nn.Linear(hidden, horizon)

        def forward(self, x):                      # x: (B, T, 1)
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])        # (B, horizon)


@dataclass
class InvocationForecaster:
    """Windowed univariate LSTM forecaster with z-score normalisation."""
    input_len: int = 64
    hidden: int = 32
    layers: int = 2
    horizon: int = 1
    epochs: int = 80
    lr: float = 1e-2
    seed: int = 0

    def __post_init__(self):
        if not _TORCH:
            raise ImportError("PyTorch required: pip install -r ml/requirements.txt")
        self._mu = 0.0
        self._sd = 1.0
        self._model = None

    def fit(self, series) -> "InvocationForecaster":
        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        s = np.asarray(series, float)
        self._mu, self._sd = float(s.mean()), float(s.std() or 1.0)
        z = (s - self._mu) / self._sd
        X, Y = make_windows(z, self.input_len, self.horizon)
        if len(X) == 0:
            raise ValueError("series shorter than input_len + horizon")
        Xt = torch.tensor(X, dtype=torch.float32).unsqueeze(-1)   # (N, L, 1)
        Yt = torch.tensor(Y, dtype=torch.float32)                 # (N, horizon)
        self._model = _LSTM(self.hidden, self.layers, self.horizon)
        opt = torch.optim.Adam(self._model.parameters(), lr=self.lr)
        loss_fn = nn.MSELoss()
        self._model.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            loss = loss_fn(self._model(Xt), Yt)
            loss.backward()
            opt.step()
        return self

    def _predict_z(self, Xz):
        self._model.eval()
        with torch.no_grad():
            xt = torch.tensor(Xz, dtype=torch.float32).unsqueeze(-1)
            return self._model(xt).numpy()

    def predict_next(self, history):
        """One forecast for the most recent `input_len` points (denormalised)."""
        h = np.asarray(history, float)[-self.input_len:]
        z = (h - self._mu) / self._sd
        out = self._predict_z(z[None, :])[0]
        return out * self._sd + self._mu

    def walk_forward(self, series):
        """One-step predictions aligned to series[input_len:] for evaluation."""
        z = (np.asarray(series, float) - self._mu) / self._sd
        X, _ = make_windows(z, self.input_len, self.horizon)
        pred_z = self._predict_z(X)[:, 0]            # first-step forecast
        return pred_z * self._sd + self._mu

    def evaluate(self, series) -> dict:
        s = np.asarray(series, float)
        y = s[self.input_len:len(s) - self.horizon + 1]
        yhat = self.walk_forward(s)
        n = min(len(y), len(yhat))
        return all_metrics(y[:n], yhat[:n])
