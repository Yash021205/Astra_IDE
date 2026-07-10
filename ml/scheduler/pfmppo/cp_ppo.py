"""
CP-PPO: critical-path-guided PPO with expert warm start and rollout search.

Three components, each addressing one measured failure of the PF-MPPO
reproduction:

1. **Expert warm start (behaviour cloning).** The paper agent starts from a random
   policy and, on a 15-task DAG, never discovers the earliest-finish-time rule.
   We first clone a Min-Min expert that selects on *true* EFT (including transfer
   and predecessor wait), which puts the policy at heuristic quality before any
   reinforcement learning happens.

2. **Makespan-aligned fine-tuning.** With `reward_mode="makespan"` and gamma = 1 the
   return telescopes exactly to the negative final makespan, so PPO improves the
   metric that is actually reported instead of a three-term proxy.

3. **Rollout search at inference.** A single greedy pass commits to every decision
   irrevocably. Sampling N schedules from the stochastic policy and keeping the one
   with the lowest makespan converts spare compute into schedule quality.

Component 3 is the largest single contributor, so the benchmark also reports the
heuristic prior under the *same* search budget: the question this module is built
to answer honestly is whether a learned prior beats a hand-written one when both
are given N samples.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from ml.scheduler.pfmppo.env import PFMPPOEnv
from ml.scheduler.pfmppo.heuristics import expert_pick


# ── Expert demonstrations ─────────────────────────────────────────────────────

def collect_demonstrations(
    env_config: Dict,
    episodes: int,
    pick=expert_pick,
    seed_offset: int = 10_000,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Roll the expert and record (observation, valid mask, chosen action index).

    Demonstration seeds are offset well away from the evaluation seeds so the
    policy is never cloned on the DAGs it is scored on.
    """
    env = PFMPPOEnv(**env_config)
    obs_buf: List[np.ndarray] = []
    mask_buf: List[np.ndarray] = []
    act_buf: List[int] = []

    for ep in range(episodes):
        obs, info = env.reset(seed=seed_offset + ep)
        mask = info["valid_mask"]
        for _ in range(env_config["max_steps"]):
            valid = np.where(mask > 0)[0]
            if len(valid) == 0:
                break
            action = int(pick(env, valid))
            obs_buf.append(np.asarray(obs, dtype=np.float32))
            mask_buf.append(np.asarray(mask, dtype=np.float32))
            act_buf.append(action)
            obs, _, terminated, truncated, info = env.step(action)
            mask = info["valid_mask"]
            if terminated or truncated:
                break

    return (np.asarray(obs_buf, dtype=np.float32),
            np.asarray(mask_buf, dtype=np.float32),
            np.asarray(act_buf, dtype=np.int64))


def collect_search_demonstrations(
    env_config: Dict,
    episodes: int,
    greedy_factory,
    sample_factory,
    samples: int = 32,
    seed_offset: int = 10_000,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, float]]:
    """Expert iteration: clone the best schedule *search* finds, not the greedy rule.

    For each training DAG the prior is sampled `samples` times and only the
    lowest-makespan rollout is kept as the demonstration, with the prior's own
    greedy schedule included as a candidate so the targets can never be worse than
    the prior itself. Distilling those targets yields a policy that can exceed the
    prior rather than merely match it, and repeating the procedure with the
    distilled policy as the new prior compounds the improvement.

    `greedy_factory` and `sample_factory` are policy factories (see `evaluate`),
    so the prior may be either a heuristic or an already-trained network.
    """
    env = PFMPPOEnv(**env_config)
    greedy_policy = greedy_factory(env)
    sample_policy = sample_factory(env)

    obs_buf: List[np.ndarray] = []
    mask_buf: List[np.ndarray] = []
    act_buf: List[int] = []
    greedy_total, search_total, kept = 0.0, 0.0, 0

    for ep in range(episodes):
        seed = seed_offset + ep
        best_traj, best_ms, complete = _replay(env, seed, greedy_policy,
                                               env_config["max_steps"], record=True)
        greedy_ms = best_ms
        if not complete:
            best_traj, best_ms = None, float("inf")

        for _ in range(samples):
            traj, ms, ok = _replay(env, seed, sample_policy,
                                   env_config["max_steps"], record=True)
            if ok and ms < best_ms:
                best_ms, best_traj = ms, traj

        if best_traj is None:
            continue
        for o, m, a in best_traj:
            obs_buf.append(o)
            mask_buf.append(m)
            act_buf.append(a)
        greedy_total += greedy_ms
        search_total += best_ms
        kept += 1

    stats = {
        "episodes_kept": kept,
        "greedy_makespan": greedy_total / max(kept, 1),
        "search_makespan": search_total / max(kept, 1),
    }
    stats["search_gain_pct"] = 100.0 * (stats["greedy_makespan"] - stats["search_makespan"]) \
        / max(stats["greedy_makespan"], 1e-9)
    return (np.asarray(obs_buf, dtype=np.float32),
            np.asarray(mask_buf, dtype=np.float32),
            np.asarray(act_buf, dtype=np.int64),
            stats)


