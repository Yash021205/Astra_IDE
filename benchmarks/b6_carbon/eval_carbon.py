"""
B6 benchmark — carbon-aware scheduling on a REAL grid carbon trace.

Fetches half-hourly carbon intensity (gCO2/kWh) from the UK Carbon Intensity API
(carbonintensity.org.uk — free, NO API key) and runs a deferrable batch workload
under the carbon-agnostic baseline vs PCAPS-style carbon-aware shifting, reporting
the carbon-reduction / completion-time tradeoff across slack budgets.

Target (Lechowicz et al., PCAPS): up to ~32.9% carbon reduction with bounded delay.

    python eval_carbon.py [--from 2024-06-01 --days 3]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
from ml.carbon import scheduler as C   # noqa: E402


def fetch_uk_trace(start: str, days: int):
    """Half-hourly gCO2/kWh from the free UK Carbon Intensity API."""
    end = (np.datetime64(start) + np.timedelta64(days, "D")).astype(str)
    url = f"https://api.carbonintensity.org.uk/intensity/{start}T00:00Z/{end}T00:00Z"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())["data"]
    vals = [d["intensity"].get("actual") or d["intensity"].get("forecast") for d in data]
    return np.asarray([v for v in vals if v is not None], dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="2024-06-01")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=200)
    ap.add_argument("--duration", type=int, default=4)   # 2h jobs (4 × 30min)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    try:
        trace = fetch_uk_trace(args.start, args.days)
        src = f"UK Carbon Intensity API {args.start} (+{args.days}d), {len(trace)} half-hourly points"
    except Exception as e:                       # offline → synthetic fallback
        trace = C.diurnal_trace(days=args.days, steps_per_day=48, seed=0)
        src = f"(API unreachable: {e}) synthetic diurnal trace, {len(trace)} points"
    print(f"\nCarbon trace: {src}")
    print(f"  gCO2/kWh  min={trace.min():.0f}  mean={trace.mean():.0f}  max={trace.max():.0f}\n")

    rng = np.random.default_rng(args.seed)
    horizon = len(trace)
    jobs = [C.Job(arrival=int(rng.integers(0, horizon - args.duration - 48)),
                  duration=args.duration, power_kw=0.2) for _ in range(args.jobs)]

    print("Carbon-aware shifting vs carbon-agnostic baseline (PCAPS target up to 32.9%):")
    print(f"  {'slack (h)':>9} {'reduction %':>12} {'mean delay (h)':>15}")
    for slack_steps in (0, 4, 8, 16, 24, 48, 96):
        m = C.evaluate(jobs, trace, slack=slack_steps)
        print(f"  {slack_steps/2:9.0f} {m['carbon_reduction_pct']:12.1f} "
              f"{m['mean_delay_steps']/2:15.1f}")
    print("\nMore slack -> more carbon saved (the PCAPS knob); ASTRA shifts only "
          "deferrable\nbatch work (CI/test/nightly), never interactive workspaces.")


if __name__ == "__main__":
    main()
