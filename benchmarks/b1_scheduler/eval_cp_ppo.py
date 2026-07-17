"""
CP-PPO benchmark: critical-path-guided policy learning by iterated search
distillation, against strengthened list-scheduling heuristics.

Method
------
1. Score every candidate (task, VM) pair with a shared per-pair network, so
   selection rules of the form "argmin over pairs" are directly representable.
2. Feed it time-aware features -- wait, transfer, compute, earliest finish time
   and upward rank -- which the original state encoding omits entirely.
3. Distil search: sample N schedules from the current prior, keep the best, and
   clone it. Repeat, using the distilled policy as the next prior.

Fairness
--------
Every method is evaluated on identical DAGs under the same time model, and the
heuristic prior is given the *same* rollout budget as the learned policy. Without
that control a searched learned policy would appear to beat a single greedy
heuristic pass purely because of the search.

Usage:
    python benchmarks/b1_scheduler/eval_cp_ppo.py --rounds 2 --metrics-out out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import torch

from ml.scheduler.pfmppo import cp_ppo as C
from ml.scheduler.pfmppo import heuristics as H
from ml.scheduler.pfmppo.env import features_per_pair
from ml.scheduler.pfmppo.pair_network import PairScoringNetwork
from ml.scheduler.pfmppo.ppo_agent import PPOAgent


def build_config(args) -> dict:
    return dict(
        num_tasks=args.num_tasks,
        num_vms=args.num_vms,
        k_pairs=args.k_pairs,
        max_steps=args.num_tasks * 4,
        max_deps_per_task=3,
        seed=42,
        dag_mode="random",
        data_dir=None,
        max_files=0,
        reward_mode="makespan",
        feature_mode="rich",
        max_tasks_in_window=args.max_tasks_window,
        time_model="listsched",
    )


def main():
    p = argparse.ArgumentParser(description="CP-PPO vs strengthened heuristics")
    p.add_argument("--num-tasks", type=int, default=15)
    p.add_argument("--num-vms", type=int, default=4)
    p.add_argument("--k-pairs", type=int, default=24)
    p.add_argument("--max-tasks-window", type=int, default=6)
    p.add_argument("--episodes", type=int, default=50)
    p.add_argument("--demo-episodes", type=int, default=300)
    p.add_argument("--bc-epochs", type=int, default=60)
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--demo-samples", type=int, default=32)
    p.add_argument("--epsilon", type=float, default=0.15)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--metrics-out", type=Path, default=None)
    p.add_argument("--save-model", type=Path, default=None,
                   help="Save the trained policy for live serving (cp_ppo.pt)")
    args = p.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    cfg = build_config(args)

    print("=" * 70)
    print("CP-PPO BENCHMARK  (list-scheduling time model)")
    print("=" * 70)
    print(f"  Tasks/DAG : {args.num_tasks}   VMs: {args.num_vms}   K: {args.k_pairs}")
    print(f"  Eval      : {args.episodes} episodes, identical DAGs for every method")
    print(f"  Search    : best-of-{args.samples} at inference\n")

    results: dict = {}
    t_start = time.time()

    def record(name, res):
        results[name] = res
        print(f"  {name:38} makespan={res['mean_makespan']:8.2f} "
              f"+-{res['std_makespan']:6.2f}  energy={res['mean_energy']:9.1f}"
              f"  complete={res['complete_rate']:.2f}")

    # ── 1. Heuristics, greedy ────────────────────────────────────────────────
    print("[1/4] Strengthened heuristics (single greedy pass)")
    for name, pick in [("HEFT (upward rank + true EFT)", H.pick_heft),
                       ("Min-Min (true EFT)", H.pick_minmin),
                       ("Max-Min (true EFT)", H.pick_maxmin),
                       ("Greedy (priority order)", H.pick_greedy),
                       ("Random", H.make_random_picker(args.seed))]:
        record(name, C.evaluate(cfg, C.make_heuristic_policy(pick, 0.0), args.episodes))

    # ── 2. Heuristics with the SAME search budget ────────────────────────────
    print(f"\n[2/4] Heuristics with equal rollout budget (best-of-{args.samples})")
    for name, pick in [(f"HEFT + best-of-{args.samples}", H.pick_heft),
                       (f"Min-Min + best-of-{args.samples}", H.pick_minmin)]:
        record(name, C.evaluate(cfg, C.make_heuristic_policy(pick, args.epsilon, seed=args.seed),
                                args.episodes, samples=args.samples))

    # ── 3. Iterated search distillation ──────────────────────────────────────
    width = features_per_pair("rich")
    net = PairScoringNetwork(features_per_pair=width, k_pairs=args.k_pairs)
    agent = PPOAgent(net, lr=1e-4, gamma=1.0, epsilon=0.2)
    round_stats = []

    # Round 1 distils search around HEFT; later rounds distil search around the
    # policy learned so far.
    greedy_factory = C.make_heuristic_policy(H.pick_heft, 0.0)
    sample_factory = C.make_heuristic_policy(H.pick_heft, args.epsilon, seed=args.seed)
    prior_name = "HEFT"

    for rnd in range(1, args.rounds + 1):
        print(f"\n[3/4] Distillation round {rnd}/{args.rounds}  (prior: {prior_name})")
        t0 = time.time()
        obs, masks, acts, st = C.collect_search_demonstrations(
            cfg, args.demo_episodes, greedy_factory, sample_factory,
            samples=args.demo_samples, seed_offset=10_000 + rnd * 100_000,
        )
        print(f"    targets: {obs.shape[0]} decisions | prior greedy={st['greedy_makespan']:.2f}"
              f" -> search={st['search_makespan']:.2f} ({st['search_gain_pct']:+.1f}%)"
              f"  [{time.time() - t0:.0f}s]")

        hist = C.behaviour_clone(net, obs, masks, acts, epochs=args.bc_epochs,
                                 lr=1e-3, seed=args.seed, verbose=False)
        val = C.evaluate(cfg, C.make_network_policy(agent, True),
                         episodes=15, seed_offset=50_000)["mean_makespan"]
        print(f"    cloned: acc={hist['accuracy'][-1]:.3f}  val makespan={val:.2f}")
        round_stats.append({"round": rnd, "prior": prior_name,
                            "prior_greedy": round(st["greedy_makespan"], 2),
                            "search_target": round(st["search_makespan"], 2),
                            "clone_accuracy": round(hist["accuracy"][-1], 4),
                            "val_makespan": round(val, 2)})

        # The distilled policy becomes the prior for the next round.
        greedy_factory = C.make_network_policy(agent, True)
        sample_factory = C.make_network_policy(agent, False)
        prior_name = f"CP-PPO round {rnd}"

    # ── 4. Final comparison ──────────────────────────────────────────────────
    print("\n[4/4] CP-PPO")
    greedy_res = C.evaluate(cfg, C.make_network_policy(agent, True), args.episodes)
    record("CP-PPO (greedy, no search)", greedy_res)
    record(f"CP-PPO (best-of-{args.samples})",
           C.evaluate(cfg, C.make_network_policy(agent, False), args.episodes, samples=args.samples))

    if args.save_model:
        C.save_policy(net, args.save_model, k_pairs=args.k_pairs, features_per_pair=width,
                      meta={"greedy_makespan": round(greedy_res["mean_makespan"], 2),
                            "num_tasks": args.num_tasks, "num_vms": args.num_vms,
                            "feature_mode": "rich", "time_model": "listsched"})
        print(f"\n  saved servable policy -> {args.save_model}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    ranked = sorted(results.items(), key=lambda kv: kv[1]["mean_makespan"])
    print("\n" + "=" * 70)
    print("RANKING (lower makespan is better)")
    print("=" * 70)
    for i, (name, r) in enumerate(ranked, 1):
        star = " *" if name.startswith("CP-PPO") else ""
        print(f"  {i:2d}. {name:40} {r['mean_makespan']:8.2f}{star}")

    ours = f"CP-PPO (best-of-{args.samples})"
    baselines = {k: v for k, v in results.items() if not k.startswith("CP-PPO")}
    best_greedy = min((kv for kv in baselines.items() if "best-of" not in kv[0]),
                      key=lambda kv: kv[1]["mean_makespan"])
    best_search = min((kv for kv in baselines.items() if "best-of" in kv[0]),
                      key=lambda kv: kv[1]["mean_makespan"])

    def gap(ref):
        return 100 * (ref[1]["mean_makespan"] - results[ours]["mean_makespan"]) / ref[1]["mean_makespan"]

    g1, g2 = gap(best_greedy), gap(best_search)
    print(f"\n  vs best greedy heuristic ({best_greedy[0]}): "
          f"{'beats' if g1 > 0 else 'trails'} by {abs(g1):.1f}%")
    print(f"  vs equal-budget baseline ({best_search[0]}): "
          f"{'beats' if g2 > 0 else 'trails'} by {abs(g2):.1f}%")
    print(f"\n  total wall time: {time.time() - t_start:.0f}s")

    if args.metrics_out:
        args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_out.write_text(json.dumps({
            "config": cfg,
            "episodes": args.episodes,
            "samples": args.samples,
            "demo_episodes": args.demo_episodes,
            "rounds": args.rounds,
            "distillation_rounds": round_stats,
            "results": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in results.items()},
            "vs_best_greedy_heuristic": {"baseline": best_greedy[0], "pct": round(g1, 2)},
            "vs_equal_budget_baseline": {"baseline": best_search[0], "pct": round(g2, 2)},
        }, indent=2))
        print(f"  metrics -> {args.metrics_out}")


if __name__ == "__main__":
    main()
