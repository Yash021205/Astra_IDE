"""Pydantic schemas for the events + metrics APIs."""
from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel


class EventOut(BaseModel):
    id:           int
    timestamp:    datetime
    kind:         str
    title:        str
    detail:       str
    workspace_id: int
    cluster_id:   str
    node_name:    str

    class Config:
        from_attributes = True


class EventList(BaseModel):
    total: int
    items: List[EventOut]


class NodeMetrics(BaseModel):
    cluster_id:    str
    node_name:     str
    cpu_util:      float       # 0..1
    memory_util:   float       # 0..1
    network_kbps:  float
    run_queue_len: float
    active_pods:   int


class ClusterMetrics(BaseModel):
    cluster_id:   str
    location:     str
    carbon_gco2:  float
    nodes:        List[NodeMetrics]
    total_pods:   int


class MetricsSnapshot(BaseModel):
    timestamp: datetime
    clusters:  List[ClusterMetrics]


class BenchmarkRow(BaseModel):
    algorithm:           str           # ppo / round_robin / random / fifo / least_loaded
    avg_latency_ms:      float
    p95_latency_ms:      float
    utilization_pct:     float
    balance_score:       float         # 0..1, higher = more balanced
    energy_kwh:          float
    sla_violations:      int


class BenchmarkReport(BaseModel):
    description: str
    rows:        List[BenchmarkRow]
    metadata:    Dict[str, str]
