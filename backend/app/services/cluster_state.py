"""
In-memory cluster state — a small mock of a multi-cluster Kubernetes
federation that the scheduler decides over.

Two clusters (matches the diagram on the /clusters page):
  - cluster-a  (DK-DK1, Denmark — lower carbon)
  - cluster-b  (IN-NO,  India   — higher carbon)
Each has two worker nodes. Per-node telemetry (cpu, mem, network, run_queue)
drifts randomly via the background telemetry loop to simulate live eBPF feed.

This module is the single source of truth for runtime cluster state. When
the real eBPF + Karmada layer comes online (Phase 3+), this becomes a thin
in-memory cache populated from the actual gRPC telemetry daemon.
"""
from __future__ import annotations

import logging
import os
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Node:
    cluster_id:    str
    name:          str
    cpu_util:      float = 0.20
    memory_util:   float = 0.30
    network_kbps:  float = 64.0
    run_queue_len: float = 1.0
    active_pods:   int   = 0
    # supported sandbox tiers on this node (labels in real K8s)
    sandboxes:     List[str] = field(default_factory=lambda: ["runc", "gvisor", "firecracker"])
    # PF-MPPO fields (Eq 2): VM capacity and power characteristics
    cpu_cap:         float = 4.0
    mem_cap:         float = 8192.0
    disk_cap:        float = 102400.0
    bandwidth_mbps:  float = 1000.0
    proc_rate_mbps:  float = 200.0
    power_static_w:  float = 11.0
    power_max_w:     float = 200.0


@dataclass
class Cluster:
    id:           str
    location:     str
    zone:         str        # electricityMaps zone code
    nodes:        Dict[str, Node]
    carbon_gco2:  float = 200.0   # cached, refreshed by carbon service


# ── Singleton store ──────────────────────────────────────────────────────────

_lock = threading.RLock()

def _nodes(cluster_id: str, prefix: str, specs: list[tuple[float, float, float]]) -> Dict[str, Node]:
    out: Dict[str, Node] = {}
    for i, (cpu, mem, rq) in enumerate(specs, start=1):
        name = f"node-{prefix}-{i}"
        out[name] = Node(cluster_id=cluster_id, name=name,
                         cpu_util=cpu, memory_util=mem, run_queue_len=rq)
    return out


# Four federated member clusters (Karmada). Carbon intensity varies by region so
# the carbon-aware policy (B6) has something to prefer; the PPO scheduler (B1)
# sees all of them as one pool.
_CLUSTERS: Dict[str, Cluster] = {
    "cluster-a": Cluster(
        id="cluster-a", location="DK-DK1 (Denmark West)", zone="DK-DK1",
        carbon_gco2=95.0,
        nodes=_nodes("cluster-a", "a", [(0.25, 0.35, 1.2), (0.40, 0.50, 2.0), (0.32, 0.41, 1.5)]),
    ),
    "cluster-b": Cluster(
        id="cluster-b", location="IN-NO (India North)", zone="IN-NO",
        carbon_gco2=710.0,
        nodes=_nodes("cluster-b", "b", [(0.20, 0.30, 0.8), (0.55, 0.45, 3.1), (0.38, 0.52, 1.9)]),
    ),
    "cluster-c": Cluster(
        id="cluster-c", location="US-CAL (California)", zone="US-CAL-CISO",
        carbon_gco2=280.0,
        nodes=_nodes("cluster-c", "c", [(0.30, 0.38, 1.4), (0.46, 0.55, 2.3)]),
    ),
    "cluster-d": Cluster(
        id="cluster-d", location="SG (Singapore)", zone="SG",
        carbon_gco2=430.0,
        nodes=_nodes("cluster-d", "d", [(0.22, 0.33, 1.0), (0.51, 0.49, 2.7)]),
    ),
}


def all_clusters() -> List[Cluster]:
    with _lock:
        return list(_CLUSTERS.values())


def all_nodes() -> List[Node]:
    with _lock:
        return [n for c in _CLUSTERS.values() for n in c.nodes.values()]


def get_cluster(cluster_id: str) -> Optional[Cluster]:
    with _lock:
        return _CLUSTERS.get(cluster_id)


def get_node(cluster_id: str, node_name: str) -> Optional[Node]:
    c = get_cluster(cluster_id)
    if c is None:
        return None
    return c.nodes.get(node_name)


def set_carbon_intensity(cluster_id: str, value: float) -> None:
    with _lock:
        if cluster_id in _CLUSTERS:
            _CLUSTERS[cluster_id].carbon_gco2 = value


def increment_pods(cluster_id: str, node_name: str, delta: int = 1) -> None:
    with _lock:
        node = get_node(cluster_id, node_name)
        if node is not None:
            node.active_pods = max(0, node.active_pods + delta)
            # Reflect load impact
            node.cpu_util      = min(1.0, node.cpu_util      + 0.05 * delta)
            node.memory_util   = min(1.0, node.memory_util   + 0.04 * delta)
            node.run_queue_len = max(0.0, node.run_queue_len + 0.3  * delta)


# ── Telemetry drift (called by background task) ─────────────────────────────

_rng = random.Random(42)

