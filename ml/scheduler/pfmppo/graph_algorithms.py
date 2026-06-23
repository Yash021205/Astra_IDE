"""
Graph algorithms for PF-MPPO (Algorithms 1, 2, and admission control).

Algorithm 1: Parse task features (succ_nums, desc_nums, task_layers) via BFS.
Algorithm 2: Global prioritization by weight = succ_nums + desc_nums + task_layers.
Admission Control (Eq 17): Filter (task, VM) pairs by predecessor completion + resources.
"""
from __future__ import annotations

from collections import deque, defaultdict
from typing import Dict, List, Set, Tuple

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG


class CyclicDependencyError(Exception):
    """Raised when a cyclic dependency is detected in the task DAG."""
    pass


def parse_task_features(dag: TaskDAG) -> Dict[str, Dict[str, int]]:
    """
    Algorithm 1: Compute succ_nums, desc_nums, task_layers for every task.

    - succ_nums: number of immediate successors
    - desc_nums: total number of reachable descendants (BFS)
    - task_layers: longest path from any root to this task (topological DP)
    """
    if dag.has_cycle():
        raise CyclicDependencyError("DAG contains a cycle")

    features: Dict[str, Dict[str, int]] = {}

    for task in dag.get_all_tasks():
        tid = task.task_id

        # Immediate successors
        succ_nums = len(dag.get_successors(tid))

        # All descendants via BFS
        descendants: Set[str] = set()
        queue = deque(dag.get_successors(tid))
        while queue:
            curr = queue.popleft()
            if curr not in descendants:
                descendants.add(curr)
                queue.extend(dag.get_successors(curr))
        desc_nums = len(descendants)

        features[tid] = {"succ_nums": succ_nums, "desc_nums": desc_nums, "task_layers": 0}

    # Compute task_layers: longest path from any root to each task
    # Using reverse topological order DP
    topo_order = _topological_sort(dag)
    layer: Dict[str, int] = {tid: 0 for tid in features}

    for tid in topo_order:
        for succ_id in dag.get_successors(tid):
            if layer[succ_id] < layer[tid] + 1:
                layer[succ_id] = layer[tid] + 1

    for tid in features:
        features[tid]["task_layers"] = layer[tid]

    return features


def global_prioritization(dag: TaskDAG, features: Dict[str, Dict[str, int]]) -> List[Task]:
    """
    Algorithm 2: Sort tasks by weight = succ_nums + desc_nums + task_layers (descending).

    Updates task.weight, task.succ_nums, task.desc_nums, task.task_layers in place.
    Returns tasks sorted by decreasing weight (highest priority first).
    """
    tasks = dag.get_all_tasks()

    for task in tasks:
        feat = features[task.task_id]
        task.succ_nums = feat["succ_nums"]
        task.desc_nums = feat["desc_nums"]
        task.task_layers = feat["task_layers"]
        task.weight = feat["succ_nums"] + feat["desc_nums"] + feat["task_layers"]

    tasks.sort(key=lambda t: t.weight, reverse=True)
    return tasks


def filter_admissible_pairs(
    sorted_tasks: List[Task],
    vms: List[VM],
    completed: Set[str],
    dag: TaskDAG,
    k: int = 10,
) -> List[Tuple[Task, VM]]:
    """
    Admission Control (Eq 17): Return up to k valid (task, VM) pairs.

    A pair (task, vm) is admissible if:
    1. All predecessors of task are in the completed set.
    2. VM has sufficient resources: avail_cpu >= req_cpu, avail_mem >= req_mem, avail_disk >= req_disk.
    """
    pairs: List[Tuple[Task, VM]] = []

    for task in sorted_tasks:
        predecessors = dag.get_predecessors(task.task_id)
        if not all(p in completed for p in predecessors):
            continue

        for vm in vms:
            if (vm.avail_cpu >= task.req_cpu and
                vm.avail_mem >= task.req_mem and
                vm.avail_disk >= task.req_disk):
                pairs.append((task, vm))
                if len(pairs) >= k:
                    return pairs

    return pairs


def detect_cycle(dag: TaskDAG) -> bool:
    """Check if the DAG contains a cycle. Raises CyclicDependencyError if found."""
    if dag.has_cycle():
        raise CyclicDependencyError("DAG contains a cyclic dependency")
    return False


def _topological_sort(dag: TaskDAG) -> List[str]:
    """Kahn's algorithm for topological ordering."""
    in_degree: Dict[str, int] = defaultdict(int)
    for task in dag.get_all_tasks():
        tid = task.task_id
        if tid not in in_degree:
            in_degree[tid] = 0
        for succ in dag.get_successors(tid):
            in_degree[succ] += 1

    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    order: List[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for succ in dag.get_successors(node):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    return order
