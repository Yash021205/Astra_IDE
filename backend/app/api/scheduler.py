"""
Scheduler API — expose the selectable placement algorithms and a live, read-only
comparison of what each one would choose for a given workload. Powers the
frontend scheduler explorer and the benchmarks page.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Query

from app.services import scheduler_service, cluster_state

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/algorithms")
def list_algorithms():
    """All placement algorithms the operator can pick from."""
    return {
        "algorithms": [
            {"id": a, "label": scheduler_service.ALGORITHM_LABELS.get(a, a)}
            for a in scheduler_service.ALGORITHMS
        ],
        "default": scheduler_service._configured_algorithm(),
    }


@router.get("/compare")
def compare(
    cpu: float = Query(0.5, ge=0.1, le=16),
    memory: int = Query(512, ge=128, le=32768),
    tier: str = Query("runc"),
    language: str = Query("python"),
    name: str = Query("preview"),
):
    """What each algorithm WOULD choose for this workload right now (no commit).
    Returns one row per algorithm with the chosen node, score and reasoning, plus
    the current cluster snapshot so the frontend can visualise the decision."""
    ws = SimpleNamespace(
        id=0, name=name, sandbox_tier=tier, language=language,
        cpu_request=cpu, memory_request=memory, risk_score=0.0,
        network_access=False, filesystem_write=True,
    )
    rows = scheduler_service.compare_algorithms(ws)  # type: ignore[arg-type]
    return {
        "workload": {"cpu": cpu, "memory": memory, "tier": tier, "language": language},
        "results": rows,
        "clusters": cluster_state.snapshot(),
    }