def tick_telemetry() -> None:
    """Drift every node's metrics slightly. Models eBPF samples arriving."""
    with _lock:
        for cluster in _CLUSTERS.values():
            for node in cluster.nodes.values():
                # CPU: gentle pull toward 0.5 + noise. Higher load if more pods.
                target_cpu = 0.20 + 0.10 * node.active_pods + _rng.gauss(0, 0.04)
                node.cpu_util = clip(node.cpu_util * 0.85 + target_cpu * 0.15, 0.02, 1.0)

                # Memory: similar but slower
                target_mem = 0.30 + 0.08 * node.active_pods + _rng.gauss(0, 0.03)
                node.memory_util = clip(node.memory_util * 0.9 + target_mem * 0.1, 0.05, 1.0)

                # Run queue: bursty
                node.run_queue_len = max(0.0,
                    node.run_queue_len * 0.8 + _rng.uniform(0, 2.0) * (0.5 + node.cpu_util),
                )

                # Network: pulses
                base_net = 64 + 256 * node.cpu_util
                node.network_kbps = clip(
                    node.network_kbps * 0.7 + base_net * 0.3 + _rng.uniform(-30, 80),
                    0.0, 5000.0,
                )


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ── Real Kubernetes metrics reader (gated; replaces the simulator on-cluster) ──
# Enable by setting ASTRA_USE_K8S_METRICS=1 in a cluster with metrics-server.
# When active, telemetry_loop calls refresh_from_kubernetes() instead of the
# random-drift tick_telemetry(). Falls back to the simulator on any error, so the
# single-VM demo is unaffected until a real cluster is present.

def _use_k8s() -> bool:
    return os.getenv("ASTRA_USE_K8S_METRICS") == "1"


def _parse_cpu(q: str) -> float:
    """Kubernetes CPU quantity -> cores. Handles n (nano), u (micro), m (milli)."""
    q = str(q)
    if q.endswith("n"):
        return float(q[:-1]) / 1e9
    if q.endswith("u"):
        return float(q[:-1]) / 1e6
    if q.endswith("m"):
        return float(q[:-1]) / 1e3
    return float(q)


def _parse_mem(q: str) -> float:
    """Kubernetes memory quantity -> MiB."""
    q = str(q)
    units = {"Ki": 1 / 1024, "Mi": 1.0, "Gi": 1024.0, "Ti": 1024 * 1024}
    for suf, mul in units.items():
        if q.endswith(suf):
            return float(q[:-len(suf)]) * mul
    return float(q) / (1024 * 1024)   # bare bytes


def refresh_from_kubernetes() -> bool:
    """Rebuild the store from live node capacity (CoreV1) + usage (metrics.k8s.io).
    Returns True if it refreshed real data, False to fall back to the simulator."""
    try:
        from kubernetes import client, config
    except ImportError:
        return False
    try:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        core = client.CoreV1Api()
        custom = client.CustomObjectsApi()
        nodes = core.list_node().items
        usage = {i["metadata"]["name"]: i["usage"] for i in
                 custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")["items"]}
    except Exception as e:
        logger.warning("k8s metrics read failed, using simulator: %s", e)
        return False

    zone = os.getenv("ASTRA_CLUSTER_ZONE", "IN-NO")
    new_nodes: Dict[str, Node] = {}
    for n in nodes:
        name = n.metadata.name
        alloc = n.status.allocatable or {}
        cpu_cap = _parse_cpu(alloc.get("cpu", "1"))
        mem_cap = _parse_mem(alloc.get("memory", "1024Mi"))
        u = usage.get(name, {})
        cpu_used = _parse_cpu(u.get("cpu", "0"))
        mem_used = _parse_mem(u.get("memory", "0"))
        # sandbox tiers available per node label (runc always; runsc/kata if labelled)
        labels = n.metadata.labels or {}
        tiers = ["runc"]
        if labels.get("sandbox.astra-ide.io/gvisor") == "true":
            tiers.append("gvisor")
        if labels.get("sandbox.astra-ide.io/firecracker") == "true":
            tiers.append("firecracker")
        new_nodes[name] = Node(
            cluster_id="cluster-local", name=name,
            cpu_util=clip(cpu_used / cpu_cap if cpu_cap else 0.0, 0.0, 1.0),
            memory_util=clip(mem_used / mem_cap if mem_cap else 0.0, 0.0, 1.0),
            sandboxes=tiers, cpu_cap=cpu_cap, mem_cap=mem_cap,
        )
    if not new_nodes:
        return False
    with _lock:
        carbon = _CLUSTERS.get("cluster-local").carbon_gco2 if "cluster-local" in _CLUSTERS else 500.0
        _CLUSTERS.clear()
        _CLUSTERS["cluster-local"] = Cluster(
            id="cluster-local", location=os.getenv("ASTRA_CLUSTER_LOCATION", "on-cluster"),
            zone=zone, nodes=new_nodes, carbon_gco2=carbon)
    return True


# ── Snapshot for the /metrics API ────────────────────────────────────────────

def snapshot() -> Dict[str, dict]:
    with _lock:
        return {
            cid: {
                "id":           c.id,
                "location":     c.location,
                "zone":         c.zone,
                "carbon_gco2":  c.carbon_gco2,
                "total_pods":   sum(n.active_pods for n in c.nodes.values()),
                "nodes": [
                    {
                        "name":          n.name,
                        "cluster_id":    n.cluster_id,
                        "cpu_util":      round(n.cpu_util, 3),
                        "memory_util":   round(n.memory_util, 3),
                        "network_kbps":  round(n.network_kbps, 1),
                        "run_queue_len": round(n.run_queue_len, 2),
                        "active_pods":   n.active_pods,
                        "sandboxes":     n.sandboxes,
                    }
                    for n in c.nodes.values()
                ],
            }
            for cid, c in _CLUSTERS.items()
        }
