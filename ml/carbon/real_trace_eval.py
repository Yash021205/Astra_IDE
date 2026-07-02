"""
B6 — fetch a REAL grid carbon-intensity trace and evaluate PCAPS-style temporal
shifting on it (replacing the synthetic diurnal_trace in tests).

Source: UK Carbon Intensity API (carbonintensity.org.uk) — free, no auth,
half-hourly ACTUAL gCO2/kWh for the GB grid. Real diurnal + weekly structure
(overnight/solar lows, evening peaks), which is exactly what carbon-aware
shifting exploits.

Saves ml/carbon/artifacts/real_trace.npz (the trace) + metrics.json (real
carbon reduction % vs a carbon-agnostic baseline, and the delay it costs).

    python -m ml.carbon.real_trace_eval --days 14 --slack 12
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.carbon.scheduler import Job, evaluate  # noqa: E402

_API = "https://api.carbonintensity.org.uk/intensity"


def fetch_uk_trace(days: int) -> np.ndarray:
    """Half-hourly ACTUAL gCO2/kWh for the last `days` days (48 points/day)."""
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    out: list[float] = []
    cur = start
    # API allows a max 14-day span per call; page in 7-day chunks to be safe.
    while cur < end:
        chunk_end = min(cur + timedelta(days=7), end)
        url = f"{_API}/{cur.strftime('%Y-%m-%dT%H:%MZ')}/{chunk_end.strftime('%Y-%m-%dT%H:%MZ')}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())["data"]
        for row in data:
            it = row["intensity"]
            val = it.get("actual")
            if val is None:
                val = it.get("forecast")
            if val is not None:
                out.append(float(val))
        cur = chunk_end
    return np.asarray(out, dtype=float)


def make_jobs(n: int, n_steps: int, rng: np.random.Generator) -> list[Job]:
    """Deferrable batch jobs (CI builds / test runs) arriving across the trace."""
    jobs = []
    for _ in range(n):
        arrival = int(rng.integers(0, max(1, n_steps - 8)))
        duration = int(rng.integers(1, 5))          # 0.5-2h of compute
        jobs.append(Job(arrival=arrival, duration=duration, power_kw=0.2))
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--slack", type=int, default=12, help="deferral budget in 30-min steps (12=6h)")
    ap.add_argument("--n-jobs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-trace", type=Path, default=Path("ml/carbon/artifacts/real_trace.npz"))
    ap.add_argument("--metrics-out", type=Path, default=Path("ml/carbon/artifacts/metrics.json"))
    args = ap.parse_args()

    print(f"fetching {args.days} days of real UK grid carbon intensity (half-hourly)...")
    trace = fetch_uk_trace(args.days)
    print(f"  got {len(trace)} real half-hourly readings; "
          f"gCO2/kWh min={trace.min():.0f} max={trace.max():.0f} mean={trace.mean():.0f}")

    rng = np.random.default_rng(args.seed)
    jobs = make_jobs(args.n_jobs, len(trace), rng)
    # step_hours=0.5 (half-hourly). Sweep a few slack budgets for the curve.
    res = evaluate(jobs, trace, slack=args.slack, step_hours=0.5)
    curve = {str(s): round(evaluate(jobs, trace, slack=s, step_hours=0.5)["carbon_reduction_pct"], 2)
             for s in (2, 6, 12, 24, 48)}

    args.out_trace.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out_trace, trace=trace)
    print(f"saved real carbon trace -> {args.out_trace}")

    metrics = {
        "dataset": "UK Carbon Intensity API (GB grid, actual gCO2/kWh, half-hourly)",
        "trace_points": len(trace),
        "days": args.days,
        "gco2_min": round(float(trace.min()), 1),
        "gco2_max": round(float(trace.max()), 1),
        "gco2_mean": round(float(trace.mean()), 1),
        "slack_steps": args.slack,
        "carbon_agnostic_g": round(res["carbon_agnostic_g"], 2),
        "carbon_aware_g": round(res["carbon_aware_g"], 2),
        "carbon_reduction_pct": round(res["carbon_reduction_pct"], 2),
        "mean_delay_steps": round(res["mean_delay_steps"], 2),
        "reduction_vs_slack": curve,
        "paper_reference": {"source": "PCAPS (Lechowicz et al.)", "up_to_pct": 32.9},
    }
    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(metrics, indent=2))
    print(f"wrote metrics -> {args.metrics_out}")
    print(f"\nREAL carbon reduction at slack={args.slack} (6h): "
          f"{metrics['carbon_reduction_pct']}%  (delay {metrics['mean_delay_steps']} steps)")
    print(f"reduction vs slack budget: {curve}")


if __name__ == "__main__":
    main()
