"""
Synthetic DAG generator for PF-MPPO training.

Generates random workflow DAGs with configurable task count, dependency density,
and resource distributions matching cloud IDE workloads.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG


def generate_random_dag(
    num_tasks: int = 20,
    max_deps_per_task: int = 3,
    seed: int = 42,
    vm_configs: Optional[List[Dict]] = None,
) -> Tuple[TaskDAG, List[VM]]:
    """
    Generate a random DAG with realistic Cloud IDE task properties.

    Tasks are organized in layers to guarantee acyclicity:
    edges only go from lower layers to higher layers.
    """
    rng = np.random.default_rng(seed)
    dag = TaskDAG()

    # Assign tasks to layers (ensures acyclicity)
    num_layers = max(2, int(np.sqrt(num_tasks)))
    layer_assignment = rng.integers(0, num_layers, size=num_tasks)
    layer_assignment.sort()

    for i in range(num_tasks):
        task = Task(
            task_id=f"task_{i}",
            t_sub=float(rng.uniform(0, 100)),
            t_dur=float(rng.uniform(0.5, 30.0)),
            data_size_mb=float(rng.uniform(1, 500)),
            req_cpu=float(rng.uniform(0.25, 4.0)),
            req_mem=float(rng.uniform(128, 4096)),
            req_disk=float(rng.uniform(256, 20480)),
        )
        dag.add_task(task)

    # Add edges (only from lower to higher layers)
    tasks_by_layer: Dict[int, List[int]] = {}
    for i, layer in enumerate(layer_assignment):
        tasks_by_layer.setdefault(int(layer), []).append(i)

    sorted_layers = sorted(tasks_by_layer.keys())
    for idx, layer in enumerate(sorted_layers[1:], 1):
        for task_idx in tasks_by_layer[layer]:
            # Connect to random tasks in earlier layers
            num_deps = rng.integers(1, min(max_deps_per_task + 1, len(sorted_layers[:idx]) * 2 + 1))
            earlier_tasks = []
            for prev_layer in sorted_layers[:idx]:
                earlier_tasks.extend(tasks_by_layer[prev_layer])
            if earlier_tasks:
                num_deps = min(num_deps, len(earlier_tasks))
                parents = rng.choice(earlier_tasks, size=num_deps, replace=False)
                for parent_idx in parents:
                    dag.add_edge(f"task_{parent_idx}", f"task_{task_idx}")

    # Generate VMs
    vms = generate_vms(vm_configs, rng)

    return dag, vms


def generate_vms(
    vm_configs: Optional[List[Dict]],
    rng: np.random.Generator,
) -> List[VM]:
    """Generate VM list from configs or use defaults."""
    if vm_configs:
        return [VM(
            node_id=cfg.get("node_id", f"vm_{i}"),
            cpu_cap=cfg.get("cpu_cap", 4.0),
            mem_cap=cfg.get("mem_cap", 8192.0),
            disk_cap=cfg.get("disk_cap", 102400.0),
            bandwidth_mbps=cfg.get("bandwidth_mbps", 1000.0),
            proc_rate_mbps=cfg.get("proc_rate_mbps", 200.0),
            power_static_w=cfg.get("power_static_w", 11.0),
            power_max_w=cfg.get("power_max_w", 200.0),
            avail_cpu=cfg.get("avail_cpu", cfg.get("cpu_cap", 4.0)),
            avail_mem=cfg.get("avail_mem", cfg.get("mem_cap", 8192.0)),
            avail_disk=cfg.get("avail_disk", cfg.get("disk_cap", 102400.0)),
            current_utilization=cfg.get("current_utilization", 0.0),
        ) for i, cfg in enumerate(vm_configs)]

    # Default: 4 heterogeneous VMs
    return [
        VM(node_id="vm_0", cpu_cap=4.0, mem_cap=8192.0, disk_cap=102400.0,
           bandwidth_mbps=1000.0, proc_rate_mbps=200.0, power_static_w=11.0, power_max_w=200.0,
           avail_cpu=4.0, avail_mem=8192.0, avail_disk=102400.0),
        VM(node_id="vm_1", cpu_cap=8.0, mem_cap=16384.0, disk_cap=204800.0,
           bandwidth_mbps=2000.0, proc_rate_mbps=400.0, power_static_w=15.0, power_max_w=350.0,
           avail_cpu=8.0, avail_mem=16384.0, avail_disk=204800.0),
        VM(node_id="vm_2", cpu_cap=2.0, mem_cap=4096.0, disk_cap=51200.0,
           bandwidth_mbps=500.0, proc_rate_mbps=100.0, power_static_w=8.0, power_max_w=120.0,
           avail_cpu=2.0, avail_mem=4096.0, avail_disk=51200.0),
        VM(node_id="vm_3", cpu_cap=16.0, mem_cap=32768.0, disk_cap=512000.0,
           bandwidth_mbps=5000.0, proc_rate_mbps=800.0, power_static_w=20.0, power_max_w=500.0,
           avail_cpu=16.0, avail_mem=32768.0, avail_disk=512000.0),
    ]


def load_vm_configs(config_path: str) -> List[Dict]:
    """Load VM configurations from a JSON file."""
    path = Path(config_path)
    with open(path) as f:
        data = json.load(f)
    return data["vms"]
