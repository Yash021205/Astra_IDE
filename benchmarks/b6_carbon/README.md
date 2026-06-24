# B6 Carbon-Aware Scheduling — Benchmark Evaluation

Reproduces the carbon-reduction / completion-time tradeoff of **PCAPS** (Lechowicz
et al., *Carbon- and Precedence-Aware Scheduling for Data Processing Clusters* —
up to **32.9%** carbon reduction) by shifting deferrable work into low-carbon
windows, on a **real grid carbon trace**.

## Data — real, free, no API key
**UK Carbon Intensity API** (`carbonintensity.org.uk`) — half-hourly gCO2/kWh,
free and **no key required**. (ASTRA's live path uses the electricityMaps client in
`backend/app/services/carbon_service.py`, which needs a key — see below.)

## Reproduce
```bash
python eval_carbon.py --from 2024-06-01 --days 4 --jobs 300
```

## Results (real UK grid, 2024-06-01 +4d; 300 deferrable 2-hour jobs)
Trace: gCO2/kWh min=14, mean=83, max=174.

| slack (h) | carbon reduction % | mean delay (h) |
|---|---|---|
| 0  | 0.0  | 0.0  |
| 4  | 13.0 | 2.2  |
| 8  | 20.3 | 4.4  |
| **12** | **25.8** | 6.5 |
| 24 | 45.0 | 12.9 |
| 48 | 62.5 | 25.9 |

**The PCAPS knob, reproduced:** more slack → more carbon saved. A ~half-day slack
already yields **~26%** reduction (in PCAPS's "up to 32.9%" region), and a full
day reaches 45% — all on *real* grid data, by simply running deferrable jobs when
the grid is cleanest.

## How it works / scope
- `ml/carbon/scheduler.py`: `carbon_aware` starts each job at the lowest-average-
  carbon window within its slack; `carbon_agnostic` runs at arrival. Carbon is
  accounted as Σ power·intensity·hours over each job's run.
- ASTRA only shifts **deferrable** work (CI builds, test runs, nightly jobs);
  interactive workspaces always run immediately (slack 0).
- Combines with **B5** (route to the lowest-carbon *cluster* — the spatial axis;
  the Karmada OverridePolicy already tags clusters `carbon-profile: high/low`) and
  **B1** (the scheduler reward already includes a carbon term).

## Live carbon data (electricityMaps) — needs a key
For per-zone real-time intensity in production, set an **electricityMaps API key**
(free tier): sign up at `electricitymaps.com` → `ASTRA_EM_API_KEY` env var. The
free/sandbox key covers zone **DK-DK1** only; `carbon_service.py` falls back to a
per-zone historical table otherwise. The UK API above needs no key and is used for
this benchmark.
