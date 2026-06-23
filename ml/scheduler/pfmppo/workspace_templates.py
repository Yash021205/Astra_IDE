"""
Realistic IDE workspace startup templates for PF-MPPO training.

Defines sub-task DAGs that model actual workspace lifecycle:
image_pull -> repo_clone -> dependency_install -> [lsp_start, ext_load] -> devserver_start

Each template has noise injection for training robustness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG
from ml.scheduler.pfmppo.dag_generator import generate_vms


@dataclass
class SubTaskProfile:
    """Resource/duration profile for a single workspace sub-task."""
    name: str
    base_duration: float
    duration_variance: float
    req_cpu: float
    req_mem: float
    req_disk: float
    data_size_mb: float
    cpu_variance: float = 0.15
    mem_variance: float = 0.15


@dataclass
class WorkspaceTemplate:
    """A workspace startup workflow template."""
    name: str
    language: str
    subtasks: List[SubTaskProfile]
    edges: List[Tuple[int, int]]


# ── Sub-task profiles ─────────────────────────────────────────────────────────

IMAGE_PULL = SubTaskProfile(
    name="image_pull", base_duration=10.0, duration_variance=0.4,
    req_cpu=0.25, req_mem=256.0, req_disk=2048.0, data_size_mb=400.0,
)
REPO_CLONE = SubTaskProfile(
    name="repo_clone", base_duration=8.0, duration_variance=0.6,
    req_cpu=0.5, req_mem=512.0, req_disk=4096.0, data_size_mb=200.0,
)
PIP_INSTALL = SubTaskProfile(
    name="pip_install", base_duration=30.0, duration_variance=0.5,
    req_cpu=2.0, req_mem=1024.0, req_disk=8192.0, data_size_mb=150.0,
)
NPM_INSTALL = SubTaskProfile(
    name="npm_install", base_duration=45.0, duration_variance=0.5,
    req_cpu=2.5, req_mem=2048.0, req_disk=12288.0, data_size_mb=300.0,
)
CMAKE_CONFIGURE = SubTaskProfile(
    name="cmake_configure", base_duration=10.0, duration_variance=0.3,
    req_cpu=1.0, req_mem=512.0, req_disk=1024.0, data_size_mb=20.0,
)
CMAKE_BUILD = SubTaskProfile(
    name="cmake_build", base_duration=120.0, duration_variance=0.5,
    req_cpu=4.0, req_mem=2048.0, req_disk=4096.0, data_size_mb=50.0,
)
GO_MOD_DOWNLOAD = SubTaskProfile(
    name="go_mod_download", base_duration=15.0, duration_variance=0.5,
    req_cpu=0.5, req_mem=512.0, req_disk=4096.0, data_size_mb=180.0,
)
GO_BUILD = SubTaskProfile(
    name="go_build", base_duration=45.0, duration_variance=0.4,
    req_cpu=3.0, req_mem=1536.0, req_disk=2048.0, data_size_mb=30.0,
)
CARGO_FETCH = SubTaskProfile(
    name="cargo_fetch", base_duration=20.0, duration_variance=0.5,
    req_cpu=0.5, req_mem=512.0, req_disk=6144.0, data_size_mb=250.0,
)
CARGO_BUILD = SubTaskProfile(
    name="cargo_build", base_duration=180.0, duration_variance=0.4,
    req_cpu=4.0, req_mem=3072.0, req_disk=8192.0, data_size_mb=60.0,
)
PKG_INSTALL_A = SubTaskProfile(
    name="pkg_a_install", base_duration=25.0, duration_variance=0.5,
    req_cpu=1.5, req_mem=1024.0, req_disk=4096.0, data_size_mb=100.0,
)
PKG_INSTALL_B = SubTaskProfile(
    name="pkg_b_install", base_duration=30.0, duration_variance=0.5,
    req_cpu=2.0, req_mem=1536.0, req_disk=6144.0, data_size_mb=150.0,
)
PKG_INSTALL_C = SubTaskProfile(
    name="pkg_c_install", base_duration=20.0, duration_variance=0.5,
    req_cpu=1.0, req_mem=768.0, req_disk=3072.0, data_size_mb=80.0,
)
LSP_START = SubTaskProfile(
    name="lsp_start", base_duration=5.0, duration_variance=0.3,
    req_cpu=1.0, req_mem=768.0, req_disk=256.0, data_size_mb=10.0,
)
EXT_LOAD = SubTaskProfile(
    name="ext_load", base_duration=3.0, duration_variance=0.2,
    req_cpu=0.5, req_mem=256.0, req_disk=512.0, data_size_mb=20.0,
)
DEVSERVER_START = SubTaskProfile(
    name="devserver_start", base_duration=3.0, duration_variance=0.3,
    req_cpu=0.5, req_mem=256.0, req_disk=128.0, data_size_mb=5.0,
)

# ── Templates ─────────────────────────────────────────────────────────────────

PYTHON_TEMPLATE = WorkspaceTemplate(
    name="python_project",
    language="python",
    subtasks=[IMAGE_PULL, REPO_CLONE, PIP_INSTALL, LSP_START, EXT_LOAD, DEVSERVER_START],
    edges=[(0, 1), (1, 2), (2, 3), (2, 4), (3, 5), (4, 5)],
)

NODEJS_TEMPLATE = WorkspaceTemplate(
    name="nodejs_project",
    language="javascript",
    subtasks=[IMAGE_PULL, REPO_CLONE, NPM_INSTALL, LSP_START, EXT_LOAD, DEVSERVER_START],
    edges=[(0, 1), (1, 2), (2, 3), (2, 4), (3, 5), (4, 5)],
)

CPP_TEMPLATE = WorkspaceTemplate(
    name="cpp_project",
    language="cpp",
    subtasks=[IMAGE_PULL, REPO_CLONE, CMAKE_CONFIGURE, CMAKE_BUILD, LSP_START, EXT_LOAD],
    edges=[(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)],
)

GO_TEMPLATE = WorkspaceTemplate(
    name="go_project",
    language="go",
    subtasks=[IMAGE_PULL, REPO_CLONE, GO_MOD_DOWNLOAD, GO_BUILD, LSP_START, EXT_LOAD],
    edges=[(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)],
)

RUST_TEMPLATE = WorkspaceTemplate(
    name="rust_project",
    language="rust",
    subtasks=[IMAGE_PULL, REPO_CLONE, CARGO_FETCH, CARGO_BUILD, LSP_START, EXT_LOAD],
    edges=[(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)],
)

MONOREPO_TEMPLATE = WorkspaceTemplate(
    name="monorepo_project",
    language="monorepo",
    subtasks=[IMAGE_PULL, REPO_CLONE, PKG_INSTALL_A, PKG_INSTALL_B, PKG_INSTALL_C, LSP_START, EXT_LOAD],
    edges=[(0, 1), (1, 2), (1, 3), (1, 4), (2, 5), (3, 5), (4, 5), (2, 6), (3, 6), (4, 6)],
)

GENERIC_TEMPLATE = WorkspaceTemplate(
    name="generic_project",
    language="generic",
    subtasks=[IMAGE_PULL, REPO_CLONE, EXT_LOAD],
    edges=[(0, 1), (1, 2)],
)

TEMPLATES: Dict[str, WorkspaceTemplate] = {
    "python": PYTHON_TEMPLATE,
    "javascript": NODEJS_TEMPLATE,
    "typescript": NODEJS_TEMPLATE,
    "nodejs": NODEJS_TEMPLATE,
    "cpp": CPP_TEMPLATE,
    "c++": CPP_TEMPLATE,
    "c": CPP_TEMPLATE,
    "go": GO_TEMPLATE,
    "golang": GO_TEMPLATE,
    "rust": RUST_TEMPLATE,
    "monorepo": MONOREPO_TEMPLATE,
    "generic": GENERIC_TEMPLATE,
}

ALL_TEMPLATES: List[WorkspaceTemplate] = [
    PYTHON_TEMPLATE, NODEJS_TEMPLATE, CPP_TEMPLATE,
    GO_TEMPLATE, RUST_TEMPLATE, MONOREPO_TEMPLATE, GENERIC_TEMPLATE,
]


def get_template_for_language(language: str) -> WorkspaceTemplate:
    """Map a workspace language string to its template. Falls back to generic."""
    return TEMPLATES.get(language.lower().strip(), GENERIC_TEMPLATE)


def _perturb(base: float, variance: float, rng: np.random.Generator) -> float:
    """Apply noise to a base value. Result is always > 0."""
    factor = rng.uniform(1.0 - variance, 1.0 + variance)
    return max(0.01, base * factor)


def instantiate_template(
    template: WorkspaceTemplate,
    workspace_id: str,
    rng: np.random.Generator,
) -> TaskDAG:
    """
    Create a concrete TaskDAG from a template with noise-perturbed values.

    Task IDs are prefixed with workspace_id for uniqueness in composite DAGs.
    """
    dag = TaskDAG()

    for i, profile in enumerate(template.subtasks):
        task = Task(
            task_id=f"{workspace_id}_{profile.name}",
            t_sub=0.0,
            t_dur=_perturb(profile.base_duration, profile.duration_variance, rng),
            data_size_mb=_perturb(profile.data_size_mb, 0.3, rng),
            req_cpu=_perturb(profile.req_cpu, profile.cpu_variance, rng),
            req_mem=_perturb(profile.req_mem, profile.mem_variance, rng),
            req_disk=_perturb(profile.req_disk, 0.2, rng),
        )
        dag.add_task(task)

    for src_idx, dst_idx in template.edges:
        src_id = f"{workspace_id}_{template.subtasks[src_idx].name}"
        dst_id = f"{workspace_id}_{template.subtasks[dst_idx].name}"
        dag.add_edge(src_id, dst_id)

    return dag


def generate_template_dag(
    num_workspaces: int,
    rng: np.random.Generator,
    language_weights: Optional[Dict[str, float]] = None,
    vm_configs: Optional[List[Dict]] = None,
) -> Tuple[TaskDAG, List[VM]]:
    """
    Generate a composite DAG from multiple workspace templates for training.

    Samples num_workspaces templates (weighted by language_weights or uniform),
    instantiates each with noise, and merges into a single DAG.
    No cross-workspace edges — workspaces are independent workflows competing
    for shared VMs.
    """
    if language_weights:
        languages = list(language_weights.keys())
        weights = np.array([language_weights[l] for l in languages])
        weights = weights / weights.sum()
    else:
        languages = [t.language for t in ALL_TEMPLATES]
        weights = None

    composite_dag = TaskDAG()

    for ws_idx in range(num_workspaces):
        lang = rng.choice(languages, p=weights)
        template = get_template_for_language(lang)
        ws_id = f"ws{ws_idx}"

        ws_dag = instantiate_template(template, ws_id, rng)

        for task in ws_dag.get_all_tasks():
            composite_dag.add_task(task)
        for src_id, successors in ws_dag.succ_map.items():
            for dst_id in successors:
                composite_dag.add_edge(src_id, dst_id)

    vms = generate_vms(vm_configs, rng)
    return composite_dag, vms


def compute_template_aggregates(template: WorkspaceTemplate) -> Dict[str, float]:
    """
    Compute aggregate resource metrics for a template (used at inference time).

    Returns dict with:
    - critical_path_duration: longest path through the DAG (sum of base durations)
    - peak_cpu: max sum of concurrent sub-tasks' CPU requirements
    - peak_mem: max sum of concurrent sub-tasks' memory requirements
    - total_disk: sum of all sub-tasks' disk requirements
    - total_data_mb: sum of all sub-tasks' data sizes
    - num_subtasks: total sub-task count
    - depth: longest path in edges (number of layers)
    """
    n = len(template.subtasks)

    # Build adjacency for topological analysis
    successors: Dict[int, List[int]] = {i: [] for i in range(n)}
    predecessors: Dict[int, List[int]] = {i: [] for i in range(n)}
    for src, dst in template.edges:
        successors[src].append(dst)
        predecessors[dst].append(src)

    # Critical path: longest path (sum of durations) using DP on topological order
    # Topological sort via Kahn's
    in_degree = {i: len(predecessors[i]) for i in range(n)}
    queue = [i for i in range(n) if in_degree[i] == 0]
    topo_order = []
    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for succ in successors[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Longest path (duration-weighted)
    dist = [0.0] * n
    for i in topo_order:
        dist[i] += template.subtasks[i].base_duration
        for succ in successors[i]:
            dist[succ] = max(dist[succ], dist[i])
    critical_path_duration = max(dist)

    # Depth (edge count on longest path)
    depth_arr = [0] * n
    for i in topo_order:
        for succ in successors[i]:
            depth_arr[succ] = max(depth_arr[succ], depth_arr[i] + 1)
    depth = max(depth_arr)

    # Peak concurrent resources: compute earliest start times, find max overlap
    earliest_start = [0.0] * n
    for i in topo_order:
        for succ in successors[i]:
            earliest_start[succ] = max(
                earliest_start[succ],
                earliest_start[i] + template.subtasks[i].base_duration,
            )

    # Find peak by checking resource usage at each task's start time
    events = []
    for i in range(n):
        start = earliest_start[i]
        end = start + template.subtasks[i].base_duration
        events.append((start, template.subtasks[i].req_cpu, template.subtasks[i].req_mem))
        events.append((end, -template.subtasks[i].req_cpu, -template.subtasks[i].req_mem))
    events.sort(key=lambda e: e[0])

    peak_cpu = 0.0
    peak_mem = 0.0
    running_cpu = 0.0
    running_mem = 0.0
    for _, cpu_delta, mem_delta in events:
        running_cpu += cpu_delta
        running_mem += mem_delta
        peak_cpu = max(peak_cpu, running_cpu)
        peak_mem = max(peak_mem, running_mem)

    total_disk = sum(p.req_disk for p in template.subtasks)
    total_data_mb = sum(p.data_size_mb for p in template.subtasks)

    return {
        "critical_path_duration": critical_path_duration,
        "peak_cpu": peak_cpu,
        "peak_mem": peak_mem,
        "total_disk": total_disk,
        "total_data_mb": total_data_mb,
        "num_subtasks": n,
        "depth": depth,
    }
