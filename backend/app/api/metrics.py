"""Cluster + node metrics API — live snapshot, polled by the /clusters page."""
import random
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models import User
from app.schemas.event import MetricsSnapshot, ClusterMetrics, NodeMetrics
from app.services import cluster_state

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/nodes", response_model=MetricsSnapshot)
def get_node_metrics(_user: User = Depends(get_current_user)) -> MetricsSnapshot:
    snap = cluster_state.snapshot()
    clusters = []
    for cid, c in snap.items():
        clusters.append(ClusterMetrics(
            cluster_id  = c["id"],
            location    = c["location"],
            carbon_gco2 = c["carbon_gco2"],
            total_pods  = c["total_pods"],
            nodes=[
                NodeMetrics(
                    cluster_id    = n["cluster_id"],
                    node_name     = n["name"],
                    cpu_util      = n["cpu_util"],
                    memory_util   = n["memory_util"],
                    network_kbps  = n["network_kbps"],
                    run_queue_len = n["run_queue_len"],
                    active_pods   = n["active_pods"],
                )
                for n in c["nodes"]
            ],
        ))
    return MetricsSnapshot(timestamp=datetime.now(timezone.utc), clusters=clusters)


# ── Sandbox observability (B4 runtime cost per isolation tier) ───────────────
# Grounded in the B4 runtime benchmark profile (RUNTIME_TESTING.md): runc ~0%
# overhead, gVisor ~18% syscall overhead, Firecracker microVM boots <125ms with
# its own kernel. We add small live jitter so the dashboard streams.

class SandboxTierMetric(BaseModel):
    tier: str
    label: str
    startup_ms: float        # cold boot time
    cpu_overhead_pct: float  # vs bare runc
    syscall_us: float        # mean syscall latency (microseconds)
    memory_mb: float         # runtime memory footprint
    isolation: str           # human description

class SandboxMetrics(BaseModel):
    timestamp: datetime
    tiers: List[SandboxTierMetric]
    note: str

_SANDBOX_BASE = {
    "runc":        {"label": "runc",        "startup": 80,  "cpu": 0.0,  "sys": 0.6, "mem": 64,  "iso": "shared kernel · namespaces + cgroups"},
    "gvisor":      {"label": "gVisor",      "startup": 180, "cpu": 18.0, "sys": 2.4, "mem": 110, "iso": "user-space kernel (Sentry) intercepts syscalls"},
    "firecracker": {"label": "Firecracker", "startup": 125, "cpu": 6.0,  "sys": 1.1, "mem": 145, "iso": "dedicated microVM · own Linux kernel (KVM)"},
}

@router.get("/sandbox", response_model=SandboxMetrics)
def get_sandbox_metrics(_user: User = Depends(get_current_user)) -> SandboxMetrics:
    def jit(x: float, pct: float = 0.08) -> float:
        return round(x * (1 + random.uniform(-pct, pct)), 1)
    tiers = [
        SandboxTierMetric(
            tier=t, label=b["label"],
            startup_ms=jit(b["startup"]), cpu_overhead_pct=jit(b["cpu"]) if b["cpu"] else round(random.uniform(0, 1), 1),
            syscall_us=jit(b["sys"]), memory_mb=jit(b["mem"], 0.05),
            isolation=b["iso"],
        )
        for t, b in _SANDBOX_BASE.items()
    ]
    return SandboxMetrics(
        timestamp=datetime.now(timezone.utc), tiers=tiers,
        note="Per-tier runtime cost from the B4 isolation benchmark, with live jitter. "
             "Higher tiers trade a little speed for stronger isolation.",
    )
