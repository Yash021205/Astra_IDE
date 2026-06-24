"""
B3 improvement benchmark — GLOBAL LSTM (trained across many functions) vs the
per-function LSTM, on the real Azure Functions 2019 trace.

Goal: fix the two soft spots of the per-function model —
  * forecasting: lower sMAPE on held-out dense functions;
  * cold-start: the global gap-model should BEAT the Shahrad hybrid-histogram on
    sparse functions (the per-function LSTM lost to it: 49% vs 73.5%).

Held-out evaluation: the test functions are NOT in the training pool, so this
measures genuine generalisation. Device-aware (auto-CUDA on the college GPU).

    python eval_azure_global.py --csv data/_extracted/invocations_per_function_md.anon.d01.csv \
        --n-train 200 --epochs 25 [--gpu-note]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.prewarming.global_forecaster import GlobalForecaster   # noqa: E402
from ml.prewarming import policy as P                           # noqa: E402

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas required")

_MINUTE_COLS = [str(i) for i in range(1, 1441)]


def _http_pool(csv):
    df = pd.read_csv(csv)
    df = df[df["Trigger"] == "http"]
    s = df[_MINUTE_COLS].to_numpy(dtype=float)
    return s, s.sum(1), (s > 0).sum(1)


def _global_adaptive_ka(counts, gap_model, gap_input_len, margin=1):
    active = np.where(np.asarray(counts) > 0)[0]
    ka = P.hybrid_histogram_keep_alive(counts)
    if len(active) < gap_input_len + 2:
        return ka
    gaps = np.diff(active).astype(float)
    pred = gap_model.walk_forward(gaps)
    for k in range(gap_input_len, len(gaps)):
        ka[active[k]] = max(1.0, float(pred[k - gap_input_len]) + margin)
    return ka


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--n-train", type=int, default=200, help="functions in the training pool")
    ap.add_argument("--n-test", type=int, default=6)
    ap.add_argument("--input-len", type=int, default=60)
    ap.add_argument("--gap-input-len", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    Path("results").mkdir(exist_ok=True)

    series, total, active = _http_pool(args.csv)
    density = active / 1440.0
    dense = np.where((density >= 0.9) & (total >= 500))[0]
    sparse = np.where((density <= 0.08) & (total >= 80) & (active >= 20))[0]
    rng = np.random.default_rng(args.seed)
    rng.shuffle(dense); rng.shuffle(sparse)
    print(f"HTTP functions: {int((total>0).sum())}  dense={len(dense)} sparse={len(sparse)}")

    # ── GLOBAL forecasting (count series): train on pool, test on held-out dense ──
    test_dense = dense[:args.n_test]
    train_dense = dense[args.n_test:args.n_test + args.n_train]
    print(f"\n[1] GLOBAL count-LSTM: train {len(train_dense)} dense fns, "
          f"test {len(test_dense)} held-out")
    gcount = GlobalForecaster(input_len=args.input_len, hidden=32, layers=2,
                              epochs=args.epochs, lr=1e-3, batch_size=256,
                              seed=args.seed).fit([series[i] for i in train_dense], log=True)
    sm, nr = [], []
    for i in test_dense:
        m = gcount.evaluate(series[i])
        sm.append(m["smape"]); nr.append(m["n_rmse"])
    print(f"  GLOBAL forecasting on held-out dense: median sMAPE={np.median(sm):.3f}  "
          f"median N-RMSE={np.median(nr):.3f}")
    print("  (per-function LSTM was: median sMAPE 0.267, N-RMSE 0.174; paper LSTM N-RMSE 0.12-0.18)")

    # ── GLOBAL cold-start (gap series): train on pool, test on held-out sparse ──
    test_sparse = sparse[:args.n_test]
    train_sparse = sparse[args.n_test:args.n_test + args.n_train]
    gap_train = []
    for i in train_sparse:
        a = np.where(series[i] > 0)[0]
        if len(a) >= args.gap_input_len + 4:
            gap_train.append(np.diff(a).astype(float))
    print(f"\n[2] GLOBAL gap-LSTM: train {len(gap_train)} sparse fns' gap series, "
          f"test {len(test_sparse)} held-out")
    ggap = GlobalForecaster(input_len=args.gap_input_len, hidden=24, layers=2,
                            epochs=max(args.epochs, 40), lr=5e-3, batch_size=128,
                            seed=args.seed).fit(gap_train, log=True)

    print(f"\n  cold starts (held-out sparse): fixed-10 vs hybrid vs GLOBAL-LSTM vs oracle")
    print(f"  {'fn':4} {'fixed':>6} {'hybrid':>7} {'global':>7} {'oracle':>7} {'glob red%':>10}")
    tf = thy = tg = to = 0
    for j, i in enumerate(test_sparse):
        c = series[i]
        fixed = P.simulate_cold_starts(c, P.DEFAULT_WINDOW)["cold_starts"]
        hyb = P.simulate_cold_starts(c, P.hybrid_histogram_keep_alive(c))["cold_starts"]
        glob = P.simulate_cold_starts(c, _global_adaptive_ka(c, ggap, args.gap_input_len))["cold_starts"]
        orc = P.simulate_cold_starts(c, P.oracle_keep_alive(c))["cold_starts"]
        gr = 100 * (fixed - glob) / fixed if fixed else 0
        tf += fixed; thy += hyb; tg += glob; to += orc
        print(f"  fn{j:<2} {fixed:6d} {hyb:7d} {glob:7d} {orc:7d} {gr:10.1f}")
    if tf:
        print(f"\n  Totals vs fixed-10: hybrid cuts {100*(tf-thy)/tf:.1f}%, "
              f"GLOBAL-LSTM cuts {100*(tf-tg)/tf:.1f}%, oracle cuts {100*(tf-to)/tf:.1f}%")
        print(f"  (per-function LSTM-adaptive cut only 49.4% — beaten by hybrid; "
              f"goal: global beats hybrid 73.5%)")


if __name__ == "__main__":
    main()
