"""
B6 — carbon-aware scheduling (PCAPS-style temporal shifting of deferrable work to
low-carbon windows). Reproduces the carbon-reduction / completion-time tradeoff of
Lechowicz et al. on a real grid carbon trace.
"""
from ml.carbon.scheduler import (
    Job, carbon_agnostic, carbon_aware, total_carbon, mean_delay, evaluate,
    diurnal_trace,
)

__all__ = [
    "Job", "carbon_agnostic", "carbon_aware", "total_carbon", "mean_delay",
    "evaluate", "diurnal_trace",
]
