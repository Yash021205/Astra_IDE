# PF-MPPO: Task-Dependent Workflow Scheduling via Deep Reinforcement Learning

Implementation of the paper *"PF-MPPO: Task-dependent workflow scheduling method based on deep reinforcement learning in dynamic heterogeneous cloud environments"* integrated into the ASTRA-IDE platform.

---

## Overview

PF-MPPO extends standard PPO with:
- **DAG-based task modeling** — tasks have dependencies forming a directed acyclic graph
- **Realistic IDE workspace templates** — 7 project-type templates (Python, Node.js, C++, Go, Rust, Monorepo, Generic) with real resource profiles
- **Hybrid training** — mix of template DAGs (70%) and random DAGs (30%) for domain-specific learning + generalization
- **Multi-agent CTDE training** — 1 Global PPO + N parallel workers
- **Pre-training + Fine-tuning** — Rule Library of pre-trained models for different cluster sizes
- **Algorithm 3 (Model Selection)** — MMD-based selection of the best pre-trained model when cluster scales

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PF-MPPO Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         Workspace Templates (workspace_templates.py)        │ │
│  │  Python | Node.js | C++ | Go | Rust | Monorepo | Generic   │ │
│  │  image_pull → repo_clone → deps_install → [lsp, ext] → dev │ │
│  └────────────────────────────┬───────────────────────────────┘ │
│                               │                                 │
│  ┌──────────┐    ┌────────────▼──┐    ┌──────────────────┐     │
│  │ TaskDAG  │───▶│  Graph Algos  │───▶│ Admission Control│     │
│  │ (dag.py) │    │  (Alg 1 & 2)  │    │ (Eq 17)          │     │
│  └──────────┘    └───────────────┘    └────────┬─────────┘     │
│                                                │               │
│                                     Top-K (Task, VM) pairs     │
│                                                │               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Gymnasium Environment (env.py)               │  │
│  │  DAG Mode: random | template | hybrid                     │  │
│  │  State: K×10 vector (Eq 28)                               │  │
│  │  Action: Discrete [0, K-1] (Eq 29)                        │  │
│  │  Reward: -(α₁·log(T) + α₂·log(E) + α₃·log(LB))          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           CTDE Trainer (multi_agent.py)                    │  │
│  │  1 Global PPO ←── trajectories ←── 9 Workers              │  │
│  │  PPO Update (Eq 36) + Action Masking + Alg 4 (CDF)        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Rule Library (rule_library.py)                     │  │
│  │  Pre-trained models for 2/4/8/16 node clusters            │  │
│  │  Selection: Node count → MMD → Shadow execution            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install gymnasium numpy
```

Or install all ML deps:
```bash
pip install -r ml/requirements.txt
```

### Run Tests

```bash
# From project root (C:\Users\udit2\OneDrive\Desktop\BTP)
python -m unittest discover -s ml/scheduler/pfmppo/tests -v
```

All 126 tests should pass (97 core + 29 template tests).

### Train a Model

```bash
# Hybrid mode (recommended): 70% realistic templates + 30% random DAGs
python -m ml.scheduler.pfmppo.train \
    --mode pretrain \
    --dag-mode hybrid \
    --config ml/scheduler/pfmppo/configs/4_nodes.json \
    --iterations 2000 \
    --workers 9 \
    --batch-size 1000 \
    --out runs/pfmppo_production

# Template-only mode (IDE-specific specialization)
python -m ml.scheduler.pfmppo.train \
    --mode pretrain \
    --dag-mode template \
    --config ml/scheduler/pfmppo/configs/4_nodes.json \
    --iterations 2000 \
    --workers 9 \
    --out runs/pfmppo_template

# Random-only mode (original behavior, backward compatible)
python -m ml.scheduler.pfmppo.train \
    --mode pretrain \
    --dag-mode random \
    --config ml/scheduler/pfmppo/configs/4_nodes.json \
    --iterations 2000 \
    --workers 9 \
    --out runs/pfmppo_random

