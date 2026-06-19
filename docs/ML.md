# ML Training Procedure

## PPO Scheduler

```bash
pip install -r ml/requirements.txt
python -m ml.scheduler.train --timesteps 100000 --num-nodes 4 --out runs/ppo
```

Outputs:
- `runs/ppo/model.zip`            — Stable-Baselines3 policy
- `runs/ppo/tensorboard/`         — TensorBoard logs

Visualize:
```bash
tensorboard --logdir runs/ppo/tensorboard
```

### State space (40-dim)

Per-node features (4 × N_nodes):
| Index range | Meaning |
|---|---|
| `[0:N]`     | CPU utilization, normalized to [0, 1] |
| `[N:2N]`    | Memory utilization, normalized |
| `[2N:3N]`   | Run queue length |
| `[3N:4N]`   | Network load |

Pending job features (6):
| Index | Meaning |
|---|---|
| 0     | CPU request / 4.0 |
| 1     | Memory request / 8GB |
| 2     | Language ID, normalized |
| 3     | Risk score [0, 1] |
| 4     | Network access requested (0/1) |
| 5     | Filesystem write (0/1) |

Cluster features (4):
| Index | Meaning |
|---|---|
| 0     | Carbon intensity, normalized |
| 1     | sin(time_of_day) |
| 2     | cos(time_of_day) |
| 3     | Warm pool count / 10 |

### Action space (MultiDiscrete[4, 3, 2, 2])

| Dim | Choices | Meaning |
|---|---|---|
| 0   | 0..N-1  | Target node index |
| 1   | 0, 1, 2 | Sandbox tier (runc, gvisor, firecracker) |
| 2   | 0, 1    | Prewarm decision |
| 3   | 0, 1    | Cross-cluster migrate |

### Reward function

See `ml/scheduler/reward.py`. Default weights (sum to 1.0):
- 0.35 × inverse latency
- 0.25 × resource utilization
- 0.15 × cluster balance
- 0.10 × inverse energy cost
- 0.10 × inverse carbon intensity
- 0.05 × co-location synergy
- − 10.0 if SLA violated

---

## LSTM Prewarming

```bash
python -m ml.prewarming.train --users 100 --days 30 --epochs 20 --out runs/lstm
```

Outputs:
- `runs/lstm/model.pt`        — PyTorch weights
- `runs/lstm/metrics.json`    — precision / recall / F1

Architecture:
```
(seq=10, features=4) → LSTM(128) → LSTM(64) → Dense(32, ReLU) → Sigmoid → P(session)
```

Features per session:
- sin(hour) — normalized
- cos(hour) — normalized
- weekday / 6
- language_id / |vocab|

Label: 1 if next session within `horizon_minutes` (default 15), else 0.

Target F1 ≥ 0.75 on held-out users.

---

## Risk Scorer

Pure-function, no training needed. Default thresholds:
- `risk < 0.30`  → runc
- `risk < 0.70`  → gvisor
- `risk ≥ 0.70`  → firecracker

Configurable via the `RiskScorer` dataclass — useful for ablation experiments
where you sweep thresholds and weights.

---

## Reproducibility

All training scripts accept `--seed`. Random numpy / PyTorch state is seeded
deterministically. Synthetic data generators are also seeded so runs can be
replayed for paper figures.

For benchmark comparisons (Phase 6 / Week 7), use the same seed across:
- PPO baseline (default scheduler, random, round-robin)
- Our PPO model evaluation
