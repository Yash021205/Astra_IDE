# PF-MPPO model artifact provenance

- **model.pt** - trained PF-MPPO (PPO) scheduler policy. (Recommit after the next
  paper-faithful training run; see below.)
- **metrics.json** - training config + evaluation numbers.

## Hyperparameters (match the paper: PF-MPPO, Future Generation Computer Systems 2025, Table 2)
- Discount factor gamma = 0.9, PPO clip = 0.2, Adam, ReLU.
- Actor and Critic learning rate = 0.001 (pretrain), 0.0001 (fine-tune).
- Number of hidden layers = 5 (input + 5 hidden + output = 7 layers).
- Mini-batch = 1000, iterations N = 2000, workers = 9.
- Reward weights alpha1/alpha2/alpha3 = 0.34/0.33/0.33 (latency/energy/load-balance),
  from Table 2 (alpha2 = alpha3 = 0.33).

## Dataset
- **The paper validates on the Alibaba Cluster-trace-v2018** (8 days, ~4000 servers).
- **We validate on the Google Cluster Trace 2011** (`clusterdata-2011-2`), another real
  public production trace with DAG task structure, loaded via
  `ml/scheduler/pfmppo/google_trace_loader.py`. This is a documented substitution of one
  real production trace for another; the method and hyperparameters follow the paper.

## Status
The previously committed model.pt was trained before the code was corrected to the paper's
reward weights (0.34/0.33/0.33) and 5-hidden-layer network, so it was removed (it no longer
matches the architecture). Until a fresh model.pt is committed, the backend uses the heuristic
scorer (graceful fallback). To produce the paper-faithful model:

1. Run `notebooks/b1_scheduler_kaggle.py` on Kaggle (it now trains with 2000 iterations, 9
   workers, and the corrected reward + network).
2. Download `ml/scheduler/pfmppo/artifacts/{model.pt, metrics.json}` and commit them.

## Paper's reported results (for reference)
PF-MPPO reduces latency by 1.2% to 28.4% and energy consumption by 2.5% to 40.1% versus the
compared DRL baselines, while maintaining load balancing.
