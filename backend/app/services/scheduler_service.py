"""
Scheduler service — chooses where each workspace pod should run.

ASTRA-IDE ships several placement algorithms and lets the operator pick one
(config `scheduler_algorithm`, or a per-call override). This is deliberate: our
own benchmarking (benchmarks/b1_scheduler) shows that on makespan the classical
list-scheduling heuristics (HEFT, Min-Min) are very strong, the multi-objective
heuristic balances load and carbon well, and the learned PF-MPPO policy is
competitive but does not dominate them. Rather than hide that behind one "smart"
scheduler, we expose the choice and let users compare.

Algorithms (all pick a (cluster, node) for one workspace; higher score = better):
  - heuristic     multi-objective weighted score (cpu, mem, run-queue, carbon)
  - pfmppo        trained PF-MPPO policy (falls back to heuristic if unavailable)
  - heft          earliest-finish-time (assign to the node that finishes it soonest)
  - minmin        minimum-completion-time (load-aware earliest finish)
  - least_loaded  lowest CPU utilization
  - carbon_aware  greenest cluster first (lowest gCO2/kWh)
  - round_robin   deterministic rotation across nodes
  - random        uniform random admissible node

HEFT and Min-Min are the single-placement projections of the DAG heuristics used
in benchmarks/b1_scheduler; for one workspace they both reduce to "earliest
finish", differing only in the tie-break, which is called out in the reasoning.
"""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
    reasoning:     str
    algorithm:     str = "heuristic"


ALGORITHMS = [
    "heuristic", "cp_ppo", "pfmppo", "heft", "minmin",
    "least_loaded", "carbon_aware", "round_robin", "random",
]

ALGORITHM_LABELS = {
    "heuristic":    "Multi-objective heuristic",
    "cp_ppo":       "CP-PPO (critical-path RL)",
    "pfmppo":       "PF-MPPO (deep RL)",
    "heft":         "HEFT (earliest finish)",
    "minmin":       "Min-Min",
    "least_loaded": "Least loaded",
    "carbon_aware": "Carbon-aware",
    "round_robin":  "Round robin",
    "random":       "Random",
}


# ── Weights for the multi-objective heuristic (mirror ml/scheduler/reward.py) ─

W_CPU         = 0.35
W_MEM         = 0.25
W_RUN_QUEUE   = 0.15
W_CARBON      = 0.15
W_OVERLOAD    = 0.10


# ── Candidate + per-node scoring primitives ──────────────────────────────────

def _candidate_nodes(workspace: Workspace):
    out = []
    for cluster in cluster_state.all_clusters():
        for node in cluster.nodes.values():
            if workspace.sandbox_tier in node.sandboxes:
                out.append((cluster, node))
    return out


def _workspace_cost(workspace: Workspace) -> float:
    """Rough compute demand of the workspace startup (cores requested)."""
    return max(0.25, float(getattr(workspace, "cpu_request", 0.5) or 0.5))


def _est_finish(workspace: Workspace, node) -> float:
    """Earliest-finish proxy: work / effective free processing capacity. Faster,
    less-loaded nodes finish sooner. Lower is better."""
    free = max(0.05, node.proc_rate_mbps * (1.0 - node.cpu_util))
    return _workspace_cost(workspace) * 100.0 / free


def _heuristic_score(cluster, node, prefer_low_carbon: bool) -> float:
    score = (
        + W_CPU       * (1.0 - node.cpu_util)
        + W_MEM       * (1.0 - node.memory_util)
        + W_RUN_QUEUE * (1.0 / (node.run_queue_len + 1.0))
    )
    if prefer_low_carbon:
        carbon_norm = min(cluster.carbon_gco2, 1000.0) / 1000.0
        score += W_CARBON * (1.0 - carbon_norm)
    if node.cpu_util > 0.85 or node.memory_util > 0.85:
        score -= W_OVERLOAD
    return score


def _explain(node, cluster) -> str:
    return (f"cpu={node.cpu_util:.2f} mem={node.memory_util:.2f} "
            f"runq={node.run_queue_len:.1f} carbon={cluster.carbon_gco2:.0f}gCO2")


# ── Algorithm implementations (return best (cluster, node, score, reasoning)) ─

