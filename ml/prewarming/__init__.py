"""
B3 — LSTM predictive pre-warming (cold-start mitigation).

Paper-grounded replacement for the earlier synthetic session-classifier.
Reproduces the LSTM baseline of "Transformer-Based Model for Cold Start
Mitigation in FaaS" (IEEE) on the Azure Functions 2019 trace, then uses the
forecast to size a pre-warm pool and adapt the keep-alive window so cold starts
drop (paper Table III: ~50-80% fewer cold starts vs a fixed 10-min window).

  forecaster.py  — windowed LSTM + sMAPE/RMSE/N-RMSE/R² metrics (Stage 1)
  policy.py      — demand→prewarm count, idle→keep-alive window, cold-start sim
"""
from ml.prewarming.forecaster import (
    InvocationForecaster, smape, rmse, normalized_rmse, r2_score, all_metrics,
    make_windows, persistence_forecast,
)
from ml.prewarming.global_forecaster import GlobalForecaster

__all__ = [
    "InvocationForecaster", "GlobalForecaster", "smape", "rmse", "normalized_rmse",
    "r2_score", "all_metrics", "make_windows", "persistence_forecast",
]