# Quick test (100 iterations)
python -m ml.scheduler.pfmppo.train \
    --mode pretrain \
    --dag-mode hybrid \
    --config ml/scheduler/pfmppo/configs/4_nodes.json \
    --iterations 100 \
    --workers 4 \
    --batch-size 200 \
    --out runs/pfmppo_test
```

### Fine-tune an Existing Model

```bash
python -m ml.scheduler.pfmppo.train \
    --mode finetune \
    --model-path runs/pfmppo_production/model.pt \
    --config ml/scheduler/pfmppo/configs/4_nodes.json \
    --iterations 500 \
    --lr 0.0001 \
    --out runs/pfmppo_finetuned
```

### Pre-train for All Cluster Configs (Rule Library)

```bash
python -m ml.scheduler.pfmppo.pretrain_all \
    --configs-dir ml/scheduler/pfmppo/configs/ \
    --out-dir rule_library/ \
    --iterations 2000 \
    --workers 9
```

This trains 4 models (2/4/8/16 nodes) and saves them with metadata for model selection.

### Run Benchmarks

```bash
python benchmarks/b1_scheduler/eval_pfmppo.py \
    --train-iterations 2000 \
    --eval-episodes 50 \
    --workers 9 \
    --num-tasks 20
```

---

## Workspace Templates

Training uses realistic IDE workspace startup DAGs instead of purely random task graphs. Each template models the actual sub-task chain for a specific project type.

### Available Templates

| Template | Language(s) | Sub-tasks | Character |
|----------|-------------|-----------|-----------|
| Python | `python` | image_pull → repo_clone → pip_install → [lsp, ext] → devserver | Heavy CPU+disk during pip |
| Node.js | `javascript`, `typescript`, `nodejs` | image_pull → repo_clone → npm_install → [lsp, ext] → devserver | Very high memory+disk |
| C++ | `cpp`, `c++`, `c` | image_pull → repo_clone → cmake_configure → cmake_build → [lsp, ext] | Very high CPU (120s build) |
| Go | `go`, `golang` | image_pull → repo_clone → go_mod_download → go_build → [lsp, ext] | High CPU (45s build) |
| Rust | `rust` | image_pull → repo_clone → cargo_fetch → cargo_build → [lsp, ext] | Heaviest (180s, 4 CPU, 3GB) |
| Monorepo | `monorepo` | image_pull → repo_clone → [pkg_a, pkg_b, pkg_c] → [lsp, ext] | 3 parallel installs |
| Generic | fallback | image_pull → repo_clone → ext_load | Minimal 3-task |

### Sub-task Resource Profiles

| Sub-task | CPU | Memory | Disk | Duration | Bandwidth Character |
|----------|-----|--------|------|----------|-------------------|
| image_pull | 0.25 | 256 MB | 2 GB | ~10s | High download |
| repo_clone | 0.5 | 512 MB | 4 GB | ~8s | High download |
| pip_install | 2.0 | 1 GB | 8 GB | ~30s | CPU+disk bound |
| npm_install | 2.5 | 2 GB | 12 GB | ~45s | Memory+disk bound |
| cmake_build | 4.0 | 2 GB | 4 GB | ~120s | CPU bound |
| cargo_build | 4.0 | 3 GB | 8 GB | ~180s | CPU+memory bound |
| lsp_start | 1.0 | 768 MB | 256 MB | ~5s | Light |
| devserver | 0.5 | 256 MB | 128 MB | ~3s | Light |

All values have noise injection (±15–60% variance) for training robustness.

### DAG Modes

| Mode | Flag | Behavior |
|------|------|----------|
| **Hybrid** (default) | `--dag-mode hybrid` | 70% template + 30% random per episode |
| Template | `--dag-mode template` | 100% realistic workspace templates |
| Random | `--dag-mode random` | Original synthetic DAGs (backward compatible) |

### Multi-Workspace Training

Each episode simulates 3–8 workspaces starting simultaneously (configurable via `--num-workspaces-min/max`). The model learns resource contention across concurrent startups — e.g., placing a Rust build and an npm install on the same compute node causes resource starvation.

---

## Integration with ASTRA-IDE Backend

### How It Works

The PF-MPPO scheduler integrates into the existing backend via a **feature flag** in environment/config:

```
scheduler_algorithm=pfmppo
pfmppo_model_path=runs/pfmppo_production/model.pt
pfmppo_k_pairs=10
```

When enabled, `scheduler_service.py` routes placement decisions through `pfmppo_inference.py`, which:
1. Converts the workspace into a single-task DAG
2. Converts live cluster nodes into VM objects
3. Computes admissible (task, VM) pairs
4. Encodes the 100-dim state vector
5. Runs inference through the trained network
6. Maps the action to a (cluster_id, node_name) placement

If inference fails for any reason, it **falls back** to the existing heuristic scorer automatically.

### Enable PF-MPPO in Development

1. **Train a model** (see Quick Start above)

2. **Set environment variables** in `backend/.env`:
   ```
   SCHEDULER_ALGORITHM=pfmppo
   PFMPPO_MODEL_PATH=../../runs/pfmppo_production/model.pt
   PFMPPO_K_PAIRS=10
   ```

3. **Start the backend** as usual:
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```

