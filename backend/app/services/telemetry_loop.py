"""
Background telemetry loop — runs as an asyncio task started from the FastAPI
lifespan. Every few seconds it:

  1. Drifts per-node metrics in cluster_state
  2. Emits a small batch of `ebpf`/`carbon`/`prewarm`/`collab` events
     into the SchedulerEvent table for the activity feed
  3. Periodically refreshes carbon intensity from the live electricityMaps API
  4. Prunes the event log so it stays small (keeps the most recent 500)

When real Tetragon + electricityMaps integrations land (Phase 3+), this loop
either disappears or becomes a thin consumer of those real streams.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from app.services import cluster_state
from app.services import events_service
from app.services.carbon_service import get_carbon_service
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# How often each kind of loop fires
TICK_TELEMETRY_S       = 4
TICK_EVENT_EMIT_S      = 5
TICK_CARBON_REFRESH_S  = 600   # 10 min — stays under electricityMaps quota
TICK_PRUNE_S           = 300

_rng = random.Random(42)


async def telemetry_main_loop() -> None:
    """Drives all sub-loops. Cancels safely when the FastAPI app shuts down."""
    logger.info("Telemetry loop starting")
    try:
        events_service.record(
            kind="system", title="ASTRA-IDE scheduler online",
            detail="PPO policy loaded |eBPF probes attached |activity stream live",
        )
    except Exception as e:
        logger.warning("Could not write startup event: %s", e)

    last_drift  = 0.0
    last_event  = 0.0
    last_carbon = 0.0
    last_prune  = 0.0
    t = 0.0

    while True:
        await asyncio.sleep(1)
        t += 1.0

        try:
            if t - last_drift > TICK_TELEMETRY_S:
                # On a real cluster (ASTRA_USE_K8S_METRICS=1) read live node metrics;
                # otherwise drift the in-memory simulator.
                if not (cluster_state._use_k8s() and cluster_state.refresh_from_kubernetes()):
                    cluster_state.tick_telemetry()
                last_drift = t

            if t - last_event > TICK_EVENT_EMIT_S:
                _emit_random_event()
                last_event = t

            if t - last_carbon > TICK_CARBON_REFRESH_S:
                _refresh_carbon()
                last_carbon = t

            if t - last_prune > TICK_PRUNE_S:
                _prune()
                last_prune = t
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Telemetry loop tick failed: %s", e)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _emit_random_event() -> None:
    nodes = cluster_state.all_nodes()
    if not nodes:
        return
    node = _rng.choice(nodes)
    cluster = cluster_state.get_cluster(node.cluster_id)
    assert cluster is not None

    r = _rng.random()
    if r < 0.5:
        events_service.record(
            kind="ebpf",
            title=f"sched_switch |{node.name}",
            detail=(
                f"cpu={node.cpu_util:.2f} mem={node.memory_util:.2f} "
                f"runq={node.run_queue_len:.1f} net={node.network_kbps:.0f}KiB/s"
            ),
            cluster_id=cluster.id, node_name=node.name,
        )
    elif r < 0.75:
        events_service.record(
            kind="prewarm",
            title="LSTM prewarmer |scoring active users",
            detail=f"top probability {_rng.uniform(0.62, 0.94):.2f} |warmed pods=2",
        )
    elif r < 0.9:
        events_service.record(
            kind="carbon",
            title=f"Carbon read |{cluster.zone}",
            detail=f"{cluster.carbon_gco2:.0f} gCO2/kWh |{_carbon_grade(cluster.carbon_gco2)}",
            cluster_id=cluster.id,
        )
    else:
        events_service.record(
            kind="collab",
            title="Yjs awareness flush",
            detail=f"rooms updated |clients={_rng.randint(1, 8)}",
        )


def _refresh_carbon() -> None:
    """Hit electricityMaps once per zone and update the cached cluster state."""
    svc = get_carbon_service()
    for cluster in cluster_state.all_clusters():
        try:
            reading = svc.get_intensity(cluster.zone)
            cluster_state.set_carbon_intensity(cluster.id, reading.carbon_intensity)
        except Exception as e:
            logger.warning("Carbon refresh failed for %s: %s", cluster.zone, e)


def _prune() -> None:
    db = SessionLocal()
    try:
        deleted = events_service.prune_old(db, keep_last=500)
        if deleted:
            logger.info("Pruned %d old events", deleted)
    finally:
        db.close()


def _carbon_grade(g: float) -> str:
    if g < 100:  return "clean"
    if g < 300:  return "moderate"
    if g < 600:  return "fossil-heavy"
    return "high carbon"


# ── Lifespan helpers (called from app.main) ─────────────────────────────────

_task: Optional[asyncio.Task] = None


async def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(telemetry_main_loop())


async def stop() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
