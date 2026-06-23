"""
Pre-train PF-MPPO models for all cluster configurations in the Rule Library.

Usage:
    python -m ml.scheduler.pfmppo.pretrain_all --configs-dir ml/scheduler/pfmppo/configs/ --out-dir rule_library/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-train PF-MPPO for all cluster configs")
    parser.add_argument("--configs-dir", type=str, default="ml/scheduler/pfmppo/configs",
                        help="Directory containing cluster config JSON files")
    parser.add_argument("--out-dir", type=str, default="rule_library",
                        help="Output directory for the rule library")
    parser.add_argument("--iterations", type=int, default=2000, help="Iterations per config")
    parser.add_argument("--workers", type=int, default=9, help="Worker agents")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size")
    parser.add_argument("--k-pairs", type=int, default=10, help="K pairs")
    parser.add_argument("--num-tasks", type=int, default=20, help="Tasks per DAG")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    args = parser.parse_args()

    try:
        import numpy as np
        from ml.scheduler.pfmppo.multi_agent import CTDETrainer
        from ml.scheduler.pfmppo.dag_generator import load_vm_configs
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    configs_dir = Path(args.configs_dir)
    out_dir = Path(args.out_dir)

    if not configs_dir.exists():
        print(f"ERROR: Configs directory not found: {configs_dir}", file=sys.stderr)
        return 1

    config_files = sorted(configs_dir.glob("*.json"))
    if not config_files:
        print(f"ERROR: No JSON config files found in {configs_dir}", file=sys.stderr)
        return 1

    print(f"PF-MPPO Pre-training Pipeline")
    print(f"  Configs: {len(config_files)} files in {configs_dir}")
    print(f"  Output:  {out_dir}")
    print(f"  Iterations per config: {args.iterations}")
    print(f"  Workers: {args.workers}")
    print()

    for idx, config_path in enumerate(config_files):
        config_name = config_path.stem
        model_dir = out_dir / config_name
        model_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{idx+1}/{len(config_files)}] Training: {config_name}")
        print(f"  Config: {config_path}")

        vm_configs = load_vm_configs(str(config_path))
        num_vms = len(vm_configs)
        print(f"  VMs: {num_vms}")

        env_config = {
            "num_tasks": args.num_tasks,
            "num_vms": num_vms,
            "k_pairs": args.k_pairs,
            "max_steps": 200,
            "max_deps_per_task": 3,
            "vm_configs": vm_configs,
            "seed": args.seed + idx * 100,
        }

        trainer = CTDETrainer(
            num_workers=args.workers,
            env_config=env_config,
            k_pairs=args.k_pairs,
            lr=0.001,
            gamma=0.9,
            epsilon=0.2,
            batch_size=args.batch_size,
        )

        metrics = trainer.train(iterations=args.iterations, log_interval=args.iterations // 5)

        # Save model
        model_path = str(model_dir / "model.pt")
        trainer.save(model_path)

        # Save metadata for rule library
        config_features = _compute_config_features(vm_configs)
        metadata = {
            "config_name": config_name,
            "num_vms": num_vms,
            "iterations": args.iterations,
            "config_features": config_features.tolist(),
            "final_metrics": {
                "mean_reward": metrics["mean_reward"][-1] if metrics["mean_reward"] else 0,
            },
        }
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"  Saved to {model_dir}")
        print()

    print("Pre-training complete!")
    return 0


def _compute_config_features(vm_configs):
    import numpy as np
    cpu_caps = [v.get("cpu_cap", 4.0) for v in vm_configs]
    mem_caps = [v.get("mem_cap", 8192.0) for v in vm_configs]
    disk_caps = [v.get("disk_cap", 102400.0) for v in vm_configs]
    bws = [v.get("bandwidth_mbps", 1000.0) for v in vm_configs]
    proc_rates = [v.get("proc_rate_mbps", 200.0) for v in vm_configs]
    powers = [v.get("power_max_w", 200.0) for v in vm_configs]
    return np.array([
        np.mean(cpu_caps),
        np.mean(mem_caps) / 1000.0,
        np.mean(disk_caps) / 10000.0,
        np.mean(bws) / 1000.0,
        np.mean(proc_rates) / 100.0,
        np.mean(powers) / 100.0,
    ], dtype=np.float32)


if __name__ == "__main__":
    raise SystemExit(main())