4. **Create a workspace** — the activity feed will show "PF-MPPO placed [workspace] on [node]" events instead of the heuristic scorer.

### Disable / Fallback

Set `SCHEDULER_ALGORITHM=heuristic` (or remove it — heuristic is the default) to revert to the original scoring function. No restart required if using `--reload`.

---

## Module Reference

| File | Purpose |
|------|---------|
| `dag.py` | `Task`, `VM`, `TaskDAG` dataclasses (Eqs 1-2) |
| `graph_algorithms.py` | Algorithm 1 (BFS features), Algorithm 2 (prioritization), Eq 17 (admission control) |
| `math_models.py` | Eqs 3-16: communication delay, computation time, energy, load balance, reward |
| `workspace_templates.py` | 7 IDE workspace startup templates, noise injection, composite DAG generation, aggregate computation |
| `env.py` | Gymnasium environment: Eq 28 (state), Eq 29 (action), Eq 30 (reward), dag_mode switching |
| `dag_generator.py` | Synthetic DAG generation (random mode) + `generate_vms()` utility |
| `network.py` | Custom PyTorch Actor-Critic network (Table 1) |
| `ppo_agent.py` | PPO agent + Algorithm 4 (weighted random sampling) + rollout buffer |
| `multi_agent.py` | CTDE trainer: 1 Global PPO + N workers (ThreadPoolExecutor) |
| `train.py` | CLI training entrypoint (pretrain / finetune / dag-mode selection) |
| `rule_library.py` | Algorithm 3: model storage + MMD selection |
| `pretrain_all.py` | Batch pre-training for all cluster configs |
| `configs/*.json` | Cluster configuration files (2/4/8/16 nodes) |

---

## Paper-to-Code Mapping

| Paper Section | Implementation |
|---------------|---------------|
| Eq 1 (Task model) | `dag.py::Task` |
| Eq 2 (VM model) | `dag.py::VM` |
| Eq 3 (Load balancing) | `math_models.py::load_balance_metric()` |
| Eq 5 (Communication delay) | `math_models.py::communication_delay()` |
| Eq 6 (Computation time) | `math_models.py::computation_time()` |
| Eq 10 (Response time) | `math_models.py::response_time()` |
| Eq 12 (Makespan) | `math_models.py::makespan()` |
| Eqs 13-16 (Energy model) | `math_models.py::dynamic_power()`, `task_energy()`, `total_energy()` |
| Eq 17 (Admission control) | `graph_algorithms.py::filter_admissible_pairs()` |
| Eq 18 (Prioritization) | `graph_algorithms.py::global_prioritization()` |
| Eq 28 (State space) | `env.py::encode_state()` |
| Eq 29 (Action space) | `env.py::PFMPPOEnv.action_space` |
| Eq 30 (Reward) | `math_models.py::pfmppo_reward()` |
| Eq 33 (Critic loss) | `ppo_agent.py::PPOAgent.update()` |
| Eq 36 (Actor loss, clipped) | `ppo_agent.py::PPOAgent.update()` |
| Table 1 (Network arch) | `network.py::PFMPPONetwork` |
| Algorithm 1 (Feature parsing) | `graph_algorithms.py::parse_task_features()` |
| Algorithm 2 (Prioritization) | `graph_algorithms.py::global_prioritization()` |
| Algorithm 3 (Model selection) | `rule_library.py::RuleLibrary.select_model()` |
| Algorithm 4 (Weighted random) | `ppo_agent.py::_weighted_random_sampling()` |
| Multi-agent CTDE | `multi_agent.py::CTDETrainer` |

