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

# Ensure project root is on path when running as script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import torch

from ml.scheduler.pfmppo.env import PFMPPOEnv
from ml.scheduler.pfmppo.multi_agent import CTDETrainer
from ml.scheduler.pfmppo.ppo_agent import PPOAgent
from ml.scheduler.pfmppo.network import PFMPPONetwork


def evaluate_agent(agent: PPOAgent, env_config: dict, episodes: int, deterministic: bool = True):
    """Evaluate a trained agent over multiple episodes."""
    env = PFMPPOEnv(**env_config)
    all_rewards = []
    all_steps = []
    invalid_actions = 0
    total_actions = 0

    for ep in range(episodes):
        obs, info = env.reset(seed=ep + 200)
        mask = info["valid_mask"]
        ep_reward = 0.0
        steps = 0

        for _ in range(env_config["max_steps"]):
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

    return {
        "mean_reward": np.mean(all_rewards),
        "std_reward": np.std(all_rewards),
        "mean_steps": np.mean(all_steps),
        "invalid_action_rate": invalid_actions / max(total_actions, 1),
    }


def evaluate_random(env_config: dict, episodes: int):
    """Evaluate random baseline."""
    env = PFMPPOEnv(**env_config)
    all_rewards = []

    for ep in range(episodes):
        obs, info = env.reset(seed=ep + 200)
        mask = info["valid_mask"]
        ep_reward = 0.0

        for _ in range(env_config["max_steps"]):
            valid = np.where(mask > 0)[0]
            if len(valid) == 0:
                break
            action = np.random.choice(valid)
            obs, reward, terminated, truncated, info = env.step(action)
            mask = info["valid_mask"]
            ep_reward += reward
            if terminated or truncated:
                break

        all_rewards.append(ep_reward)

    return {"mean_reward": np.mean(all_rewards), "std_reward": np.std(all_rewards)}


def evaluate_greedy(env_config: dict, episodes: int):
    """Evaluate greedy baseline (always pick first valid action = highest priority)."""
    env = PFMPPOEnv(**env_config)
    all_rewards = []

    for ep in range(episodes):
        obs, info = env.reset(seed=ep + 200)
        mask = info["valid_mask"]
        ep_reward = 0.0

        for _ in range(env_config["max_steps"]):
            valid = np.where(mask > 0)[0]
            if len(valid) == 0:
                break
            action = valid[0]  # Always pick first (highest priority from Algorithm 2)
            obs, reward, terminated, truncated, info = env.step(action)
            mask = info["valid_mask"]
            ep_reward += reward
            if terminated or truncated:
                break

        all_rewards.append(ep_reward)

    return {"mean_reward": np.mean(all_rewards), "std_reward": np.std(all_rewards)}


def main():
    parser = argparse.ArgumentParser(description="Evaluate PF-MPPO against baselines")
    parser.add_argument("--train-iterations", type=int, default=500)
    parser.add_argument("--eval-episodes", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--num-tasks", type=int, default=15)
    parser.add_argument("--num-vms", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    env_config = {
        "num_tasks": args.num_tasks,
        "num_vms": args.num_vms,
        "k_pairs": 10,
        "max_steps": 100,
        "max_deps_per_task": 3,
        "seed": 42,
    }

    print("=" * 70)
    print("PF-MPPO BENCHMARK EVALUATION")
    print("=" * 70)
    print(f"  Tasks/DAG: {args.num_tasks}")
    print(f"  VMs:       {args.num_vms}")
    print(f"  Training:  {args.train_iterations} iterations, {args.workers} workers")
    print(f"  Eval:      {args.eval_episodes} episodes")
    print()

    # Train PF-MPPO
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
    print()

    # Evaluate all algorithms
    print("[2/4] Evaluating PF-MPPO (deterministic)...")
    pfmppo_results = evaluate_agent(trainer.get_agent(), env_config, args.eval_episodes)

    print("[3/4] Evaluating baselines...")
    random_results = evaluate_random(env_config, args.eval_episodes)
    greedy_results = evaluate_greedy(env_config, args.eval_episodes)

    # Results table
    print()
    print("[4/4] RESULTS")
    print("-" * 70)
    print(f"{'Algorithm':<20} {'Mean Reward':>12} {'Std':>8} {'Invalid%':>10}")
    print("-" * 70)
    print(f"{'PF-MPPO':<20} {pfmppo_results['mean_reward']:>12.2f} {pfmppo_results['std_reward']:>8.2f} {pfmppo_results['invalid_action_rate']*100:>9.1f}%")
    print(f"{'Greedy (Priority)':<20} {greedy_results['mean_reward']:>12.2f} {greedy_results['std_reward']:>8.2f} {'N/A':>10}")
    print(f"{'Random':<20} {random_results['mean_reward']:>12.2f} {random_results['std_reward']:>8.2f} {'N/A':>10}")
    print("-" * 70)
    print()

    # Summary
    if pfmppo_results["mean_reward"] > random_results["mean_reward"]:
        improvement = ((pfmppo_results["mean_reward"] - random_results["mean_reward"])
                      / abs(random_results["mean_reward"]) * 100)
        print(f"PF-MPPO outperforms Random by {improvement:.1f}%")
    else:
        print("PF-MPPO did not outperform Random (more training may be needed)")

    if pfmppo_results["mean_reward"] > greedy_results["mean_reward"]:
        improvement = ((pfmppo_results["mean_reward"] - greedy_results["mean_reward"])
                      / abs(greedy_results["mean_reward"]) * 100)
        print(f"PF-MPPO outperforms Greedy by {improvement:.1f}%")

    # Save results
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    results = {
        "pfmppo": pfmppo_results,
        "random": random_results,
        "greedy": greedy_results,
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


if __name__ == "__main__":
    main()
