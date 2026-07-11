"""
CP-PPO inference service for live scheduling decisions.

Serves the critical-path-guided policy (`PairScoringNetwork`) trained by
`benchmarks/b1_scheduler/eval_cp_ppo.py`. For one workspace it scores every
admissible live node with the shared per-pair network and picks the best -- the
greedy policy, which already beat HEFT in the benchmark. Best-of-N search is a
training/benchmark construct (it needs a full task DAG) and is not used for a
single live placement.

The 16 per-pair features mirror the trained rich encoding. A live workspace is a
single task with no predecessors, so the predecessor-wait and transfer features
are zero; the remaining features (resource slack, processing rate, compute time,
earliest finish time, and the gap to the best available finish time) carry the
signal. This is a deliberate, disclosed sim-to-real approximation: the policy was
trained on multi-task DAGs, and it is applied here to a single placement.

Falls back to None (caller uses the heuristic) if the artifact is missing or torch
is unavailable.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.models import Workspace
from app.services import cluster_state
from app.services.scheduler_service import PlacementDecision

logger = logging.getLogger(__name__)

FEATURES_PER_PAIR = 16

_torch = None
_network_cls = None
_template_fn = None
_aggregates_fn = None
_initialized = False


def _ensure_imports():
    global _torch, _network_cls, _template_fn, _aggregates_fn, _initialized
    if _initialized:
        return
    _initialized = True
    try:
        import torch
        _torch = torch
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from ml.scheduler.pfmppo.pair_network import PairScoringNetwork
        from ml.scheduler.pfmppo.workspace_templates import (
            get_template_for_language,
            compute_template_aggregates,
        )
        _network_cls = PairScoringNetwork
        _template_fn = get_template_for_language
        _aggregates_fn = compute_template_aggregates
    except ImportError as e:
        logger.warning("CP-PPO dependencies not available: %s", e)


class CPPPOInferenceService:
    """Thread-safe singleton serving the CP-PPO placement policy."""

    def __init__(self, model_path: str, k_pairs: int = 24):
        _ensure_imports()
        self._lock = threading.Lock()
        self.k_pairs = k_pairs
        self.features_per_pair = FEATURES_PER_PAIR
        self.network = None
        self._load_model(model_path)

    def _load_model(self, model_path: str) -> None:
        if _torch is None or _network_cls is None:
            logger.error("PyTorch or PairScoringNetwork not available")
            return
        path = Path(model_path)
        if not path.is_absolute():
            # Resolve a repo-relative path against both layouts: parents[2] is /app
            # in the container image (where ml/ is copied to /app/ml), parents[3] is
            # the repo root when running the backend straight from a checkout.
            here = Path(__file__).resolve()
            candidates = [here.parents[2] / model_path, here.parents[3] / model_path]
            path = next((c for c in candidates if c.exists()), candidates[0])
        if not path.exists():
            logger.info("CP-PPO model not found (%s); using heuristic fallback", path)
            return
        try:
            checkpoint = _torch.load(str(path), map_location="cpu", weights_only=True)
            self.k_pairs = int(checkpoint.get("k_pairs", self.k_pairs))
            self.features_per_pair = int(checkpoint.get("features_per_pair", FEATURES_PER_PAIR))
            self.network = _network_cls(features_per_pair=self.features_per_pair,
                                        k_pairs=self.k_pairs)
            self.network.load_state_dict(checkpoint["network"])
            self.network.eval()
            logger.info("CP-PPO model loaded from %s (k=%d, f=%d)",
                        path, self.k_pairs, self.features_per_pair)
        except Exception as e:
            logger.error("Failed to load CP-PPO model: %s", e)
            self.network = None

    def _get_workspace_aggregates(self, workspace: Workspace) -> dict:
        if _template_fn and _aggregates_fn:
            language = getattr(workspace, "language", "generic") or "generic"
            agg = _aggregates_fn(_template_fn(language))
            cpu_scale = max(workspace.cpu_request / 0.5, 1.0)
            agg["peak_cpu"] *= cpu_scale
            agg["peak_mem"] = max(agg["peak_mem"], workspace.memory_request)
            return agg
        return {
            "peak_cpu": workspace.cpu_request, "peak_mem": workspace.memory_request,
            "total_disk": 1024.0, "total_data_mb": 50.0,
            "critical_path_duration": 1.0, "num_subtasks": 1, "depth": 0,
        }

    def decide_placement(self, workspace: Workspace) -> Optional[PlacementDecision]:
        if self.network is None or _torch is None:
            return None
        try:
            with self._lock:
                return self._infer(workspace)
        except Exception as e:
            logger.warning("CP-PPO inference error: %s", e)
            return None

    def _infer(self, workspace: Workspace) -> Optional[PlacementDecision]:
        candidates: List[Tuple[str, cluster_state.Node]] = []
        for node in cluster_state.all_nodes():
            if workspace.sandbox_tier in node.sandboxes:
                candidates.append((node.cluster_id, node))
        if not candidates:
            return None

        agg = self._get_workspace_aggregates(workspace)
        window = candidates[:self.k_pairs]

        # Earliest finish time per candidate (single task: no wait, no transfer).
        efts = []
        for _, node in window:
            proc = max(node.proc_rate_mbps, 1.0)
            compute = agg["total_data_mb"] / proc
            eft = compute + agg["critical_path_duration"]
            efts.append((compute, eft))
        best_eft = min(e for _, e in efts) if efts else 0.0
        max_eft = max(e for _, e in efts) if efts else 1.0

        state = np.zeros(self.k_pairs * self.features_per_pair, dtype=np.float32)
        for i, (cid, node) in enumerate(window):
            off = i * self.features_per_pair
            avail_cpu = node.cpu_cap * (1.0 - node.cpu_util)
            avail_mem = node.mem_cap * (1.0 - node.memory_util)
            avail_disk = node.disk_cap * 0.8
            compute, eft = efts[i]
            state[off + 0] = avail_cpu - agg["peak_cpu"]
            state[off + 1] = (avail_mem - agg["peak_mem"]) / 1000.0
            state[off + 2] = (avail_disk - agg["total_disk"]) / 10000.0
            state[off + 3] = node.bandwidth_mbps / 1000.0
            state[off + 4] = node.proc_rate_mbps / 100.0
            state[off + 5] = agg["critical_path_duration"] / 30.0
            state[off + 6] = agg["total_data_mb"] / 500.0
            state[off + 7] = (agg["num_subtasks"] - 1) / 10.0
            state[off + 8] = (agg["num_subtasks"] - 1) / 20.0
            state[off + 9] = agg["depth"] / 10.0
            state[off + 10] = 0.0                              # wait (no predecessors)
            state[off + 11] = 0.0                              # transfer
            state[off + 12] = compute / 30.0
            state[off + 13] = eft / 30.0
            state[off + 14] = eft / max_eft if max_eft > 0 else 0.0
            state[off + 15] = (eft - best_eft) / 30.0

        valid_mask = np.zeros(self.k_pairs, dtype=np.float32)
        valid_mask[:len(window)] = 1.0

        state_t = _torch.tensor(state, dtype=_torch.float32).unsqueeze(0)
        mask_t = _torch.tensor(valid_mask, dtype=_torch.float32).unsqueeze(0)
        with _torch.no_grad():
            probs, _ = self.network(state_t, mask_t)

        action = int(probs.squeeze(0).argmax().item())
        action = min(action, len(window) - 1)
        cid, node = window[action]
        score = float(probs.squeeze(0)[action].item())
        return PlacementDecision(
            cluster_id=cid,
            node_name=node.name,
            sandbox_tier=workspace.sandbox_tier,
            score=score,
            reasoning=f"CP-PPO greedy action={action} prob={score:.3f}",
        )


_instance: Optional[CPPPOInferenceService] = None
_instance_lock = threading.Lock()


def get_inference_service() -> Optional[CPPPOInferenceService]:
    global _instance
    if _instance is not None:
        return _instance
    with _instance_lock:
        if _instance is not None:
            return _instance
        from app.core.config import get_settings
        settings = get_settings()
        model_path = getattr(settings, "cp_ppo_model_path", "")
        if not model_path:
            return None
        inst = CPPPOInferenceService(
            model_path=model_path,
            k_pairs=getattr(settings, "cp_ppo_k_pairs", 24),
        )
        if inst.network is None:
            return None
        _instance = inst
        return _instance