def _replay(env, seed, policy, max_steps, record=False):
    """Roll one episode under `policy`, optionally recording the trajectory.

    Returns (trajectory or None, makespan, complete).
    """
    obs, info = env.reset(seed=seed)
    mask = info["valid_mask"]
    traj = [] if record else None

    for _ in range(max_steps):
        if not np.any(mask > 0):
            break
        action = int(policy(obs, mask))
        if record:
            traj.append((np.asarray(obs, dtype=np.float32),
                         np.asarray(mask, dtype=np.float32), action))
        obs, _, terminated, truncated, info = env.step(action)
        mask = info["valid_mask"]
        if terminated or truncated:
            break

    makespan = max(env.task_finish_times.values(), default=0.0)
    return traj, makespan, env.all_scheduled()


def behaviour_clone(
    network,
    obs: np.ndarray,
    masks: np.ndarray,
    actions: np.ndarray,
    epochs: int = 30,
    batch_size: int = 256,
    lr: float = 1e-3,
    device: Optional[str] = None,
    seed: int = 0,
    verbose: bool = True,
) -> Dict[str, List[float]]:
    """Supervised warm start of the actor on expert demonstrations.

    Cross-entropy is computed over the masked action distribution the network
    already produces, so the cloned policy is immediately usable by PPO without
    any surgery on the network.
    """
    dev = torch.device(device or "cpu")
    network.to(dev)
    torch.manual_seed(seed)

    x = torch.as_tensor(obs, dtype=torch.float32, device=dev)
    m = torch.as_tensor(masks, dtype=torch.float32, device=dev)
    y = torch.as_tensor(actions, dtype=torch.long, device=dev)

    opt = torch.optim.Adam(network.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    history = {"loss": [], "accuracy": []}
    n = len(x)

    for epoch in range(epochs):
        order = rng.permutation(n)
        losses, correct = [], 0
        for start in range(0, n, batch_size):
            idx = order[start:start + batch_size]
            bx, bm, by = x[idx], m[idx], y[idx]

            probs, _ = network(bx, bm)
            # The network returns masked probabilities; go back to log-space for a
            # numerically safe cross-entropy.
            logp = torch.log(probs.clamp_min(1e-8))
            loss = F.nll_loss(logp, by)

            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
            opt.step()

            losses.append(float(loss.item()))
            correct += int((probs.argmax(dim=1) == by).sum().item())

        history["loss"].append(float(np.mean(losses)))
        history["accuracy"].append(correct / max(n, 1))
        if verbose and (epoch % 10 == 0 or epoch == epochs - 1):
            print(f"    [BC {epoch + 1:3d}/{epochs}] loss={history['loss'][-1]:.4f} "
                  f"acc={history['accuracy'][-1]:.3f}")

    return history


# ── Inference: greedy and rollout search ──────────────────────────────────────

def _episode_result(env) -> Tuple[float, float, bool]:
    makespan = max(env.task_finish_times.values(), default=0.0)
    return makespan, float(getattr(env, "total_energy", 0.0)), env.all_scheduled()


def run_episode(
    env,
    seed: int,
    policy: Callable[[np.ndarray, np.ndarray], int],
    max_steps: int,
) -> Tuple[float, float, float, bool]:
    """One episode under `policy`. Returns (reward, makespan, energy, complete)."""
    obs, info = env.reset(seed=seed)
    mask = info["valid_mask"]
    total = 0.0
    for _ in range(max_steps):
        if not np.any(mask > 0):
            break
        action = policy(obs, mask)
        obs, reward, terminated, truncated, info = env.step(action)
        mask = info["valid_mask"]
        total += reward
        if terminated or truncated:
            break
    makespan, energy, complete = _episode_result(env)
    return total, makespan, energy, complete


def make_network_policy(agent, deterministic: bool):
    """A `policy_factory` for a PPOAgent. The env argument is unused: the network
    reads everything it needs from the observation."""
    def factory(env):
        def policy(obs, mask):
            action, _, _ = agent.select_action(obs, mask, deterministic=deterministic)
            return int(action)
        return policy
    return factory


def best_of_n(
    env,
    seed: int,
    policy: Callable[[np.ndarray, np.ndarray], int],
    max_steps: int,
    n: int,
) -> Tuple[float, float, float, bool]:
    """Sample `n` schedules for one DAG and keep the lowest-makespan one.

    Every sample replays the same DAG (identical `seed`), so this is search over
    schedules for a fixed problem, not an easier problem.
    """
    best = None
    for _ in range(n):
        result = run_episode(env, seed, policy, max_steps)
        # Only complete schedules are eligible; an episode that stalls with tasks
        # unplaced would otherwise win by reporting the makespan of a partial run.
        if not result[3]:
            continue
        if best is None or result[1] < best[1]:
            best = result
    if best is None:
        return run_episode(env, seed, policy, max_steps)
    return best


def evaluate(
    env_config: Dict,
    policy_factory: Callable[[PFMPPOEnv], Callable[[np.ndarray, np.ndarray], int]],
    episodes: int,
    samples: int = 1,
    seed_offset: int = 200,
) -> Dict[str, float]:
    """Evaluate a policy over `episodes` DAGs, optionally with rollout search.

    `policy_factory` is handed the very env the episodes run in, because heuristic
    policies read live state (`admissible_pairs`, `current_time`) off it.
    """
    env = PFMPPOEnv(**env_config)
    policy = policy_factory(env)
    rewards, makespans, energies, complete = [], [], [], []

    for ep in range(episodes):
        seed = seed_offset + ep
        if samples > 1:
            r, mk, en, ok = best_of_n(env, seed, policy, env_config["max_steps"], samples)
        else:
            r, mk, en, ok = run_episode(env, seed, policy, env_config["max_steps"])
        rewards.append(r)
        makespans.append(mk)
        energies.append(en)
        complete.append(bool(ok))

    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "mean_makespan": float(np.mean(makespans)),
        "std_makespan": float(np.std(makespans)),
        "mean_energy": float(np.mean(energies)),
        "complete_rate": float(np.mean(complete)),
    }


