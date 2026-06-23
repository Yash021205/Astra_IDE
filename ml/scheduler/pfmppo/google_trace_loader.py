"""
Google Cluster Trace 2011 data loader for PF-MPPO training.

Parses the publicly available Google cluster-usage traces (v2.1) and converts
them into (TaskDAG, List[VM]) training episodes compatible with the PF-MPPO
environment. This replaces synthetic random DAGs with real production workload
patterns from a Google compute cell (~12,500 machines, 29 days of data).

Trace schema reference:
  "Google cluster-usage traces: format + schema" (Reiss, Wilkes, Hellerstein 2014)

Data source: gs://clusterdata-2011-2/
"""
from __future__ import annotations

import gzip
import glob
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG

# Resource scaling: trace values are normalized 0-1 relative to max machine.
# We scale to absolute values matching PF-MPPO's expected observation ranges.
CPU_SCALE = 32.0         # max machine ~32 cores
MEM_SCALE = 131072.0     # max machine ~128 GB in MB
DISK_SCALE = 512000.0    # disk in MB
BANDWIDTH_BASE = 1000.0  # not in trace; use default
PROC_RATE_BASE = 200.0   # not in trace; use default
TIME_SCALE = 1e-6        # trace timestamps are microseconds

# Task event types (from schema)
EVT_SUBMIT = 0
EVT_SCHEDULE = 1
EVT_EVICT = 2
EVT_FAIL = 3
EVT_FINISH = 4
EVT_KILL = 5

# Machine event types
MEVT_ADD = 0
MEVT_REMOVE = 1


@dataclass
class TraceMachine:
    machine_id: str
    cpu: float
    mem: float
    platform_id: str = ""


@dataclass
class TraceTask:
    job_id: str
    task_index: int
    cpu_request: float = 0.0
    mem_request: float = 0.0
    disk_request: float = 0.0
    priority: int = 0
    scheduling_class: int = 0
    submit_time: int = 0
    schedule_time: int = -1
    finish_time: int = -1
    machine_id: str = ""
    duration_us: int = 0


@dataclass
class TraceJob:
    job_id: str
    tasks: List[TraceTask] = field(default_factory=list)
    scheduling_class: int = 0


