"""BenchmarkRun — a saved record of one scheduler-benchmark replay.

Every time a user runs the live benchmark simulator, we persist the run params
and a compact result summary so the Benchmarks page can show a "previous runs"
log (observability) and runs stay reproducible by seed.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id:            Mapped[int]      = mapped_column(primary_key=True, index=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id:       Mapped[int]      = mapped_column(Integer, index=True, default=0)
    username:      Mapped[str]      = mapped_column(String(64), default="")
    n_jobs:        Mapped[int]      = mapped_column(Integer, default=0)
    seed:          Mapped[int]      = mapped_column(Integer, default=0)
    winner:        Mapped[str]      = mapped_column(String(32), default="ppo")
    # PPO row headline metrics for the log table
    ppo_latency_ms: Mapped[float]   = mapped_column(Float, default=0.0)
    ppo_util_pct:   Mapped[float]   = mapped_column(Float, default=0.0)
    ppo_balance:    Mapped[float]   = mapped_column(Float, default=0.0)
    ppo_sla:        Mapped[int]     = mapped_column(Integer, default=0)
    # Improvement of PPO vs baseline average (latency %, positive = better)
    latency_gain_pct: Mapped[float] = mapped_column(Float, default=0.0)
    # Full result rows as JSON (for re-rendering charts from history)
    rows_json:     Mapped[str]      = mapped_column(Text, default="[]")
