"""
Generate frontend/public/research-metrics.json from the committed benchmark
artifacts (ml/*/artifacts/metrics.json), so the /research page shows the REAL
measured numbers instead of a separate hardcode. Re-run after any retrain:

    python scripts/gen_results.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(rel: str) -> dict:
    p = REPO / rel
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main() -> None:
    b1 = _load("ml/scheduler/pfmppo/artifacts/metrics.json")
    b3 = _load("ml/prewarming/artifacts/metrics.json")
    b4 = _load("ml/anomaly_ids/artifacts/metrics.json")
    b6 = _load("ml/carbon/artifacts/metrics.json")

    # B1 dataset may be a plain string (Kaggle eval) or a dict {paper, ours}.
    _b1_ds = b1.get("dataset", {})
    _b1_ds = _b1_ds.get("ours") if isinstance(_b1_ds, dict) else _b1_ds
    _b1_beats = bool((b1.get("eval") or {}).get("pfmppo_beats_best_baseline"))

    out = {
        "B1": {
            "measured": _b1_beats,
            "value": ("beats HEFT/Min-Min baselines" if _b1_beats else "retrain pending"),
            "detail": _b1_ds or "Google Cluster Trace 2011",
        },
        "B3": {
            "measured": bool(b3),
            "value": (f"{b3.get('cold_start_reduction_pct', {}).get('lstm_adaptive_vs_fixed10', '')}% fewer cold starts"
                      if b3 else ""),
            "detail": f"forecast N-RMSE {b3.get('median_n_rmse', '')}" if b3 else "",
        },
        "B4": {
            "measured": bool(b4.get("astra_ids")),
            "value": (f"F1 {b4['astra_ids']['f1']:.2f}" if b4.get("astra_ids") else ""),
            "detail": (f"beats STIDE {b4['baselines']['stide']['f1']:.2f}, "
                       f"frequency {b4['baselines']['frequency_iforest']['f1']:.2f}"
                       if b4.get("baselines") else ""),
        },
        "B6": {
            "measured": bool(b6),
            "value": (f"{b6.get('reduction_vs_slack', {}).get('24', b6.get('carbon_reduction_pct', ''))}% CO2 cut"
                      if b6 else ""),
            "detail": f"real {b6.get('dataset', '')}" if b6 else "",
        },
    }

    dest = REPO / "frontend" / "public" / "research-metrics.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"wrote {dest}")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
