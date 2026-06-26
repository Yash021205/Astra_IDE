"""
Reusable: download a PUBLIC HuggingFace dataset split to a local CSV using the
datasets-server API (no auth token needed for public datasets).

    python fetch_hf_dataset.py <owner/name> --split train --out data/x.csv

Works for any feature's benchmark — the downloaded CSV lands under a gitignored
data/ dir. We page through /rows (100 at a time) so there are no parquet/pandas
dependencies; only the Python stdlib is used.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://datasets-server.huggingface.co"


def _get(url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "astra-bench"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt + 1} after error: {e} (sleep {wait}s)")
            time.sleep(wait)
    return {}


def _first_config_split(dataset: str, split: str | None) -> tuple[str, str]:
    info = _get(f"{_BASE}/splits?dataset={urllib.parse.quote(dataset)}")
    splits = info.get("splits", [])
    if not splits:
        raise SystemExit(f"No splits found for {dataset}")
    if split:
        for s in splits:
            if s["split"] == split:
                return s["config"], s["split"]
    return splits[0]["config"], splits[0]["split"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dataset", help="HuggingFace dataset id, e.g. owner/name")
    ap.add_argument("--split", default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0, help="cap rows (0 = all)")
    args = ap.parse_args()

    config, split = _first_config_split(args.dataset, args.split)
    print(f"Dataset {args.dataset}  config={config}  split={split}")

    first = _get(f"{_BASE}/rows?dataset={urllib.parse.quote(args.dataset)}"
                 f"&config={urllib.parse.quote(config)}&split={split}"
                 f"&offset=0&length=1")
    total = first.get("num_rows_total") or 0
    cols = [f["name"] for f in first.get("features", [])]
    if args.limit:
        total = min(total, args.limit)
    print(f"  columns={cols}  rows={total}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        offset = 0
        while offset < total:
            length = min(100, total - offset)
            page = _get(f"{_BASE}/rows?dataset={urllib.parse.quote(args.dataset)}"
                        f"&config={urllib.parse.quote(config)}&split={split}"
                        f"&offset={offset}&length={length}")
            for item in page.get("rows", []):
                writer.writerow({c: item["row"].get(c, "") for c in cols})
                written += 1
            offset += length
            print(f"  fetched {written}/{total}", end="\r")
    print(f"\nWrote {written} rows -> {args.out}")


if __name__ == "__main__":
    main()
