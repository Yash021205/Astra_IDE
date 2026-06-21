"""
Benchmarks API — comparison of the ASTRA PPO-style scheduler against
classical baselines (Round-Robin, Random, FIFO, Least-Loaded).

The numbers returned here are produced by a synthetic workload simulator
(no actual cluster needed). When a real PPO model is available, the same
endpoint will run an online comparison against k3s' default scheduler.

The simulator builds a sequence of `n_jobs` workloads with realistic CPU /
memory / risk distributions, replays each algorithm over the same current
cluster snapshot, and aggregates latency / utilization / energy stats.
"""
from __future__ import annotations

import json
import random
import statistics
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, BenchmarkRun
from app.schemas.event import BenchmarkRow, BenchmarkReport
from app.services import cluster_state
from app.services import scheduler_service

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


# ── Synthetic workload generator ─────────────────────────────────────────────

def _make_workload(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    workload = []
    for i in range(n):
        workload.append({
            "id":         i,
            "cpu_req":    round(rng.uniform(0.1, 1.5), 2),
            "mem_req":    round(rng.uniform(64, 2048), 0),
            "risk":       round(rng.random(), 2),
            # Pick a "true" optimal sandbox tier; doesn't drive placement but
            # we report it for context.
            "true_tier":  rng.choice(["runc", "gvisor", "firecracker"]),
        })
    return workload


# ── Per-algorithm simulator ──────────────────────────────────────────────────

def _simulate(algorithm: str, workload: list[dict]) -> BenchmarkRow:
    """
    Replay the workload against a fresh shallow copy of the cluster state
    using the chosen algorithm. Measure latency, utilization, energy.
    """
    # Shallow copy of node loads — we don't want to mutate the live state
    nodes: list[dict] = []
    for n in cluster_state.all_nodes():
        nodes.append({
            "cluster_id":  n.cluster_id,
            "name":        n.name,
            "cpu_util":    n.cpu_util,
            "memory_util": n.memory_util,
            "run_queue":   n.run_queue_len,
            "carbon":      cluster_state.get_cluster(n.cluster_id).carbon_gco2,
        })

    latencies: list[float] = []
    sla_violations = 0
    energy = 0.0

    rr_idx = 0

    for job in workload:
        candidates = [n for n in nodes]

        if algorithm == "ppo":
            # Score-based pick (mirrors the live scheduler heuristic)
            best = max(candidates, key=lambda n: (
                + 0.35 * (1 - n["cpu_util"])
                + 0.25 * (1 - n["memory_util"])
                + 0.15 * (1 / (n["run_queue"] + 1))
                + 0.15 * (1 - min(n["carbon"], 1000) / 1000)
                - (0.10 if n["cpu_util"] > 0.85 else 0)
            ))
        elif algorithm == "round_robin":
            best = candidates[rr_idx % len(candidates)]
            rr_idx += 1
        elif algorithm == "random":
            best = random.choice(candidates)
        elif algorithm == "fifo":
            # Always pick the first node — worst-case
            best = candidates[0]
        elif algorithm == "least_loaded":
            best = min(candidates, key=lambda n: n["cpu_util"])
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        # Synthesize a latency from node load + carbon:
        latency_ms = (
            120 +                                # base K8s pod start
            best["cpu_util"]  * 1800 +           # contention penalty
            best["run_queue"] * 250 +
            (350 if job["risk"] > 0.7 else      # firecracker overhead
              150 if job["risk"] > 0.3 else 60)
        )
        latencies.append(latency_ms)
        if latency_ms > 5000:
            sla_violations += 1

        # Update node load
        best["cpu_util"]    = min(1.0, best["cpu_util"]    + job["cpu_req"]  * 0.20)
        best["memory_util"] = min(1.0, best["memory_util"] + job["mem_req"]  / 8192 * 0.5)
        best["run_queue"]   = best["run_queue"] + 0.4

        # Energy proxy: load × carbon
        energy += best["cpu_util"] * (best["carbon"] / 1000.0) * 0.01

    avg_util = statistics.mean(n["cpu_util"] for n in nodes)
    # Balance score: 1 − stddev(cpu_util) / mean(cpu_util)
    if avg_util > 0:
        balance = max(0.0, 1.0 - statistics.pstdev(n["cpu_util"] for n in nodes) / avg_util)
    else:
        balance = 1.0

    return BenchmarkRow(
        algorithm        = algorithm,
        avg_latency_ms   = round(statistics.mean(latencies), 1),
        p95_latency_ms   = round(_percentile(latencies, 95), 1),
        utilization_pct  = round(avg_util * 100, 1),
        balance_score    = round(balance, 3),
        energy_kwh       = round(energy, 3),
        sla_violations   = sla_violations,
    )


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


# ── HTTP endpoint ────────────────────────────────────────────────────────────

@router.get("/run", response_model=BenchmarkReport)
def run_benchmark(
    n_jobs: int = Query(200, ge=20, le=2000, description="Number of synthetic workloads"),
    seed:   int = Query(42,  description="RNG seed for reproducibility"),
    user:   User = Depends(get_current_user),
    db:     Session = Depends(get_db),
) -> BenchmarkReport:
    workload   = _make_workload(n_jobs, seed)
    algorithms = ["ppo", "least_loaded", "round_robin", "random", "fifo"]
    rows = [_simulate(alg, workload) for alg in algorithms]

    _persist_run(db, user, n_jobs, seed, rows)

    return BenchmarkReport(
        description=(
            f"Replay of {n_jobs} synthetic workloads against the current "
            "cluster snapshot. Lower latency, higher utilization and balance, "
            "lower energy are better."
        ),
        rows=rows,
        metadata={
            "n_jobs":      str(n_jobs),
            "seed":        str(seed),
            "algorithms":  ", ".join(algorithms),
            "nodes":       str(len(cluster_state.all_nodes())),
        },
    )


# ── Run history (observability: log of previous runs) ────────────────────────

class BenchmarkRunOut(BaseModel):
    id:               int
    created_at:       datetime
    username:         str
    n_jobs:           int
    seed:             int
    winner:           str
    ppo_latency_ms:   float
    ppo_util_pct:     float
    ppo_balance:      float
    ppo_sla:          int
    latency_gain_pct: float

    class Config:
        from_attributes = True


def _persist_run(db: Session, user: User, n_jobs: int, seed: int, rows: list[BenchmarkRow]) -> None:
    ppo = next((r for r in rows if r.algorithm == "ppo"), None)
    if ppo is None:
        return
    baselines = [r for r in rows if r.algorithm != "ppo"]
    base_lat = statistics.mean(r.avg_latency_ms for r in baselines) if baselines else ppo.avg_latency_ms
    gain = ((base_lat - ppo.avg_latency_ms) / base_lat * 100) if base_lat else 0.0
    # winner = lowest avg latency
    winner = min(rows, key=lambda r: r.avg_latency_ms).algorithm
    try:
        db.add(BenchmarkRun(
            user_id=user.id, username=user.username, n_jobs=n_jobs, seed=seed,
            winner=winner,
            ppo_latency_ms=ppo.avg_latency_ms, ppo_util_pct=ppo.utilization_pct,
            ppo_balance=ppo.balance_score, ppo_sla=ppo.sla_violations,
            latency_gain_pct=round(gain, 1),
            rows_json=json.dumps([r.model_dump() for r in rows]),
        ))
        db.commit()
    except Exception:
        db.rollback()


@router.get("/history", response_model=List[BenchmarkRunOut])
def benchmark_history(
    limit: int = Query(20, ge=1, le=100),
    _user: User = Depends(get_current_user),
    db:    Session = Depends(get_db),
) -> List[BenchmarkRun]:
    return (db.query(BenchmarkRun)
              .order_by(BenchmarkRun.created_at.desc())
              .limit(limit).all())
