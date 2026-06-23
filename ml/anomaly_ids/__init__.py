"""
Graph-based container intrusion detection — implementation of Iacovazzi & Raza,
"Ensemble of Random and Isolation Forests for Graph-Based Intrusion Detection in
Containers", IEEE CSR 2022 (DOI 10.1109/CSR54599.2022.9850307).

3-stage pipeline (paper §IV):
  1. syscall sequence -> bigram-weighted directed graph -> anonymous-walk
     embedding (length 4 -> 15 features = Bell number B4)
  2. Random Forest classifier (100 estimators) over N normal workload classes
  3. Ensemble of N Isolation Forests (100 estimators), Eq.1 anomaly score +
     the §IV-B-4 decision rules

Runtime input (the syscall stream) arrives from the eBPF/Tetragon layer (B2);
until that is live we validate the pipeline on synthetic separable data.
"""
from ml.anomaly_ids.embedding import (
    generate_anonymous_walks, build_syscall_graph, anonymous_walk_embedding,
    EMBED_DIM,
)
from ml.anomaly_ids.detector import ContainerIDS, Decision

__all__ = [
    "generate_anonymous_walks", "build_syscall_graph", "anonymous_walk_embedding",
    "EMBED_DIM", "ContainerIDS", "Decision",
]
