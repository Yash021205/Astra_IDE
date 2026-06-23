"""
Data structures for the PF-MPPO scheduler.

Task (Eq 1): represents a schedulable unit of work within a DAG.
VM (Eq 2): represents a virtual machine / Kubernetes node with resource capacities.
TaskDAG: directed acyclic graph of task dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Task:
    """A schedulable task within a workflow DAG (paper Equation 1)."""
    task_id: str
    t_sub: float = 0.0          # submission timestamp
    t_dur: float = 1.0          # expected duration (seconds)
    data_size_mb: float = 0.0   # data to transfer
    req_cpu: float = 1.0        # required CPU cores
    req_mem: float = 512.0      # required memory (MB)
    req_disk: float = 1024.0    # required disk (MB)
    # Computed by graph algorithms (Algorithm 1 & 2)
    succ_nums: int = 0
    desc_nums: int = 0
    task_layers: int = 0
    weight: float = 0.0


@dataclass
class VM:
    """A virtual machine / K8s node (paper Equation 2)."""
    node_id: str
    cpu_cap: float = 4.0            # total CPU cores
    mem_cap: float = 8192.0         # total RAM (MB)
    disk_cap: float = 102400.0      # total disk (MB)
    bandwidth_mbps: float = 1000.0  # network bandwidth
    proc_rate_mbps: float = 200.0   # data processing rate
    power_static_w: float = 11.0    # static idle power (Watts)
    power_max_w: float = 200.0      # max power (Watts)
    avail_cpu: float = 4.0          # currently available CPU
    avail_mem: float = 8192.0       # currently available memory
    avail_disk: float = 102400.0    # currently available disk
    current_utilization: float = 0.0


class TaskDAG:
    """Directed Acyclic Graph of task dependencies."""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self.succ_map: Dict[str, List[str]] = {}
        self.prec_map: Dict[str, List[str]] = {}

    def add_task(self, task: Task) -> None:
        self._tasks[task.task_id] = task
        if task.task_id not in self.succ_map:
            self.succ_map[task.task_id] = []
        if task.task_id not in self.prec_map:
            self.prec_map[task.task_id] = []

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add dependency: from_id must complete before to_id can start."""
        if from_id not in self.succ_map:
            self.succ_map[from_id] = []
        if to_id not in self.prec_map:
            self.prec_map[to_id] = []
        self.succ_map[from_id].append(to_id)
        self.prec_map[to_id].append(from_id)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        return list(self._tasks.values())

    def get_roots(self) -> List[Task]:
        """Tasks with no predecessors."""
        return [t for t in self._tasks.values() if not self.prec_map.get(t.task_id)]

    def get_successors(self, task_id: str) -> List[str]:
        return self.succ_map.get(task_id, [])

    def get_predecessors(self, task_id: str) -> List[str]:
        return self.prec_map.get(task_id, [])

    def num_tasks(self) -> int:
        return len(self._tasks)

    def has_cycle(self) -> bool:
        """Detect cycle using DFS coloring (white=0, gray=1, black=2)."""
        color: Dict[str, int] = {tid: 0 for tid in self._tasks}

        def dfs(node: str) -> bool:
            color[node] = 1
            for succ in self.succ_map.get(node, []):
                if color[succ] == 1:
                    return True
                if color[succ] == 0 and dfs(succ):
                    return True
            color[node] = 2
            return False

        for tid in self._tasks:
            if color[tid] == 0:
                if dfs(tid):
                    return True
        return False
