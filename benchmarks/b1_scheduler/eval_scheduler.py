"""
B1 benchmark — DRL-PPO scheduler vs non-learning baselines (report §6.1).

Trains PPO on the SchedulerEnv, then evaluates PPO and each baseline
(round-robin/FIFO, least-loaded, best-fit, random) on the SAME seeded job
streams, reporting mean reward, utilisation, cluster balance, and SLA-violation
rate. Expectation (paper direction): PPO learns the joint placement+tier policy
that beats hand-written heuristics on the weighted objective.

    python eval_scheduler.py [--timesteps 40000 --episodes 30]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.scheduler.env import SchedulerEnv, compute_balance   # noqa: E402
from ml.scheduler import baselines as B                       # noqa: E402


def run_episode(env, act, seed):
    obs, _ = env.reset(seed=seed)
    total_r, utils, bals, sla = 0.0, [], [], 0
    done = False
    while not done:
        action = act(obs, env)
        obs, r, term, trunc, info = env.step(action)
        total_r += r
        utils.append(float(env.state.cpu_util.mean()))
        bals.append(compute_balance(env.state.cpu_util))
        sla += int(info.get("sla_violated", False))
        done = term or trunc
    return {"reward": total_r, "util": float(np.mean(utils)),
            "balance": float(np.mean(bals)), "sla_rate": sla / env.max_steps}


def evaluate(act, episodes, num_nodes):
    env = SchedulerEnv(num_nodes=num_nodes)
    rows = [run_episode(env, act, seed=1000 + e) for e in range(episodes)]
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timesteps", type=int, default=40000)
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--num-nodes", type=int, default=4)
    args = ap.parse_args()

    from stable_baselines3 import PPO
    print(f"Training PPO for {args.timesteps} timesteps ...")
    train_env = SchedulerEnv(num_nodes=args.num_nodes)
    model = PPO("MlpPolicy", train_env, verbose=0, seed=0)
    model.learn(total_timesteps=args.timesteps)

    def ppo_act(obs, env):
        action, _ = model.predict(obs, deterministic=True)
        return action

    policies = {"PPO (ours)": ppo_act}
    for name, fn in B.all_baselines(seed=0).items():
        policies[name] = (lambda f: (lambda obs, env: f(env)))(fn)

    print(f"\nEvaluation over {args.episodes} seeded episodes "
          f"({args.num_nodes} nodes)\n")
    print(f"{'policy':14} {'reward':>9} {'util':>7} {'balance':>8} {'SLA viol%':>10}")
    results = {}
    for name, act in policies.items():
        m = evaluate(act, args.episodes, args.num_nodes)
        results[name] = m
        print(f"{name:14} {m['reward']:9.1f} {m['util']:7.3f} "
              f"{m['balance']:8.3f} {100*m['sla_rate']:10.2f}")

    best_base = max((m["reward"] for n, m in results.items() if n != "PPO (ours)"))
    ppo_r = results["PPO (ours)"]["reward"]
    print(f"\nPPO reward {ppo_r:.1f} vs best baseline {best_base:.1f}  "
          f"({'+' if ppo_r>=best_base else ''}{100*(ppo_r-best_base)/abs(best_base):.1f}%). "
          "PPO also targets lower SLA violations + higher balance.")


if __name__ == "__main__":
    main()