class GoogleTraceDataset:
    """Loads and indexes Google Cluster Trace for PF-MPPO training episodes."""

    def __init__(
        self,
        data_dir: str,
        max_tasks_per_episode: int = 50,
        max_jobs_per_episode: int = 10,
        min_tasks_per_job: int = 2,
        max_task_duration_s: float = 3600.0,
        max_files: int = 10,
        seed: int = 42,
    ):
        self.data_dir = data_dir
        self.max_tasks_per_episode = max_tasks_per_episode
        self.max_jobs_per_episode = max_jobs_per_episode
        self.min_tasks_per_job = min_tasks_per_job
        self.max_task_duration_s = max_task_duration_s
        self.max_files = max_files
        self.seed = seed

        self.machines: List[TraceMachine] = []
        self.jobs: List[TraceJob] = []
        self._loaded = False
        self._median_duration_s = 300.0
        self._median_cpu = 0.015
        self._median_mem = 0.015
        self._median_disk = 0.0002

    def load(self) -> "GoogleTraceDataset":
        """Parse trace files and build indexed structures."""
        print(f"Loading Google Cluster Trace from {self.data_dir} (max_files={self.max_files})...")
        self._load_machines()
        print(f"  Loaded {len(self.machines)} machines")
        self._load_tasks()
        print(f"  Loaded {len(self.jobs)} jobs ({sum(len(j.tasks) for j in self.jobs)} tasks)")
        self._loaded = True
        return self

    def _load_machines(self):
        """Parse machine_events to build machine registry."""
        pattern = os.path.join(self.data_dir, "machine_events", "*.csv.gz")
        files = sorted(glob.glob(pattern))
        if not files:
            raise FileNotFoundError(
                f"No machine_events files found in {self.data_dir}/machine_events/"
            )

        machines_map: Dict[str, TraceMachine] = {}
        for fpath in files:
            with gzip.open(fpath, "rt") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 6:
                        continue
                    machine_id = parts[1]
                    event_type = int(parts[2]) if parts[2] else -1
                    if event_type == MEVT_REMOVE:
                        machines_map.pop(machine_id, None)
                        continue
                    if event_type != MEVT_ADD:
                        continue
                    cpu = float(parts[4]) if parts[4] else 0.0
                    mem = float(parts[5]) if parts[5] else 0.0
                    platform_id = parts[3] if len(parts) > 3 else ""
                    if cpu > 0 and mem > 0:
                        machines_map[machine_id] = TraceMachine(
                            machine_id=machine_id,
                            cpu=cpu,
                            mem=mem,
                            platform_id=platform_id,
                        )

        self.machines = list(machines_map.values())
        if not self.machines:
            raise ValueError("No valid machines parsed from trace")

    def _load_tasks(self):
        """Parse task_events to build job→task structures with lifecycles."""
        pattern = os.path.join(self.data_dir, "task_events", "*.csv.gz")
        files = sorted(glob.glob(pattern))
        if not files:
            raise FileNotFoundError(
                f"No task_events files found in {self.data_dir}/task_events/"
            )
        if self.max_files and len(files) > self.max_files:
            files = files[:self.max_files]

        # Collect task events grouped by (job_id, task_index)
        task_events: Dict[Tuple[str, int], List[dict]] = defaultdict(list)

        for fi, fpath in enumerate(files):
            if (fi + 1) % 5 == 0 or fi == 0:
                print(f"  Parsing task_events file {fi+1}/{len(files)}...")
            with gzip.open(fpath, "rt") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 12:
                        continue
                    ts = int(parts[0]) if parts[0] else 0
                    job_id = parts[2]
                    task_idx = int(parts[3]) if parts[3] else 0
                    event_type = int(parts[5]) if parts[5] else -1
                    cpu = float(parts[9]) if parts[9] else 0.0
                    mem = float(parts[10]) if parts[10] else 0.0
                    disk = float(parts[11]) if parts[11] else 0.0
                    priority = int(parts[8]) if parts[8] else 0
                    sched_class = int(parts[7]) if parts[7] else 0
                    machine_id = parts[4] if parts[4] else ""

                    task_events[(job_id, task_idx)].append({
                        "ts": ts,
                        "evt": event_type,
                        "cpu": cpu,
                        "mem": mem,
                        "disk": disk,
                        "priority": priority,
                        "sched_class": sched_class,
                        "machine": machine_id,
                    })

        # Reconstruct task lifecycles and group by job
        jobs_map: Dict[str, TraceJob] = {}
        durations = []

        for (job_id, task_idx), events in task_events.items():
            task = TraceTask(job_id=job_id, task_index=task_idx)

            for evt in events:
                if evt["cpu"] > 0:
                    task.cpu_request = evt["cpu"]
                if evt["mem"] > 0:
                    task.mem_request = evt["mem"]
                if evt["disk"] > 0:
                    task.disk_request = evt["disk"]
                task.priority = evt["priority"]
                task.scheduling_class = evt["sched_class"]

                if evt["evt"] == EVT_SUBMIT:
                    task.submit_time = evt["ts"]
                elif evt["evt"] == EVT_SCHEDULE:
                    task.schedule_time = evt["ts"]
                    task.machine_id = evt["machine"]
                elif evt["evt"] == EVT_FINISH:
                    task.finish_time = evt["ts"]

            # Compute duration
            if task.schedule_time >= 0 and task.finish_time > task.schedule_time:
                task.duration_us = task.finish_time - task.schedule_time
                dur_s = task.duration_us * TIME_SCALE
                if 0 < dur_s <= self.max_task_duration_s:
                    durations.append(dur_s)

            if job_id not in jobs_map:
                jobs_map[job_id] = TraceJob(
                    job_id=job_id,
                    scheduling_class=task.scheduling_class,
                )
            jobs_map[job_id].tasks.append(task)

        # Compute global medians for fallback
        if durations:
            self._median_duration_s = float(np.median(durations))

        cpus = [t.cpu_request for j in jobs_map.values() for t in j.tasks if t.cpu_request > 0]
        mems = [t.mem_request for j in jobs_map.values() for t in j.tasks if t.mem_request > 0]
        disks = [t.disk_request for j in jobs_map.values() for t in j.tasks if t.disk_request > 0]
        if cpus:
            self._median_cpu = float(np.median(cpus))
        if mems:
            self._median_mem = float(np.median(mems))
        if disks:
            self._median_disk = float(np.median(disks))

        # Filter: keep jobs with enough tasks that have valid data
        self.jobs = []
        for job in jobs_map.values():
            # Keep tasks that have resource requests
            valid_tasks = [
                t for t in job.tasks
                if t.cpu_request > 0 or t.mem_request > 0
            ]
            if len(valid_tasks) >= self.min_tasks_per_job:
                job.tasks = sorted(valid_tasks, key=lambda t: t.task_index)
                self.jobs.append(job)

        if not self.jobs:
            raise ValueError(
                f"No valid jobs found (min {self.min_tasks_per_job} tasks with resources)"
            )

    def sample_episode(
        self,
        rng: np.random.Generator,
        vm_configs: Optional[List[Dict]] = None,
    ) -> Tuple[TaskDAG, List[VM]]:
        """Sample one training episode from trace data."""
        if not self._loaded:
            raise RuntimeError("Call .load() before sampling episodes")

        dag = TaskDAG()

        # Pick random jobs for this episode
        n_jobs = min(self.max_jobs_per_episode, len(self.jobs))
        job_indices = rng.choice(len(self.jobs), size=n_jobs, replace=False)
        selected_jobs = [self.jobs[i] for i in job_indices]

        # Build DAG from selected jobs
        task_count = 0
        for job in selected_jobs:
            # Limit tasks per job to stay within budget
            remaining = self.max_tasks_per_episode - task_count
            if remaining <= 0:
                break
            tasks_to_use = job.tasks[:remaining]

            job_task_ids = []
            for t in tasks_to_use:
                task_id = f"j{job.job_id}_t{t.task_index}"

                # Scale resource requests to absolute values
                req_cpu = max(0.25, t.cpu_request * CPU_SCALE)
                req_mem = max(128.0, t.mem_request * MEM_SCALE)
                req_disk = max(256.0, t.disk_request * DISK_SCALE)

                # Duration: use measured or fallback to median
                if t.duration_us > 0:
                    dur_s = t.duration_us * TIME_SCALE
                    dur_s = min(dur_s, self.max_task_duration_s)
                else:
                    dur_s = self._median_duration_s

                # Data size estimate from disk request
                data_size = max(1.0, t.disk_request * DISK_SCALE * 0.1)

                task_obj = Task(
                    task_id=task_id,
                    t_sub=float(t.submit_time * TIME_SCALE),
                    t_dur=float(dur_s),
                    data_size_mb=float(data_size),
                    req_cpu=float(req_cpu),
                    req_mem=float(req_mem),
                    req_disk=float(req_disk),
                )
                dag.add_task(task_obj)
                job_task_ids.append(task_id)
                task_count += 1

            # Build edges within job: layered structure based on task indices
            self._build_job_edges(dag, job_task_ids, rng)

        # Sample machines as VMs
        vms = self._sample_vms(rng, vm_configs)

        return dag, vms

    def _build_job_edges(
        self,
        dag: TaskDAG,
        task_ids: List[str],
        rng: np.random.Generator,
    ):
        """Create dependency edges within a job's tasks.

        Strategy: assign tasks to layers, add edges from earlier to later layers.
        This mimics real job structure where tasks have sequential phases.
        """
        n = len(task_ids)
        if n <= 1:
            return

        # Assign to layers (sqrt(n) layers)
        num_layers = max(2, int(np.sqrt(n)))
        layer_size = max(1, n // num_layers)

        layers: List[List[str]] = []
        for i in range(0, n, layer_size):
            layers.append(task_ids[i:i + layer_size])

        # Connect adjacent layers: each task in layer L+1 depends on 1-2 tasks in layer L
        for li in range(1, len(layers)):
            for task_id in layers[li]:
                n_deps = min(len(layers[li - 1]), int(rng.integers(1, 3)))
                parents = rng.choice(
                    layers[li - 1], size=n_deps, replace=False
                )
                for parent_id in parents:
                    dag.add_edge(parent_id, task_id)

    def _sample_vms(
        self,
        rng: np.random.Generator,
        vm_configs: Optional[List[Dict]] = None,
    ) -> List[VM]:
        """Sample VMs from trace machines or use provided configs."""
        if vm_configs:
            from ml.scheduler.pfmppo.dag_generator import generate_vms
            return generate_vms(vm_configs, rng)

        # Sample 4 diverse machines: pick from different memory capacity tiers
        # (trace has more memory diversity than CPU diversity)
        n_vms = 4
        mem_values = sorted(set(round(m.mem, 4) for m in self.machines))
        if len(mem_values) >= n_vms:
            tier_indices = np.linspace(0, len(mem_values) - 1, n_vms, dtype=int)
            selected = []
            for ti in tier_indices:
                target_mem = mem_values[ti]
                candidates = [m for m in self.machines if round(m.mem, 4) == target_mem]
                selected.append(candidates[int(rng.integers(len(candidates)))])
        else:
            indices = rng.choice(len(self.machines), size=min(n_vms, len(self.machines)), replace=False)
            selected = [self.machines[idx] for idx in indices]

        vms = []
        for i, m in enumerate(selected):
            cpu_cap = max(2.0, m.cpu * CPU_SCALE)
            mem_cap = max(4096.0, m.mem * MEM_SCALE)
            bw = BANDWIDTH_BASE * (cpu_cap / 4.0)
            pr = PROC_RATE_BASE * (cpu_cap / 4.0)
            vms.append(VM(
                node_id=f"vm_{i}",
                cpu_cap=cpu_cap,
                mem_cap=mem_cap,
                disk_cap=DISK_SCALE,
                bandwidth_mbps=bw,
                proc_rate_mbps=pr,
                power_static_w=8.0 + cpu_cap,
                power_max_w=50.0 + cpu_cap * 20.0,
                avail_cpu=cpu_cap,
                avail_mem=mem_cap,
                avail_disk=DISK_SCALE,
            ))
        return vms

    @property
    def num_jobs(self) -> int:
        return len(self.jobs)

    @property
    def num_machines(self) -> int:
        return len(self.machines)

    def stats(self) -> Dict:
        """Summary statistics of loaded trace data."""
        total_tasks = sum(len(j.tasks) for j in self.jobs)
        return {
            "num_jobs": len(self.jobs),
            "num_machines": len(self.machines),
            "total_tasks": total_tasks,
            "median_duration_s": self._median_duration_s,
            "median_cpu_request": self._median_cpu,
            "median_mem_request": self._median_mem,
            "tasks_per_job_avg": total_tasks / max(1, len(self.jobs)),
        }


def generate_trace_dag(
    dataset: GoogleTraceDataset,
    rng: np.random.Generator,
    vm_configs: Optional[List[Dict]] = None,
) -> Tuple[TaskDAG, List[VM]]:
    """Top-level generator matching the interface of generate_random_dag."""
    return dataset.sample_episode(rng=rng, vm_configs=vm_configs)
