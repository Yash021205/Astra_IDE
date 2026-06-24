"""
B3 benchmark — LSTM invocation forecasting + cold-start reduction on the real
Azure Functions 2019 trace (Shahrad et al.), reproducing the LSTM baseline of the
Transformer cold-start paper (Tables I/II) and the cold-start reduction (Table III).

The paper splits functions by problem (and so do we):
  * DENSE / frequent functions  → cold-start DELAY: forecast the invocation series,
    report sMAPE / N-RMSE / R². These are where sMAPE is meaningful (paper good
    band: sMAPE ~0.10-0.17, N-RMSE ~0.12-0.18). sMAPE is pathological on sparse
    near-zero series, exactly as the paper's hard datasets (1/3/8) show.
  * SPARSE / irregular functions → cold-start FREQUENCY: an adaptive keep-alive
    window (predicted inter-arrival) cuts cold starts vs the fixed 10-min window.
    Compared: fixed-10 vs Shahrad hybrid-histogram vs LSTM-adaptive vs oracle.
    Paper Table III: ~50-80% fewer cold starts.

    python eval_azure.py --csv data/_extracted/invocations_per_function_md.anon.d01.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.prewarming.forecaster import InvocationForecaster, persistence_forecast, smape  # noqa: E402
from ml.prewarming import policy as P                                                    # noqa: E402

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas required: pip install -r ml/requirements.txt")

_MINUTE_COLS = [str(i) for i in range(1, 1441)]


def _http_pool(csv: Path):
    df = pd.read_csv(csv)
    df = df[df["Trigger"] == "http"]
    series = df[_MINUTE_COLS].to_numpy(dtype=float)
    total = series.sum(axis=1)
    active = (series > 0).sum(axis=1)
    return series, total, active


def _pick(series, total, active, mask, n, seed):
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return []
    idx = idx[np.argsort(total[idx])]
    sel = idx[np.linspace(0, len(idx) - 1, min(n, len(idx))).round().astype(int)]
    return [(f"fn{j}", series[i], int(total[i]), int(active[i])) for j, i in enumerate(sel)]


# ── LSTM-driven adaptive keep-alive (predict the next inter-arrival gap) ────────

def _lstm_adaptive_keep_alive(counts, input_len=8, epochs=60, seed=0, margin=1):
    """Train an LSTM on the function's inter-arrival GAP series, walk-forward
    predict each next gap, and set the keep-alive window to it (paper §V: 'predict
    intervals between calls' → adapt the idle window). Falls back to the
    hybrid-histogram window where there is too little history to train."""
    counts = np.asarray(counts)
    active = np.where(counts > 0)[0]
    ka = P.hybrid_histogram_keep_alive(counts)              # fallback baseline
    if len(active) < input_len + 8:
        return ka
    gaps = np.diff(active).astype(float)                    # gap after each active step
    split = max(input_len + 4, int(len(gaps) * 0.5))
    f = InvocationForecaster(input_len=input_len, hidden=16, layers=2,
                             epochs=epochs, lr=1e-2, seed=seed).fit(gaps[:split])
    pred = f.walk_forward(gaps)                             # predicts gaps[input_len:]
    # gaps[k] is the gap AFTER active step k; assign predicted gap to that step.
    for k in range(input_len, len(gaps)):
        t = active[k]
        ka[t] = max(1.0, float(pred[k - input_len]) + margin)
    return ka


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--n-functions", type=int, default=6)
    ap.add_argument("--input-len", type=int, default=60)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    Path("results").mkdir(exist_ok=True)

    series, total, active = _http_pool(args.csv)
    density = active / 1440.0
    # "Popular/frequently used" functions (paper §V-A) — genuinely always-on, so
    # the series is non-degenerate and sMAPE is meaningful.
    dense = _pick(series, total, active, (density >= 0.9) & (total >= 500),
                  args.n_functions, args.seed)
    sparse = _pick(series, total, active,
                   (density <= 0.08) & (total >= 80) & (active >= 20),
                   args.n_functions, args.seed)
    print(f"HTTP functions: {int((total>0).sum())}  |  dense={len(dense)} sparse={len(sparse)}\n")

    # ── Forecasting on DENSE functions (paper Tables I/II) ──
    print("FORECASTING — dense functions (paper LSTM: sMAPE~0.10-0.17, N-RMSE~0.12-0.18)")
    print(f"{'fn':5} {'tot':>9} {'dens':>5} {'sMAPE':>7} {'N-RMSE':>7} {'R2':>7} {'naive sMAPE':>12}")
    sm, nr = [], []
    for name, s, tot, act in dense:
        split = int(len(s) * 0.8)
        f = InvocationForecaster(input_len=args.input_len, hidden=32, layers=2,
                                 epochs=args.epochs, lr=1e-2, seed=args.seed).fit(s[:split])
        m = f.evaluate(s[split - args.input_len:])
        y, yh = persistence_forecast(s[split - args.input_len:], args.input_len, 1)
        naive = smape(y[:, 0], yh[:, 0])
        sm.append(m["smape"]); nr.append(m["n_rmse"])
        print(f"{name:5} {tot:9d} {act/1440:5.2f} {m['smape']:7.3f} {m['n_rmse']:7.3f} "
              f"{m['r2']:7.3f} {naive:12.3f}")
    if sm:
        print(f"  median sMAPE={np.median(sm):.3f}  median N-RMSE={np.median(nr):.3f}")

    # ── Cold-start reduction on SPARSE functions (paper Table III) ──
    print("\nCOLD-START — sparse functions (paper: adaptive 50-80% fewer than fixed-10)")
    print(f"{'fn':5} {'tot':>6} {'fixed':>6} {'hybrid':>7} {'lstm':>6} {'oracle':>7} "
          f"{'lstm red%':>10} {'oracle red%':>12}")
    tf = thy = tl = to = 0
    for name, s, tot, act in sparse:
        fixed = P.simulate_cold_starts(s, P.DEFAULT_WINDOW)["cold_starts"]
        hyb = P.simulate_cold_starts(s, P.hybrid_histogram_keep_alive(s))["cold_starts"]
        lstm = P.simulate_cold_starts(s, _lstm_adaptive_keep_alive(s, seed=args.seed))["cold_starts"]
        orc = P.simulate_cold_starts(s, P.oracle_keep_alive(s))["cold_starts"]
        lr = 100 * (fixed - lstm) / fixed if fixed else 0
        orr = 100 * (fixed - orc) / fixed if fixed else 0
        tf += fixed; thy += hyb; tl += lstm; to += orc
        print(f"{name:5} {tot:6d} {fixed:6d} {hyb:7d} {lstm:6d} {orc:7d} {lr:10.1f} {orr:12.1f}")
    if tf:
        print(f"\nTotals vs fixed-10: hybrid cuts {100*(tf-thy)/tf:.1f}%, "
              f"LSTM-adaptive cuts {100*(tf-tl)/tf:.1f}%, oracle cuts {100*(tf-to)/tf:.1f}%")


if __name__ == "__main__":
    main()
