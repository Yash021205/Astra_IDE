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


def mean_compute_cost(task: Task, vms: List[VM]) -> float:
    """Average compute time of `task` over all VMs: data/proc_rate + duration.

    This is HEFT's w_i (the mean computation cost used to rank tasks), and it is
    duration-aware, unlike `global_prioritization`'s structural weight.
    """
    if not vms:
        return float(task.t_dur)
    total = sum(task.data_size_mb / vm.proc_rate_mbps for vm in vms if vm.proc_rate_mbps > 0)
    return total / len(vms) + float(task.t_dur)


def mean_comm_cost(task: Task, vms: List[VM]) -> float:
    """Average communication cost of shipping `task`'s output to another VM.

    HEFT's c_ij. Averaged over VM bandwidths; zero when a single VM makes every
    transfer local.
    """
    if len(vms) < 2:
        return 0.0
    bws = [vm.bandwidth_mbps for vm in vms if vm.bandwidth_mbps > 0]
    if not bws:
        return 0.0
    return task.data_size_mb / (sum(bws) / len(bws))


def upward_rank(dag: TaskDAG, vms: List[VM]) -> Dict[str, float]:
    """HEFT upward rank (b-level) for every task.

        rank_u(i) = w_i + max over successors j of ( c_ij + rank_u(j) )

    with rank_u(exit) = w_exit. This is the length of the longest path from a task
    to any exit node, in expected time, and is the priority HEFT schedules by.
    Computed in reverse topological order so each task is visited after all of its
    successors.
    """
    if dag.has_cycle():
        raise CyclicDependencyError("DAG contains a cycle")

    w = {t.task_id: mean_compute_cost(t, vms) for t in dag.get_all_tasks()}
    c = {t.task_id: mean_comm_cost(t, vms) for t in dag.get_all_tasks()}

    rank: Dict[str, float] = {}
    for tid in reversed(_topological_sort(dag)):
        best_succ = 0.0
        for succ_id in dag.get_successors(tid):
            # Successors are already ranked (reverse topological order).
            best_succ = max(best_succ, c[tid] + rank.get(succ_id, 0.0))
        rank[tid] = w[tid] + best_succ

    # Any task missing from the topological order (isolated/unreachable) still
    # needs a rank so callers can index it unconditionally.
    for t in dag.get_all_tasks():
        rank.setdefault(t.task_id, w[t.task_id])
    return rank


def prioritize_by_upward_rank(dag: TaskDAG, vms: List[VM]) -> List[Task]:
    """Tasks sorted by decreasing upward rank (HEFT's task ordering)."""
    rank = upward_rank(dag, vms)
    tasks = dag.get_all_tasks()
    tasks.sort(key=lambda t: rank[t.task_id], reverse=True)
    return tasks


def filter_admissible_pairs(
    sorted_tasks: List[Task],
    vms: List[VM],
    completed: Set[str],
    dag: TaskDAG,
    k: int = 10,
    max_tasks: int | None = None,
    scheduled: Set[str] | None = None,
) -> List[Tuple[Task, VM]]:
    """
    Admission Control (Eq 17): Return up to k valid (task, VM) pairs.

    A pair (task, vm) is admissible if:
    1. The task has not already been scheduled.
    2. All predecessors of task are in the completed set.
    3. VM has sufficient resources: avail_cpu >= req_cpu, avail_mem >= req_mem, avail_disk >= req_disk.

    `scheduled` is the set of task ids already placed. It must be supplied for
    correct behaviour: without it a task stays admissible after being placed and
    can be scheduled repeatedly, which both double-counts its cost and (because
    the simulator only releases resources for tasks it has not yet completed)
    leaks that task's CPU and memory permanently, deadlocking the episode with
    most of the DAG unscheduled. It defaults to None only so that existing callers
    and tests keep their original semantics.

    `max_tasks` caps how many distinct ready tasks contribute pairs. The default
    (None) keeps the original behaviour: pairs are emitted task-major and the
    function returns as soon as k is reached, so with 4 VMs and k=10 only the top
    ~2 ready tasks are ever reachable. Passing max_tasks together with a larger k
    widens the candidate window so the policy can choose among more tasks.
    """
    pairs: List[Tuple[Task, VM]] = []
    tasks_seen = 0

    for task in sorted_tasks:
        if scheduled is not None and task.task_id in scheduled:
            continue

        predecessors = dag.get_predecessors(task.task_id)
        if not all(p in completed for p in predecessors):
            continue

        if max_tasks is not None and tasks_seen >= max_tasks:
            break
        tasks_seen += 1

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
