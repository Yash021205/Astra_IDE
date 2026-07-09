"""
Strengthened list-scheduling heuristics for the PF-MPPO environment.

The original benchmark pickers estimated a pair's cost as `data/proc_rate + t_dur`,
which ignores both the communication delay from predecessors on other VMs and the
wait for predecessors that have not finished yet. That understates the cost of the
very placements a scheduler must avoid, so it weakens HEFT and Min-Min against
whatever is being compared to them.

This module computes the *exact* finish time the simulator will produce for a
(task, VM) pair -- see `PFMPPOEnv._execute_placement` -- and builds HEFT and Min-Min
on top of it, so the baselines are as strong as the environment allows.

All pickers share one signature so the benchmark can use them interchangeably:

    pick(env, valid_indices: List[int]) -> int
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ml.scheduler.pfmppo.dag import Task, VM
from ml.scheduler.pfmppo.graph_algorithms import upward_rank
from ml.scheduler.pfmppo.math_models import communication_delay, computation_time

# Upward ranks are a property of the DAG, not of the schedule so far, so they are
# computed once per episode and cached against the DAG object.
_rank_cache: Dict[int, Dict[str, float]] = {}


def episode_upward_rank(env) -> Dict[str, float]:
    """Upward rank for the DAG currently loaded in `env`, cached per episode."""
    key = id(env.dag)
    cached = _rank_cache.get(key)
    if cached is None:
        cached = upward_rank(env.dag, env.vms)
        # The cache only ever needs the current episode; keep it from growing.
        _rank_cache.clear()
        _rank_cache[key] = cached
    return cached


def placement_timing(env, task: Task, vm: VM) -> Tuple[float, float, float, float]:
    """Exact (wait, transfer, compute, finish_time) for placing `task` on `vm` now.

    Mirrors `PFMPPOEnv._execute_placement` under whichever time model the env is
    running, so a heuristic built on this optimises the quantity the simulator will
    actually charge it.
    """
    vm_by_id = {v.node_id: v for v in env.vms}
    compute = computation_time(task.data_size_mb, vm.proc_rate_mbps)
    listsched = getattr(env, "time_model", "legacy") == "listsched"

    transfer = 0.0
    wait = 0.0
    data_ready = 0.0
    for parent_id in env.dag.get_predecessors(task.task_id):
        parent_vm_id = env.task_assignments.get(parent_id)
        delay = 0.0
        if parent_vm_id and parent_vm_id != vm.node_id:
            parent_task = env.dag.get_task(parent_id)
            parent_vm = vm_by_id.get(parent_vm_id)
            if parent_task and parent_vm:
                delay = communication_delay(
                    parent_task.data_size_mb,
                    parent_vm.bandwidth_mbps,
                    vm.bandwidth_mbps,
                )
        transfer = max(transfer, delay)
        finished_at = env.task_finish_times.get(parent_id, 0.0)
        data_ready = max(data_ready, finished_at + delay)
        wait = max(wait, finished_at - env.current_time)

    if listsched:
        vm_free = env.vm_ready.get(vm.node_id, 0.0)
        start = max(vm_free, data_ready)
        return max(0.0, start - vm_free), transfer, compute, start + compute + task.t_dur

    wait = max(0.0, wait)
    finish = env.current_time + wait + transfer + compute + task.t_dur
    return wait, transfer, compute, finish


def true_eft(env, task: Task, vm: VM) -> float:
    """Earliest finish time of `task` on `vm`, including transfer and wait."""
    return placement_timing(env, task, vm)[3]


# ── Pickers ───────────────────────────────────────────────────────────────────

def pick_minmin(env, valid: List[int]) -> int:
    """Min-Min: over every ready (task, VM) pair, take the globally minimum EFT."""
    pairs = env.admissible_pairs
    return min(valid, key=lambda i: true_eft(env, pairs[i][0], pairs[i][1]))


def pick_heft(env, valid: List[int]) -> int:
    """HEFT: schedule the ready task with the highest upward rank, on the VM that
    finishes it earliest.

    This is the real HEFT rule: the priority comes from the critical path
    (`upward_rank`), not from the environment's structural ordering, and the VM is
    chosen by true earliest finish time.
    """
    pairs = env.admissible_pairs
    rank = episode_upward_rank(env)
    best_task = max(valid, key=lambda i: rank.get(pairs[i][0].task_id, 0.0))
    target = pairs[best_task][0].task_id
    candidates = [i for i in valid if pairs[i][0].task_id == target]
    return min(candidates, key=lambda i: true_eft(env, pairs[i][0], pairs[i][1]))


def pick_maxmin(env, valid: List[int]) -> int:
    """Max-Min: among each task's best VM, schedule the task whose best finish is
    latest. Complements Min-Min on DAGs with a few long tasks."""
    pairs = env.admissible_pairs
    best_per_task: Dict[str, Tuple[int, float]] = {}
    for i in valid:
        task, vm = pairs[i]
        eft = true_eft(env, task, vm)
        cur = best_per_task.get(task.task_id)
        if cur is None or eft < cur[1]:
            best_per_task[task.task_id] = (i, eft)
    return max(best_per_task.values(), key=lambda p: p[1])[0]


def pick_greedy(env, valid: List[int]) -> int:
    """Greedy: take the environment's own top-priority admissible pair."""
    return valid[0]


def make_random_picker(seed: int = 0):
    """Seeded random picker, so the Random baseline reproduces run to run."""
    import numpy as np
    rng = np.random.default_rng(seed)

    def pick(env, valid: List[int]) -> int:
        return int(rng.choice(valid))

    return pick


# The expert used to warm-start the learned policy. Min-Min on true EFT is the
# strongest single-step greedy rule available in this environment.
expert_pick = pick_minmin
