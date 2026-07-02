"""
Mathematical models for PF-MPPO reward computation (paper Equations 3-16).

All functions are pure, stateless, and operate on scalar inputs.
"""
from __future__ import annotations

import math
from typing import List


def communication_delay(data_mb: float, bw_src: float, bw_dst: float, same_vm: bool = False) -> float:
    """
    Eq 5: Communication delay when transferring data between VMs.
    If tasks are on the same VM, delay is 0.
    Otherwise: Tra = data / min(bw_src, bw_dst)
    """
    if same_vm:
        return 0.0
    min_bw = min(bw_src, bw_dst)
    if min_bw <= 0:
        return float('inf')
    return data_mb / min_bw


def computation_time(data_mb: float, proc_rate: float) -> float:
    """
    Eq 6: Computation time = data / processing_rate.
    """
    if proc_rate <= 0:
        return float('inf')
    return data_mb / proc_rate


def response_time(wait: float, transfer: float, compute: float) -> float:
    """
    Eq 10: Total response time = wait_time + transfer_time + computation_time.
    """
    return wait + transfer + compute


def makespan(finish_times: List[float]) -> float:
    """
    Eq 12: Makespan = max of all task finish times.
    """
    if not finish_times:
        return 0.0
    return max(finish_times)


def dynamic_power(p_static: float, p_max: float, utilization: float, freq: float = 1.0) -> float:
    """
    Eq 14: Dynamic power of a VM.
    P = P_static + (P_max - P_static) * f^3 * U
    """
    return p_static + (p_max - p_static) * (freq ** 3) * utilization


def task_energy(power_w: float, start_time: float, finish_time: float) -> float:
    """
    Eq 15: Energy consumed by a task on a VM.
    E = P * (finish - start)
    """
    duration = max(0.0, finish_time - start_time)
    return power_w * duration


def total_energy(energies: List[float]) -> float:
    """
    Eq 16: Total data center energy = sum of all task energies.
    """
    return sum(energies)


def load_balance_metric(utilizations: List[float]) -> float:
    """
    Eq 3: Load balancing metric = standard deviation of VM utilizations.
    Lower value = better balanced. Returns 0.0 for empty/single-VM clusters.
    """
    n = len(utilizations)
    if n <= 1:
        return 0.0
    mean_u = sum(utilizations) / n
    variance = sum((u - mean_u) ** 2 for u in utilizations) / n
    return math.sqrt(variance)


def pfmppo_reward(
    response_t: float,
    energy: float,
    load_balance: float,
    alpha1: float = 0.34,
    alpha2: float = 0.33,
    alpha3: float = 0.33,
    eps: float = 1e-6,
) -> float:
    """
    Eq 30: PF-MPPO reward function (matches the paper).
    R = -(alpha1 * log(T_resp) + alpha2 * log(E) + alpha3 * log(LB))

    Weights are the paper's Table 2 values: alpha2 = alpha3 = 0.33 (energy, load
    balance), with alpha1 = 0.34 (latency) so the three sum to 1. Larger alpha1
    emphasizes minimizing completion time; larger alpha2/alpha3 emphasize energy
    and load balancing (paper section 3.4).
    """
    log_resp = math.log(max(response_t, eps))
    log_energy = math.log(max(energy, eps))
    log_lb = math.log(max(load_balance, eps))
    return -(alpha1 * log_resp + alpha2 * log_energy + alpha3 * log_lb)
