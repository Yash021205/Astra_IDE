"""
PF-MPPO Benchmark Evaluation.

Trains PF-MPPO and compares against baselines on DAG scheduling workloads.
Reports: makespan, avg response time, total energy, load balance, SLA violations.

Usage:
    python benchmarks/b1_scheduler/eval_pfmppo.py [--train-iterations 500] [--eval-episodes 20]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Tuple

# Ensure project root is on path when running as script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import torch

from ml.scheduler.pfmppo.env import PFMPPOEnv
from ml.scheduler.pfmppo.multi_agent import CTDETrainer
from ml.scheduler.pfmppo.ppo_agent import PPOAgent
from ml.scheduler.pfmppo.network import PFMPPONetwork
from ml.scheduler.pfmppo.math_models import computation_time


def _episode_makespan_energy(env) -> Tuple[float, float]:
    """Objective metrics of the completed episode: makespan (max task finish time)
    and total energy consumed — the quantities the paper actually reports."""
    makespan = max(env.task_finish_times.values(), default=0.0)
    return makespan, float(getattr(env, "total_energy", 0.0))


def evaluate_agent(agent: PPOAgent, env_config: dict, episodes: int, deterministic: bool = True):
    """Evaluate a trained agent over multiple episodes."""
    env = PFMPPOEnv(**env_config)
    all_rewards, all_steps, makespans, energies = [], [], [], []
    invalid_actions = 0
    total_actions = 0

    for ep in range(episodes):
        obs, info = env.reset(seed=ep + 200)
        mask = info["valid_mask"]
        ep_reward = 0.0
        steps = 0

        for _ in range(env_config["max_steps"]):
            # Fairness: the Random/Greedy baselines below stop when no action is
            # valid (a task is waiting on unfinished dependencies). PF-MPPO must do
            # the same, else it alone eats the invalid-action penalty for "waiting".
            if not np.any(mask > 0):
                break
            action, _, _ = agent.select_action(obs, mask, deterministic=deterministic)
            obs, reward, terminated, truncated, info = env.step(action)
            mask = info["valid_mask"]
            ep_reward += reward
            steps += 1
            total_actions += 1
            if info.get("invalid_action"):
                invalid_actions += 1
            if terminated or truncated:
                break

        all_rewards.append(ep_reward)
        all_steps.append(steps)
        mk, en = _episode_makespan_energy(env)
        makespans.append(mk)
        energies.append(en)

    return {
        "mean_reward": np.mean(all_rewards),
        "std_reward": np.std(all_rewards),
        "mean_steps": np.mean(all_steps),
        "mean_makespan": np.mean(makespans),
        "mean_energy": np.mean(energies),
        "invalid_action_rate": invalid_actions / max(total_actions, 1),
    }


def _est_finish(task, vm) -> float:
    """Estimated completion time of a task on a VM (compute + duration). Heterogeneity
    enters via vm.proc_rate_mbps: faster VMs finish sooner."""
    return computation_time(task.data_size_mb, vm.proc_rate_mbps) + task.t_dur


def _run_baseline(env_config: dict, episodes: int, pick):
    """Run a heuristic that chooses an action index from the valid set each step, and
    report reward + makespan + energy uniformly (same seeds as evaluate_agent)."""
    env = PFMPPOEnv(**env_config)
    all_rewards, makespans, energies = [], [], []
    for ep in range(episodes):
        obs, info = env.reset(seed=ep + 200)
        mask = info["valid_mask"]
        ep_reward = 0.0
        for _ in range(env_config["max_steps"]):
            valid = np.where(mask > 0)[0]
            if len(valid) == 0:
                break
            action = int(pick(env, valid))
            obs, reward, terminated, truncated, info = env.step(action)
            mask = info["valid_mask"]
            ep_reward += reward
            if terminated or truncated:
                break
        all_rewards.append(ep_reward)
        mk, en = _episode_makespan_energy(env)
        makespans.append(mk)
        energies.append(en)
    return {"mean_reward": np.mean(all_rewards), "std_reward": np.std(all_rewards),
            "mean_makespan": np.mean(makespans), "mean_energy": np.mean(energies)}


def _pick_random(env, valid):
    return np.random.choice(valid)


def _pick_greedy(env, valid):
    return valid[0]                                   # highest-priority ready pair (Algorithm 2)


def _pick_minmin(env, valid):
    pairs = env.admissible_pairs                      # global min estimated completion time
    return min(valid, key=lambda i: _est_finish(*pairs[i]))


def _pick_heft(env, valid):
    pairs = env.admissible_pairs                      # top task -> earliest-finish VM
    top_task = pairs[valid[0]][0].task_id
    cand = [i for i in valid if pairs[i][0].task_id == top_task]
    return min(cand, key=lambda i: _est_finish(*pairs[i]))


def evaluate_random(env_config, episodes):
    return _run_baseline(env_config, episodes, _pick_random)


def evaluate_greedy(env_config, episodes):
    return _run_baseline(env_config, episodes, _pick_greedy)


def evaluate_minmin(env_config, episodes):
    return _run_baseline(env_config, episodes, _pick_minmin)


def evaluate_heft(env_config, episodes):
    return _run_baseline(env_config, episodes, _pick_heft)


def main():
    parser = argparse.ArgumentParser(description="Evaluate PF-MPPO against baselines")
    parser.add_argument("--train-iterations", type=int, default=500)
    parser.add_argument("--eval-episodes", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--num-tasks", type=int, default=15)
    parser.add_argument("--num-vms", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--model-path", type=str, default=None,
                        help="evaluate this trained model instead of training a fresh one")
    parser.add_argument("--dag-mode", type=str, default="random",
                        help="workload distribution for eval (random|template|hybrid|trace_hybrid)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Google-trace dir (required for trace/trace_hybrid eval)")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--metrics-out", type=str, default=None,
                        help="append the PPO-vs-baselines table to this metrics.json")
    parser.add_argument("--reward-mode", type=str, default="shaped",
                        choices=["paper", "shaped"],
                        help="'shaped' = objective-aligned reward (makespan+energy); "
                             "'paper' = Eq 30 log reward")
    args = parser.parse_args()

    env_config = {
        "num_tasks": args.num_tasks,
        "num_vms": args.num_vms,
        "k_pairs": 10,
        "max_steps": 100,
        "max_deps_per_task": 3,
        "seed": 42,
        "dag_mode": args.dag_mode,
        "data_dir": args.data_dir,
        "max_files": args.max_files,
        "reward_mode": args.reward_mode,
    }

    print("=" * 70)
    print("PF-MPPO BENCHMARK EVALUATION")
    print("=" * 70)
    print(f"  Tasks/DAG: {args.num_tasks}")
    print(f"  VMs:       {args.num_vms}")
    if args.model_path:
        print(f"  Model:     {args.model_path} (loaded, not trained here)")
    else:
        print(f"  Training:  {args.train_iterations} iterations, {args.workers} workers")
    print(f"  Eval:      {args.eval_episodes} episodes  |  DAG mode: {args.dag_mode}")
    print()

    # Load a committed model, or train a fresh one.
    train_time = 0.0
    if args.model_path:
        print(f"[1/4] Loading trained PF-MPPO model: {args.model_path}")
        network = PFMPPONetwork(input_dim=10 * 10, k_pairs=10)
        agent = PPOAgent(network=network, lr=0.001, gamma=0.9, epsilon=0.2)
        agent.load(args.model_path)
    else:
        print("[1/4] Training PF-MPPO agent...")
        t0 = time.time()
        trainer = CTDETrainer(
            num_workers=args.workers,
            env_config=env_config,
            k_pairs=10,
            lr=0.001,
            batch_size=args.batch_size,
            gamma=0.9,
            epsilon=0.2,
        )
        metrics = trainer.train(iterations=args.train_iterations, log_interval=args.train_iterations // 4)
        train_time = time.time() - t0
        print(f"    Training time: {train_time:.1f}s")
        print(f"    Final mean reward: {metrics['mean_reward'][-1]:.4f}")
        agent = trainer.get_agent()
    print()

    # Evaluate all algorithms
    print("[2/4] Evaluating PF-MPPO (deterministic)...")
    pfmppo_results = evaluate_agent(agent, env_config, args.eval_episodes)

    print("[3/4] Evaluating baselines (HEFT, Min-Min, Greedy, Random)...")
    heft_results = evaluate_heft(env_config, args.eval_episodes)
    minmin_results = evaluate_minmin(env_config, args.eval_episodes)
    greedy_results = evaluate_greedy(env_config, args.eval_episodes)
    random_results = evaluate_random(env_config, args.eval_episodes)

    # Results table (higher reward is better; reward = -cost)
    baselines = {
        "HEFT": heft_results,
        "Min-Min": minmin_results,
        "Greedy (Priority)": greedy_results,
        "Random": random_results,
    }
    print()
    print("[4/4] RESULTS")
    print("-" * 70)
    print(f"{'Algorithm':<20} {'Mean Reward':>12} {'Std':>8} {'Invalid%':>10}")
    print("-" * 70)
    print(f"{'PF-MPPO':<20} {pfmppo_results['mean_reward']:>12.2f} {pfmppo_results['std_reward']:>8.2f} {pfmppo_results['invalid_action_rate']*100:>9.1f}%")
    for name, res in baselines.items():
        print(f"{name:<20} {res['mean_reward']:>12.2f} {res['std_reward']:>8.2f} {'N/A':>10}")
    print("-" * 70)
    print()

    # Objective metrics the paper actually reports: makespan + energy (lower is better).
    print()
    print("Makespan / Energy (lower is better) - the paper's reported objectives:")
    print(f"{'Algorithm':<20} {'Makespan':>12} {'Energy':>12}")
    print("-" * 46)
    print(f"{'PF-MPPO':<20} {pfmppo_results['mean_makespan']:>12.2f} {pfmppo_results['mean_energy']:>12.1f}")
    for name, res in baselines.items():
        print(f"{name:<20} {res['mean_makespan']:>12.2f} {res['mean_energy']:>12.1f}")
    print()

    # Summary: PF-MPPO vs each baseline on makespan (the headline scheduling metric).
    ppo_mk = pfmppo_results["mean_makespan"]
    for name, res in baselines.items():
        b = res["mean_makespan"]
        if ppo_mk < b:
            print(f"PF-MPPO beats {name} on makespan by {(b - ppo_mk) / b * 100:.1f}%")
        else:
            print(f"PF-MPPO trails {name} on makespan by {(ppo_mk - b) / b * 100:.1f}%")

    # Save results
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    results = {
        "pfmppo": pfmppo_results,
        "heft": heft_results,
        "minmin": minmin_results,
        "greedy": greedy_results,
        "random": random_results,
        "config": env_config,
        "train_iterations": args.train_iterations,
        "train_time_s": round(train_time, 1),
    }
    # Convert numpy types for JSON serialization
    def convert(obj):
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        return obj

    with open(out_dir / "pfmppo_benchmark.json", "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out_dir / 'pfmppo_benchmark.json'}")

    # Merge the real PPO-vs-baselines table into the served artifact metrics.
    if args.metrics_out:
        mp = Path(args.metrics_out)
        base = {}
        if mp.exists():
            try:
                base = json.loads(mp.read_text())
            except ValueError:
                base = {}
        best_baseline = max(b["mean_reward"] for b in baselines.values())
        base["eval"] = {
            "dag_mode": args.dag_mode,
            "eval_episodes": args.eval_episodes,
            "num_tasks": args.num_tasks,
            "mean_reward": {
                "pfmppo": round(float(pfmppo_results["mean_reward"]), 3),
                "heft": round(float(heft_results["mean_reward"]), 3),
                "minmin": round(float(minmin_results["mean_reward"]), 3),
                "greedy_priority": round(float(greedy_results["mean_reward"]), 3),
                "random": round(float(random_results["mean_reward"]), 3),
            },
            "pfmppo_beats_best_baseline": bool(pfmppo_results["mean_reward"] > best_baseline),
            "pfmppo_invalid_action_rate": round(float(pfmppo_results["invalid_action_rate"]), 4),
            "note": "higher reward is better (reward = -cost); baselines are the paper's HEFT/Min-Min + Greedy/Random",
        }
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(base, indent=2))
        print(f"merged eval table -> {mp}")


if __name__ == "__main__":
    main()
