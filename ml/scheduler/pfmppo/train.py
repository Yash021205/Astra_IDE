"""
PF-MPPO Training entrypoint.

Usage:
    python -m ml.scheduler.pfmppo.train --mode pretrain --config ml/scheduler/pfmppo/configs/4_nodes.json --iterations 2000 --workers 9 --out runs/pfmppo/

Modes:
    pretrain: Stage 1 training from scratch (LR=0.001)
    finetune: Stage 2 fine-tuning from existing model (LR=0.0001)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train PF-MPPO scheduler")
    parser.add_argument("--mode", choices=["pretrain", "finetune"], default="pretrain",
                        help="Training mode: pretrain (Stage 1) or finetune (Stage 2)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to cluster config JSON file")
    parser.add_argument("--model-path", type=str, default=None,
                        help="Path to existing model (required for finetune mode)")
    parser.add_argument("--iterations", type=int, default=2000,
                        help="Number of training iterations")
    parser.add_argument("--workers", type=int, default=9,
                        help="Number of parallel worker agents")
    parser.add_argument("--lr", type=float, default=None,
                        help="Learning rate (default: 0.001 for pretrain, 0.0001 for finetune)")
    parser.add_argument("--batch-size", type=int, default=1000,
                        help="Transitions per iteration across all workers")
    parser.add_argument("--gamma", type=float, default=0.9, help="Discount factor")
    parser.add_argument("--epsilon", type=float, default=0.2, help="PPO clip ratio")
    parser.add_argument("--k-pairs", type=int, default=10, help="Number of (task, VM) pairs (K)")
    parser.add_argument("--num-tasks", type=int, default=20, help="Tasks per DAG")
    parser.add_argument("--num-vms", type=int, default=4, help="VMs in the cluster (overridden by config)")
    parser.add_argument("--max-steps", type=int, default=200, help="Max steps per episode")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default="runs/pfmppo", help="Output directory")
    parser.add_argument("--log-interval", type=int, default=100, help="Log every N iterations")
    parser.add_argument("--dag-mode", choices=["random", "template", "hybrid", "trace", "trace_hybrid"],
                        default="hybrid",
                        help="DAG generation mode: random (synthetic), template (IDE workloads), hybrid (mix), trace (Google cluster trace), trace_hybrid (trace + random)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Path to Google cluster trace data directory (required for trace/trace_hybrid mode)")
    parser.add_argument("--num-workspaces-min", type=int, default=3,
                        help="Min simultaneous workspaces per episode (template/hybrid mode)")
    parser.add_argument("--num-workspaces-max", type=int, default=8,
                        help="Max simultaneous workspaces per episode (template/hybrid mode)")
    parser.add_argument("--template-ratio", type=float, default=0.7,
                        help="Fraction of episodes using templates in hybrid mode")
    parser.add_argument("--max-files", type=int, default=10,
                        help="Trace files to load in trace mode (0 = the FULL dataset)")
    args = parser.parse_args()

    try:
        import torch
        import numpy as np
    except ImportError:
        print("ERROR: PyTorch is not installed.", file=sys.stderr)
        print("Install ML deps: pip install -r ml/requirements.txt", file=sys.stderr)
        return 1

    try:
        from ml.scheduler.pfmppo.multi_agent import CTDETrainer
        from ml.scheduler.pfmppo.dag_generator import load_vm_configs
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Determine learning rate
    if args.lr is not None:
        lr = args.lr
    else:
        lr = 0.001 if args.mode == "pretrain" else 0.0001

    # Load VM configs if provided
    vm_configs = None
    num_vms = args.num_vms
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            vm_configs = load_vm_configs(str(config_path))
            num_vms = len(vm_configs)
            print(f"Loaded {num_vms} VM configs from {config_path}")
        else:
            print(f"WARNING: Config file not found: {config_path}", file=sys.stderr)

    # Validate trace mode requirements
    if args.dag_mode in ("trace", "trace_hybrid") and not args.data_dir:
        print("ERROR: --data-dir is required for trace/trace_hybrid mode", file=sys.stderr)
        return 1

    # Build env config
    env_config = {
        "num_tasks": args.num_tasks,
        "num_vms": num_vms,
        "k_pairs": args.k_pairs,
        "max_steps": args.max_steps,
        "max_deps_per_task": 3,
        "vm_configs": vm_configs,
        "seed": args.seed,
        "dag_mode": args.dag_mode,
        "num_workspaces": (args.num_workspaces_min, args.num_workspaces_max),
        "template_ratio": args.template_ratio,
        "data_dir": args.data_dir,
        "max_files": args.max_files,
    }

    # Create output directory
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"PF-MPPO Training")
    print(f"  Mode:       {args.mode}")
    print(f"  DAG mode:   {args.dag_mode}")
    print(f"  Workers:    {args.workers}")
    print(f"  Iterations: {args.iterations}")
    print(f"  LR:         {lr}")
    print(f"  Batch:      {args.batch_size}")
    print(f"  Gamma:      {args.gamma}")
    print(f"  Epsilon:    {args.epsilon}")
    print(f"  K-pairs:    {args.k_pairs}")
    print(f"  Num tasks:  {args.num_tasks}")
    print(f"  Num VMs:    {num_vms}")
    if args.dag_mode != "random":
        print(f"  Workspaces: {args.num_workspaces_min}-{args.num_workspaces_max}")
        print(f"  Template%:  {args.template_ratio * 100:.0f}%")
    print(f"  Output:     {out_dir}")
    print()

    # Create trainer
    trainer = CTDETrainer(
        num_workers=args.workers,
        env_config=env_config,
        k_pairs=args.k_pairs,
        lr=lr,
        gamma=args.gamma,
        epsilon=args.epsilon,
        batch_size=args.batch_size,
        update_epochs=4,
        mini_batch_size=64,
    )

    # Load existing model for fine-tuning
    if args.mode == "finetune":
        if not args.model_path:
            print("ERROR: --model-path required for finetune mode", file=sys.stderr)
            return 1
        model_path = Path(args.model_path)
        if not model_path.exists():
            print(f"ERROR: Model not found: {model_path}", file=sys.stderr)
            return 1
        trainer.load(str(model_path))
        print(f"Loaded pre-trained model from {model_path}")

    # Train
    metrics = trainer.train(iterations=args.iterations, log_interval=args.log_interval)

    # Save model
    model_save_path = str(out_dir / "model.pt")
    trainer.save(model_save_path)
    print(f"\nSaved model to {model_save_path}")

    # Save training metadata
    metadata = {
        "mode": args.mode,
        "dag_mode": args.dag_mode,
        "iterations": args.iterations,
        "workers": args.workers,
        "lr": lr,
        "batch_size": args.batch_size,
        "gamma": args.gamma,
        "epsilon": args.epsilon,
        "k_pairs": args.k_pairs,
        "num_tasks": args.num_tasks,
        "num_vms": num_vms,
        "config": args.config,
        "final_metrics": {
            "actor_loss": metrics["actor_loss"][-1] if metrics["actor_loss"] else 0,
            "critic_loss": metrics["critic_loss"][-1] if metrics["critic_loss"] else 0,
            "entropy": metrics["entropy"][-1] if metrics["entropy"] else 0,
            "mean_reward": metrics["mean_reward"][-1] if metrics["mean_reward"] else 0,
        },
    }
    metadata_path = out_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {metadata_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
