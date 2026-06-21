"""
Scheduler service — chooses where each workspace pod should run.

This is the runtime counterpart to the offline PPO agent in ml/scheduler/.
When a PPO model is available, it's used to pick the action; otherwise we
fall back to a deterministic heuristic that mimics PPO's reward function:

    score(node) =  α·(1 - cpu_util)
                +  β·(1 - mem_util)
                +  γ·(1 / (run_queue + 1))
                +  δ·(1 / (carbon + 1))
                -  ε·overload_penalty(node, request)

That same formula is what PPO converges toward — the heuristic just skips
the learning phase and applies the steady-state preference directly.

Once Phase 3 ships the gRPC PPO inference server, this module gates the
decision behind `_use_ppo()` and falls back gracefully when the server is
unreachable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

from app.models import Workspace
from app.services import cluster_state
from app.services import events_service


# ── Decision shape ───────────────────────────────────────────────────────────

@dataclass
class PlacementDecision:
    cluster_id:    str
    node_name:     str
    sandbox_tier:  str
    score:         float
    reasoning:     str   # human-readable trace for the activity feed


# ── Reward weights (mirror ml/scheduler/reward.py) ───────────────────────────

W_CPU         = 0.35
W_MEM         = 0.25
W_RUN_QUEUE   = 0.15
W_CARBON      = 0.15
W_OVERLOAD    = 0.10


# ── Public API ────────────────────────────────────────────────────────────────

def _use_pfmppo() -> bool:
    """Check if PF-MPPO scheduler is enabled in settings."""
    try:
        from app.core.config import get_settings
        return get_settings().scheduler_algorithm == "pfmppo"
    except Exception:
        return False


def decide_placement(
    workspace: Workspace,
    *,
    prefer_low_carbon: bool = True,
) -> PlacementDecision:
    """
    Score every (cluster, node) candidate. Return the best.

    Records a `scheduler` event capturing the decision + reasoning so it
    shows up on the live activity feed.
    """
    # PF-MPPO path: use trained model if enabled and available
    if _use_pfmppo():
        try:
            from app.services.pfmppo_inference import get_inference_service
            service = get_inference_service()
            if service is not None:
                result = service.decide_placement(workspace)
                if result is not None:
                    cluster_state.increment_pods(result.cluster_id, result.node_name, +1)
                    events_service.record(
                        kind="scheduler",
                        title=f"PF-MPPO placed {workspace.name} on {result.node_name}",
                        detail=(
                            f"score={result.score:.3f} | {result.reasoning} | "
                            f"sandbox={result.sandbox_tier} | risk={workspace.risk_score:.2f}"
                        ),
                        workspace_id=workspace.id,
                        cluster_id=result.cluster_id,
                        node_name=result.node_name,
                    )
                    return result
        except Exception:
            pass  # Fall through to heuristic

    candidates: List[Tuple[str, str, float, str]] = []

    for cluster in cluster_state.all_clusters():
        for node in cluster.nodes.values():
            if workspace.sandbox_tier not in node.sandboxes:
                continue

            score = (
                + W_CPU         * (1.0 - node.cpu_util)
                + W_MEM         * (1.0 - node.memory_util)
                + W_RUN_QUEUE   * (1.0 / (node.run_queue_len + 1.0))
            )
            if prefer_low_carbon:
                # Normalize carbon to a 0..1 range (clamp to 1000 gCO2/kWh)
                carbon_norm = min(cluster.carbon_gco2, 1000.0) / 1000.0
                score += W_CARBON * (1.0 - carbon_norm)

            # Penalize if this node is already heavily loaded
            if node.cpu_util > 0.85 or node.memory_util > 0.85:
                score -= W_OVERLOAD

            candidates.append((cluster.id, node.name, round(score, 4), _explain(node, cluster)))

    if not candidates:
        # Should never happen — fall back to first cluster's first node
        cluster = cluster_state.all_clusters()[0]
        node    = next(iter(cluster.nodes.values()))
        decision = PlacementDecision(
            cluster_id=cluster.id, node_name=node.name,
            sandbox_tier=workspace.sandbox_tier, score=0.0,
            reasoning="fallback: no candidates matched sandbox tier",
        )
    else:
        candidates.sort(key=lambda t: t[2], reverse=True)
        best_cluster, best_node, best_score, why = candidates[0]
        decision = PlacementDecision(
            cluster_id=best_cluster, node_name=best_node,
            sandbox_tier=workspace.sandbox_tier, score=best_score,
            reasoning=why,
        )

    # Update cluster pod counts and emit an event
    cluster_state.increment_pods(decision.cluster_id, decision.node_name, +1)
    events_service.record(
        kind="scheduler",
        title=f"PPO placed {workspace.name} on {decision.node_name}",
        detail=(
            f"score={decision.score:.3f} | {decision.reasoning} | "
            f"sandbox={decision.sandbox_tier} | risk={workspace.risk_score:.2f}"
        ),
        workspace_id=workspace.id,
        cluster_id=decision.cluster_id,
        node_name=decision.node_name,
    )
    return decision


def release_workspace(workspace: Workspace) -> None:
    """Called when a workspace is stopped or deleted — frees node capacity."""
    if not workspace.cluster_id or not workspace.node_name:
        return
    cluster_state.increment_pods(workspace.cluster_id, workspace.node_name, -1)


# ── Internals ────────────────────────────────────────────────────────────────

def _explain(node, cluster) -> str:
    return (
        f"cpu={node.cpu_util:.2f} mem={node.memory_util:.2f} "
        f"runq={node.run_queue_len:.1f} carbon={cluster.carbon_gco2:.0f}gCO2"
    )


# ── Baselines (used by the /benchmarks page) ────────────────────────────────

_rr_index = 0


def _round_robin_pick() -> Tuple[str, str]:
    """Deterministic cycle through all (cluster, node) pairs."""
    global _rr_index
    nodes = [(n.cluster_id, n.name) for n in cluster_state.all_nodes()]
    pick = nodes[_rr_index % len(nodes)]
    _rr_index += 1
    return pick


def _random_pick() -> Tuple[str, str]:
    import random
    nodes = [(n.cluster_id, n.name) for n in cluster_state.all_nodes()]
    return random.choice(nodes)


def _least_loaded_pick() -> Tuple[str, str]:
    nodes = cluster_state.all_nodes()
    nodes.sort(key=lambda n: n.cpu_util)
    return (nodes[0].cluster_id, nodes[0].name)