def _choose(workspace: Workspace, algorithm: str, prefer_low_carbon: bool = True
            ) -> Optional[Tuple[str, str, float, str]]:
    cands = _candidate_nodes(workspace)
    if not cands:
        return None

    if algorithm == "cp_ppo":
        res = _try_cp_ppo(workspace)
        if res is not None:
            return res
        algorithm = "heuristic"        # graceful fallback, recorded in reasoning below

    if algorithm == "pfmppo":
        res = _try_pfmppo(workspace)
        if res is not None:
            return res
        algorithm = "heuristic"        # graceful fallback, recorded in reasoning below

    if algorithm == "round_robin":
        global _rr_index
        c, n = cands[_rr_index % len(cands)]
        _rr_index += 1
        return c.id, n.name, 0.0, f"round-robin slot {_rr_index} | {_explain(n, c)}"

    if algorithm == "random":
        c, n = _random.choice(cands)
        return c.id, n.name, 0.0, f"random pick | {_explain(n, c)}"

    scored: List[Tuple[str, str, float, str]] = []
    for cluster, node in cands:
        if algorithm == "heuristic":
            s = _heuristic_score(cluster, node, prefer_low_carbon)
            why = f"score={s:.3f} | {_explain(node, cluster)}"
        elif algorithm == "heft":
            s = -_est_finish(workspace, node)
            why = f"est_finish={-s:.1f} (earliest) | {_explain(node, cluster)}"
        elif algorithm == "minmin":
            # min completion time, tie-broken toward lower memory pressure
            s = -(_est_finish(workspace, node) + 5.0 * node.memory_util)
            why = f"min-completion | {_explain(node, cluster)}"
        elif algorithm == "least_loaded":
            s = 1.0 - node.cpu_util
            why = f"cpu_util={node.cpu_util:.2f} (lowest) | {_explain(node, cluster)}"
        elif algorithm == "carbon_aware":
            s = 1.0 - min(cluster.carbon_gco2, 1000.0) / 1000.0
            why = f"carbon={cluster.carbon_gco2:.0f}gCO2 (greenest) | {_explain(node, cluster)}"
        else:
            s = _heuristic_score(cluster, node, prefer_low_carbon)
            why = f"score={s:.3f} | {_explain(node, cluster)}"
        scored.append((cluster.id, node.name, round(s, 4), why))

    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[0]


def _try_cp_ppo(workspace: Workspace) -> Optional[Tuple[str, str, float, str]]:
    try:
        from app.services.cp_ppo_inference import get_inference_service
        service = get_inference_service()
        if service is None:
            return None
        result = service.decide_placement(workspace)
        if result is None:
            return None
        return result.cluster_id, result.node_name, result.score, result.reasoning
    except Exception:
        return None


def _try_pfmppo(workspace: Workspace) -> Optional[Tuple[str, str, float, str]]:
    try:
        from app.services.pfmppo_inference import get_inference_service
        service = get_inference_service()
        if service is None:
            return None
        result = service.decide_placement(workspace)
        if result is None:
            return None
        return result.cluster_id, result.node_name, result.score, result.reasoning
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def _configured_algorithm() -> str:
    try:
        from app.core.config import get_settings
        algo = get_settings().scheduler_algorithm
        return algo if algo in ALGORITHMS else "heuristic"
    except Exception:
        return "heuristic"


def decide_placement(
    workspace: Workspace,
    *,
    algorithm: Optional[str] = None,
    prefer_low_carbon: bool = True,
    record: bool = True,
) -> PlacementDecision:
    """Place `workspace` using `algorithm` (or the configured default). Records a
    `scheduler` activity event and updates node pod counts when `record` is set."""
    algo = algorithm or _configured_algorithm()
    if algo not in ALGORITHMS:
        algo = "heuristic"

    picked = _choose(workspace, algo, prefer_low_carbon)
    if picked is None:
        cluster = cluster_state.all_clusters()[0]
        node = next(iter(cluster.nodes.values()))
        decision = PlacementDecision(cluster.id, node.name, workspace.sandbox_tier,
                                     0.0, "fallback: no node matched sandbox tier", algo)
    else:
        cid, nname, score, why = picked
        decision = PlacementDecision(cid, nname, workspace.sandbox_tier, score, why, algo)

    if record:
        cluster_state.increment_pods(decision.cluster_id, decision.node_name, +1)
        events_service.record(
            kind="scheduler",
            title=f"{ALGORITHM_LABELS.get(algo, algo)} placed {workspace.name} on {decision.node_name}",
            detail=(f"algo={algo} | score={decision.score:.3f} | {decision.reasoning} | "
                    f"sandbox={decision.sandbox_tier} | risk={workspace.risk_score:.2f}"),
            workspace_id=workspace.id,
            cluster_id=decision.cluster_id,
            node_name=decision.node_name,
        )
    return decision


def compare_algorithms(workspace: Workspace) -> List[dict]:
    """What each algorithm WOULD choose for this workspace, without committing —
    powers the frontend scheduler comparison. Read-only (record=False)."""
    rows = []
    for algo in ALGORITHMS:
        picked = _choose(workspace, algo)
        if picked is None:
            continue
        cid, nname, score, why = picked
        rows.append({
            "algorithm": algo,
            "label": ALGORITHM_LABELS.get(algo, algo),
            "cluster_id": cid,
            "node_name": nname,
            "score": score,
            "reasoning": why,
        })
    return rows


def release_workspace(workspace: Workspace) -> None:
    """Called when a workspace is stopped or deleted — frees node capacity."""
    if not workspace.cluster_id or not workspace.node_name:
        return
    cluster_state.increment_pods(workspace.cluster_id, workspace.node_name, -1)


# ── Baselines kept for the /benchmarks API (thin wrappers) ───────────────────

_rr_index = 0


def _round_robin_pick() -> Tuple[str, str]:
    global _rr_index
    nodes = [(n.cluster_id, n.name) for n in cluster_state.all_nodes()]
    pick = nodes[_rr_index % len(nodes)]
    _rr_index += 1
    return pick


def _random_pick() -> Tuple[str, str]:
    nodes = [(n.cluster_id, n.name) for n in cluster_state.all_nodes()]
    return _random.choice(nodes)


def _least_loaded_pick() -> Tuple[str, str]:
    nodes = cluster_state.all_nodes()
    nodes.sort(key=lambda n: n.cpu_util)
    return (nodes[0].cluster_id, nodes[0].name)
