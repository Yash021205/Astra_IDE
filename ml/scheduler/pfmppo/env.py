"""
PF-MPPO Gymnasium environment implementing the paper's state/action/reward formulation.

Observation (Eq 28): K x 10 flattened vector of (Task, VM) pair features.
Action (Eq 29): Discrete index into admissible pairs [0, K-1].
Reward (Eq 30): R = -(alpha1*log(T_resp) + alpha2*log(E) + alpha3*log(LB))
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except ImportError:
    _GYM_AVAILABLE = False
    gym = None
    spaces = None

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG
from ml.scheduler.pfmppo.dag_generator import generate_random_dag, load_vm_configs
from ml.scheduler.pfmppo.workspace_templates import generate_template_dag
from ml.scheduler.pfmppo.graph_algorithms import (
    parse_task_features,
    global_prioritization,
    filter_admissible_pairs,
)
from ml.scheduler.pfmppo.math_models import (
    communication_delay,
    computation_time,
    response_time,
    dynamic_power,
    task_energy,
    load_balance_metric,
    pfmppo_reward,
)


K_PAIRS_DEFAULT = 10
FEATURES_PER_PAIR = 10
INVALID_ACTION_PENALTY = -50.0


def encode_state(pairs: List[Tuple[Task, VM]], k: int = K_PAIRS_DEFAULT) -> np.ndarray:
    """
    Eq 28: Encode admissible (Task, VM) pairs into a fixed-size state vector.

    Each pair is encoded as 10 features:
    [avail_cpu - req_cpu, avail_mem - req_mem, avail_disk - req_disk,
     vm_bandwidth, vm_proc_rate, task_duration, task_data_size,
     task_succ_nums, task_desc_nums, task_layers]

    Zero-padded to K * 10 dimensions.
    """
    state = np.zeros(k * FEATURES_PER_PAIR, dtype=np.float32)

    for i, (task, vm) in enumerate(pairs[:k]):
        offset = i * FEATURES_PER_PAIR
        state[offset + 0] = vm.avail_cpu - task.req_cpu
        state[offset + 1] = (vm.avail_mem - task.req_mem) / 1000.0  # normalize to ~[-4, 32]
        state[offset + 2] = (vm.avail_disk - task.req_disk) / 10000.0  # normalize
        state[offset + 3] = vm.bandwidth_mbps / 1000.0  # normalize to ~[0, 5]
        state[offset + 4] = vm.proc_rate_mbps / 100.0   # normalize to ~[0, 8]
        state[offset + 5] = task.t_dur / 30.0           # normalize to ~[0, 1]
        state[offset + 6] = task.data_size_mb / 500.0   # normalize to ~[0, 1]
        state[offset + 7] = task.succ_nums / 10.0       # normalize
        state[offset + 8] = task.desc_nums / 20.0       # normalize
        state[offset + 9] = task.task_layers / 10.0     # normalize

    return state


if _GYM_AVAILABLE:

    class PFMPPOEnv(gym.Env):
        """
        PF-MPPO scheduling environment.

        Each episode presents a workflow DAG to schedule across a set of VMs.
        The agent picks one (Task, VM) pair per step until all tasks complete.
        """

        metadata = {"render_modes": ["ansi"]}

        def __init__(
            self,
            num_tasks: int = 20,
            num_vms: int = 4,
            k_pairs: int = K_PAIRS_DEFAULT,
            max_steps: int = 200,
            max_deps_per_task: int = 3,
            vm_configs: Optional[List[Dict]] = None,
            seed: Optional[int] = None,
            alpha1: float = 0.34,   # paper Table 2: latency weight (0.34 = 1 - 0.33 - 0.33)
            alpha2: float = 0.33,   # paper Table 2: energy weight
            alpha3: float = 0.33,   # paper Table 2: load-balance weight
            dag_mode: str = "random",
            num_workspaces: Tuple[int, int] = (3, 8),
            language_weights: Optional[Dict[str, float]] = None,
            template_ratio: float = 0.7,
            data_dir: Optional[str] = None,
            max_files: int = 10,
        ):
            super().__init__()
            self.max_files = max_files
            self.num_tasks = num_tasks
            self.num_vms = num_vms
            self.k_pairs = k_pairs
            self.max_steps = max_steps
            self.max_deps_per_task = max_deps_per_task
            self.vm_configs = vm_configs
            self.alpha1 = alpha1
            self.alpha2 = alpha2
            self.alpha3 = alpha3
            self.dag_mode = dag_mode
            self.num_workspaces = num_workspaces
            self.language_weights = language_weights
            self.template_ratio = template_ratio
            self.data_dir = data_dir
            self.trace_dataset = None

            obs_dim = k_pairs * FEATURES_PER_PAIR
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(k_pairs)

            self._rng = np.random.default_rng(seed)
            self._seed = seed
            self._episode_count = 0

            # State (set in reset)
            self.dag: TaskDAG = TaskDAG()
            self.vms: List[VM] = []
            self.features: Dict[str, Dict[str, int]] = {}
            self.sorted_tasks: List[Task] = []
            self.completed: Set[str] = set()
            self.task_assignments: Dict[str, str] = {}
            self.task_finish_times: Dict[str, float] = {}
            self.current_time: float = 0.0
            self.step_count: int = 0
            self.admissible_pairs: List[Tuple[Task, VM]] = []
            self.valid_mask: np.ndarray = np.zeros(k_pairs, dtype=np.float32)

        def reset(self, *, seed: Optional[int] = None, options=None):
            super().reset(seed=seed)
            if seed is not None:
                self._rng = np.random.default_rng(seed)

            self._episode_count += 1
            dag_seed = self._rng.integers(0, 2**31)

            use_trace = (
                self.dag_mode == "trace"
                or (self.dag_mode == "trace_hybrid" and self._rng.random() < self.template_ratio)
            )
            use_template = (
                self.dag_mode == "template"
                or (self.dag_mode == "hybrid" and self._rng.random() < self.template_ratio)
            )

            if use_trace:
                if self.trace_dataset is None:
                    # Shared, process-wide cache: all CTDE worker threads reuse ONE
                    # parse instead of each re-parsing the multi-GB trace.
                    from ml.scheduler.pfmppo.google_trace_loader import load_cached
                    self.trace_dataset = load_cached(
                        data_dir=self.data_dir,
                        max_tasks_per_episode=self.num_tasks,
                        max_files=self.max_files,   # 0 = load the FULL trace
                    )
                self.dag, self.vms = self.trace_dataset.sample_episode(
                    rng=np.random.default_rng(int(dag_seed)),
                    vm_configs=self.vm_configs,
                )
            elif use_template:
                n_ws = int(self._rng.integers(self.num_workspaces[0], self.num_workspaces[1] + 1))
                ws_rng = np.random.default_rng(int(dag_seed))
                self.dag, self.vms = generate_template_dag(
                    num_workspaces=n_ws,
                    rng=ws_rng,
                    language_weights=self.language_weights,
                    vm_configs=self.vm_configs,
                )
            else:
                self.dag, self.vms = generate_random_dag(
                    num_tasks=self.num_tasks,
                    max_deps_per_task=self.max_deps_per_task,
                    seed=int(dag_seed),
                    vm_configs=self.vm_configs,
                )

            # Reset VM available resources
            for vm in self.vms:
                vm.avail_cpu = vm.cpu_cap
                vm.avail_mem = vm.mem_cap
                vm.avail_disk = vm.disk_cap
                vm.current_utilization = 0.0

            self.features = parse_task_features(self.dag)
            self.sorted_tasks = global_prioritization(self.dag, self.features)

            self.completed = set()
            self.task_assignments = {}
            self.task_finish_times = {}
            self.current_time = 0.0
            self.step_count = 0

            self._update_admissible_pairs()
            obs = encode_state(self.admissible_pairs, self.k_pairs)
            return obs, {"valid_mask": self.valid_mask.copy()}

        def step(self, action: int):
            self.step_count += 1
            action = int(action)

            # Invalid action check
            if action >= len(self.admissible_pairs) or self.valid_mask[action] == 0:
                obs = encode_state(self.admissible_pairs, self.k_pairs)
                terminated = len(self.completed) >= self.dag.num_tasks()
                truncated = self.step_count >= self.max_steps
                return obs, INVALID_ACTION_PENALTY, terminated, truncated, {
                    "valid_mask": self.valid_mask.copy(),
                    "invalid_action": True,
                }

            task, vm = self.admissible_pairs[action]

            # Execute the scheduling decision
            reward = self._execute_placement(task, vm)

            # Advance simulation: complete tasks whose duration has elapsed
            self._advance_time()

            # Recompute admissible pairs
            self._update_admissible_pairs()

            obs = encode_state(self.admissible_pairs, self.k_pairs)
            terminated = len(self.completed) >= self.dag.num_tasks()
            truncated = self.step_count >= self.max_steps

            return obs, reward, terminated, truncated, {
                "valid_mask": self.valid_mask.copy(),
                "invalid_action": False,
            }

        def get_valid_mask(self) -> np.ndarray:
            """Return current valid action mask."""
            return self.valid_mask.copy()

        def render(self):
            return (
                f"step={self.step_count} completed={len(self.completed)}/{self.dag.num_tasks()} "
                f"time={self.current_time:.2f} pairs={len(self.admissible_pairs)}"
            )

        # ── Internal methods ───────────────────────────────────────────

        def _execute_placement(self, task: Task, vm: VM) -> float:
            """Place task on VM, compute reward."""
            # Allocate resources
            vm.avail_cpu -= task.req_cpu
            vm.avail_mem -= task.req_mem
            vm.avail_disk -= task.req_disk
            vm.current_utilization = 1.0 - (vm.avail_cpu / vm.cpu_cap)

            # Compute timing
            parent_vms = [
                self.task_assignments.get(p) for p in self.dag.get_predecessors(task.task_id)
            ]
            # Communication delay: max transfer from any parent on a different VM
            transfer = 0.0
            for parent_id in self.dag.get_predecessors(task.task_id):
                parent_vm_id = self.task_assignments.get(parent_id)
                if parent_vm_id and parent_vm_id != vm.node_id:
                    parent_task = self.dag.get_task(parent_id)
                    parent_vm = self._get_vm(parent_vm_id)
                    if parent_task and parent_vm:
                        t = communication_delay(
                            parent_task.data_size_mb,
                            parent_vm.bandwidth_mbps,
                            vm.bandwidth_mbps,
                        )
                        transfer = max(transfer, t)

            compute = computation_time(task.data_size_mb, vm.proc_rate_mbps)

            # Wait time: time since last predecessor finished
            wait = 0.0
            for p_id in self.dag.get_predecessors(task.task_id):
                ft = self.task_finish_times.get(p_id, 0.0)
                wait = max(wait, ft - self.current_time)
            wait = max(0.0, wait)

            # Task timing
            start_time = self.current_time + wait + transfer
            finish_time = start_time + compute + task.t_dur

            self.task_assignments[task.task_id] = vm.node_id
            self.task_finish_times[task.task_id] = finish_time

            # Compute reward components
            resp_t = response_time(wait, transfer, compute + task.t_dur)
            power = dynamic_power(vm.power_static_w, vm.power_max_w, vm.current_utilization)
            energy = task_energy(power, start_time, finish_time)
            utilizations = [v.current_utilization for v in self.vms]
            lb = load_balance_metric(utilizations)

            reward = pfmppo_reward(resp_t, energy, lb, self.alpha1, self.alpha2, self.alpha3)
            return reward

        def _advance_time(self):
            """Advance time and mark completed tasks."""
            # Find minimum finish time among unfinished tasks
            pending_finishes = {
                tid: ft for tid, ft in self.task_finish_times.items()
                if tid not in self.completed
            }
            if not pending_finishes:
                return

            # Complete all tasks that finish at or before the earliest finish time
            min_finish = min(pending_finishes.values())
            self.current_time = max(self.current_time, min_finish)

            for tid, ft in list(pending_finishes.items()):
                if ft <= self.current_time:
                    self.completed.add(tid)
                    # Release resources
                    vm_id = self.task_assignments.get(tid)
                    task = self.dag.get_task(tid)
                    if vm_id and task:
                        vm = self._get_vm(vm_id)
                        if vm:
                            vm.avail_cpu = min(vm.cpu_cap, vm.avail_cpu + task.req_cpu)
                            vm.avail_mem = min(vm.mem_cap, vm.avail_mem + task.req_mem)
                            vm.avail_disk = min(vm.disk_cap, vm.avail_disk + task.req_disk)
                            vm.current_utilization = 1.0 - (vm.avail_cpu / vm.cpu_cap)

        def _update_admissible_pairs(self):
            """Recompute admissible (task, vm) pairs and valid mask."""
            self.admissible_pairs = filter_admissible_pairs(
                self.sorted_tasks, self.vms, self.completed, self.dag, self.k_pairs
            )
            self.valid_mask = np.zeros(self.k_pairs, dtype=np.float32)
            for i in range(min(len(self.admissible_pairs), self.k_pairs)):
                self.valid_mask[i] = 1.0

        def _get_vm(self, node_id: str) -> Optional[VM]:
            for vm in self.vms:
                if vm.node_id == node_id:
                    return vm
            return None

else:

    class PFMPPOEnv:
        """Stub when gymnasium is not installed."""
        def __init__(self, *args: Any, **kwargs: Any):
            raise ImportError(
                "gymnasium is not installed. Install ML extras: pip install -r ml/requirements.txt"
            )