---

## Training Parameters (Paper Table 2)

| Parameter | Value | CLI Flag |
|-----------|-------|----------|
| Learning Rate (pre-train) | 0.001 | `--lr 0.001` |
| Learning Rate (fine-tune) | 0.0001 | `--lr 0.0001` |
| Discount factor γ | 0.9 | `--gamma 0.9` |
| Clip ratio ε | 0.2 | `--epsilon 0.2` |
| Batch size | 1000 | `--batch-size 1000` |
| Workers | 9 | `--workers 9` |
| Iterations | 2000 | `--iterations 2000` |
| K (top pairs) | 10 | `--k-pairs 10` |
| Reward weights | α₁=0.34, α₂=0.33, α₃=0.33 (paper Table 2) | Set in env.py |
| DAG mode | hybrid | `--dag-mode hybrid` |
| Workspaces per episode | 3–8 | `--num-workspaces-min 3 --num-workspaces-max 8` |
| Template ratio (hybrid) | 0.7 | `--template-ratio 0.7` |

---

## Cluster Configs

Located in `ml/scheduler/pfmppo/configs/`:

| Config | Description |
|--------|-------------|
| `2_nodes.json` | 2 small VMs (2 CPU, 4GB each) — dev/test |
| `4_nodes.json` | 4 heterogeneous VMs — matches current ASTRA cluster |
| `8_nodes.json` | 8 mixed VMs (compute-heavy + memory-heavy) |
| `16_nodes.json` | 16 balanced VMs — large-scale |

To add a custom config, create a JSON file:
```json
{
  "description": "My custom cluster",
  "vms": [
    {
      "node_id": "vm_0",
      "cpu_cap": 8.0,
      "mem_cap": 16384.0,
      "disk_cap": 204800.0,
      "bandwidth_mbps": 2000.0,
      "proc_rate_mbps": 400.0,
      "power_static_w": 15.0,
      "power_max_w": 350.0
    }
  ]
}
```

---

## Changes to Existing Code

These modifications were made to integrate PF-MPPO:

1. **`backend/app/core/config.py`** — Added `scheduler_algorithm`, `pfmppo_model_path`, `pfmppo_rule_library_dir`, `pfmppo_k_pairs` settings

2. **`backend/app/services/cluster_state.py`** — Extended `Node` dataclass with `cpu_cap`, `mem_cap`, `disk_cap`, `bandwidth_mbps`, `proc_rate_mbps`, `power_static_w`, `power_max_w` (all with backward-compatible defaults)

3. **`backend/app/services/scheduler_service.py`** — Added PF-MPPO path at the top of `decide_placement()` that checks config and routes to `pfmppo_inference.py`

4. **`backend/app/services/pfmppo_inference.py`** — New file: singleton inference service that loads model and provides `decide_placement()`

---

## Troubleshooting

**"No module named 'torch'"** — Install PyTorch: `pip install torch --index-url https://download.pytorch.org/whl/cu124`

**"No module named 'gymnasium'"** — Install: `pip install gymnasium`

**"PF-MPPO model not found"** — Train a model first (see Quick Start) and set `PFMPPO_MODEL_PATH` correctly

**High invalid action rate during training** — Normal for early training. The agent learns action masking over time. Train for at least 1000+ iterations.

**Training is slow** — Reduce `--workers` if you have few CPU cores. The ThreadPoolExecutor parallelism is bounded by CPU count.

**CUDA out of memory** — The PF-MPPO network is tiny (~8K params). If you see OOM errors, they're likely from other processes. Training runs on CPU by default; set device manually in code for GPU training.
