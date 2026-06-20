"""
Training script for the PPO scheduler.

Usage:
    python -m ml.scheduler.train --timesteps 100000 --num-nodes 4 --out runs/ppo

Outputs:
    runs/ppo/model.zip         The trained Stable-Baselines3 policy
    runs/ppo/tensorboard/      TB logs (rewards, value loss, entropy)

Following the spec we train in two phases:
  Phase 1 (offline): synthetic workloads sampled by the env
  Phase 2 (online):  fine-tune against telemetry replay (TODO once eBPF live)

This script handles Phase 1.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train PPO scheduler on simulated cluster")
    parser.add_argument("--timesteps", type=int, default=100_000,
                        help="Total training timesteps (default: 100k)")
    parser.add_argument("--num-nodes", type=int, default=4,
                        help="Number of simulated cluster nodes")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-steps", type=int, default=2048,
                        help="Steps per rollout (PPO horizon)")
    parser.add_argument("--out", type=str, default="runs/ppo",
                        help="Output directory for model + logs")
    args = parser.parse_args()

    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.env_checker import check_env
        from stable_baselines3.common.callbacks import EvalCallback
    except ImportError:
        print("ERROR: stable-baselines3 is not installed.", file=sys.stderr)
        print("Install ML deps:  pip install -r ml/requirements.txt", file=sys.stderr)
        return 1

    from ml.scheduler.env import SchedulerEnv

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    env      = SchedulerEnv(num_nodes=args.num_nodes, seed=args.seed)
    eval_env = SchedulerEnv(num_nodes=args.num_nodes, seed=args.seed + 1)
    check_env(env, warn=True)

    model = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        verbose=1,
        seed=args.seed,
        tensorboard_log=str(out_dir / "tensorboard"),
    )

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=str(out_dir / "best"),
        log_path=str(out_dir / "eval"),
        eval_freq=max(5000, args.n_steps),
        deterministic=True,
        render=False,
    )

    model.learn(total_timesteps=args.timesteps, callback=eval_callback)
    model.save(out_dir / "model")
    print(f"Saved trained model to {out_dir / 'model.zip'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