def save_policy(network, path, *, k_pairs: int, features_per_pair: int,
                meta: Optional[Dict] = None) -> None:
    """Persist a trained CP-PPO policy so the backend can serve it.

    The payload carries the architecture parameters alongside the weights so the
    inference service can rebuild `PairScoringNetwork` without guessing.
    """
    import torch
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "arch": "pair_scoring",
        "network": network.state_dict(),
        "k_pairs": int(k_pairs),
        "features_per_pair": int(features_per_pair),
    }
    if meta:
        payload["meta"] = meta
    torch.save(payload, str(path))


def make_heuristic_policy(pick, epsilon: float = 0.0, seed: int = 0):
    """A `policy_factory` for a heuristic, optionally epsilon-perturbed.

    `epsilon = 0` is the deterministic rule. Above zero the heuristic occasionally
    takes a random legal action, which gives it a stochastic prior of its own so it
    can be given the *same* rollout budget as the learned policy. Without this,
    comparing a searched learned policy against a single greedy heuristic pass
    would credit the policy for what is really the search.
    """
    def factory(env):
        rng = np.random.default_rng(seed)

        def policy(obs, mask):
            valid = np.where(mask > 0)[0]
            if epsilon > 0 and rng.random() < epsilon:
                return int(rng.choice(valid))
            return int(pick(env, valid))

        return policy
    return factory
