"""Cluster + node metrics API — live snapshot, polled by the /clusters page."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

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
