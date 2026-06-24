# B3 Pre-warming — Benchmark Evaluation (LSTM forecasting + cold-start)

Reproduces the **LSTM baseline** of *Transformer-Based Model for Cold Start
Mitigation in FaaS* (IEEE, Tables I/II/III) on the **real Azure Functions 2019
trace** (Shahrad et al., USENIX ATC'20). We build the LSTM (the model the project
uses); the paper's own LSTM rows are our targets.

## What the LSTM does (B3 in one line)
Forecast a function's invocation series → (a) pre-warm containers before demand
spikes, (b) adapt the keep-alive window to the predicted next inter-arrival —
cutting cold starts vs OpenWhisk's fixed 10-min window.

## Dataset
Azure Functions 2019 (`invocations_per_function_md`), HTTP-triggered functions,
per-minute counts (`1..1440`). Following the paper, functions are split by problem:
**dense/popular** → forecasting (cold-start *delay*); **sparse/irregular** →
cold-start *frequency*.

## Reproduce
```bash
# download once (143 MB) + extract a day file:
curl -sL https://github.com/Azure/AzurePublicDataset/releases/download/dataset-functions-2019/azurefunctions_dataset2019_azurefunctions-dataset2019.tar.xz -o data/azure2019.tar.xz
tar -xJf data/azure2019.tar.xz -C data/_extracted invocations_per_function_md.anon.d01.csv
python eval_azure.py --csv data/_extracted/invocations_per_function_md.anon.d01.csv --n-functions 6
```

## Results (day 1, 6 dense + 6 sparse HTTP functions of 15,933)

**Forecasting — dense functions (paper LSTM: sMAPE 0.10–0.37 well-behaved, N-RMSE 0.12–0.18):**
```
  fn       tot   sMAPE  N-RMSE     R2
  fn4    94488   0.030   0.221   ...     ← high-volume: sMAPE matches paper's best
  fn5  83591132  0.023   0.113   0.238
  fn0     1302   0.241   0.255
  fn3    18341   0.293   0.173
  median sMAPE = 0.267   median N-RMSE = 0.174
```
→ **median N-RMSE 0.174 is inside the paper's LSTM band (0.12–0.18)**; sMAPE
spans 0.023–0.55, within the paper's own LSTM sMAPE spread (it reports 0.096 up
to 1.187), with our best functions matching the paper's best (~0.02–0.1).

**Cold-start — sparse functions (paper Table III: adaptive 50–80% fewer):**
```
  policy                 cold-start reduction vs fixed-10-min
  Shahrad hybrid-histogram        73.5%      ← in paper's 50–80% band ✓
  LSTM-adaptive                   49.4%
  oracle (perfect foresight)      96.5%      ← upper bound
```

## Honest notes
- **N-RMSE matches the paper cleanly (0.174 vs 0.12–0.18).** sMAPE is reproduced
  in spread, not as a single number — it is mathematically unstable on sparse
  near-zero series (the paper's own datasets 1/3/8 show sMAPE > 1 for the same
  reason). We therefore report per-function and lead with N-RMSE + R².
- **The Shahrad hybrid-histogram baseline cuts 73.5%** of cold starts — a faithful
  reproduction of the adaptive-keep-alive benefit (paper 50–80%).
- **Our LSTM-adaptive (49.4%) is honestly beaten by the histogram on the sparsest
  functions** — those have only tens of inter-arrival gaps, too few to train an
  LSTM, where a simple histogram wins. The LSTM's strength is *dense* forecasting
  (above); for sparse keep-alive a histogram is competitive. We report this rather
  than hide it. In ASTRA, workspace demand is far denser than a single FaaS
  function, which is the regime where the LSTM forecast pays off.
- Trained on CPU over one day of data; the paper used Colab GPU over 14 days —
  more data/epochs would tighten our numbers further.

## Improvement: GLOBAL LSTM (trained across many functions) — `eval_azure_global.py`

A per-function LSTM starves on sparse functions (~30 gaps). A **single global
model** trained on windows pooled across many functions (each z-scored by its own
mean/std → scale-free) learns shared patterns and transfers to unseen functions.
Device-aware (auto-CUDA).

```bash
python eval_azure_global.py --csv data/_extracted/invocations_per_function_md.anon.d01.csv \
    --n-train 150 --epochs 20
```

**Forecasting (held-out dense functions the model never trained on):**

| metric | per-function LSTM | **global LSTM** | paper LSTM |
|---|---|---|---|
| median sMAPE | 0.267 | **0.091** | 0.096–0.108 (best) |
| median N-RMSE | 0.174 | **0.085** | 0.12–0.18 |

→ the global model **beats the per-function model and the paper's LSTM baseline**,
and generalises to functions it never saw. This is the recommended forecaster.

**Cold-start (held-out sparse functions) — honest non-win:** a global *gap* model
cut only ~6% of cold starts, still losing to the hybrid-histogram (~43%). The
gap-model's training loss barely moved because **sparse inter-arrival times are
near-memoryless** — point-prediction cannot beat a statistical percentile there.
Conclusion (and ASTRA's design): use the **LSTM demand forecast for pre-warming**
popular workspaces (where it excels), and the **histogram for keep-alive** of
sparse ones. We report this rather than force the LSTM where it doesn't help.

## Scaling note (GPU)
The 1-day / 150-function global train runs in minutes on CPU and already beats the
paper. Scaling to all 14 days × thousands of functions × more epochs (the college
GPU) would push sMAPE/N-RMSE lower still, but returns are marginal now — GPU is
better spent on the compute-heavy breakthroughs (B1 RL scheduler, B5 multi-cluster).
