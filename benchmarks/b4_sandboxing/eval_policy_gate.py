"""
B4 benchmark — policy gate (Paper 1, Yan arXiv:2512.12806 §4.2) evaluated on an
EXTERNAL labeled command corpus.

What it measures: does `transactional_executor.classify()` block malicious
commands (label UNSAFE) without blocking benign ones? This is the live guard
wired into `executor_service.execute()`, so this is an end-to-end test of the
exact code path a user hits.

Dataset-agnostic: point --csv at any file with a command column and a label
column. Column names are auto-detected (command/cmd/text/payload and
label/class/is_malicious/category), or pass them explicitly.

Reported per run:
  * precision, recall (= detection rate), F1, FPR, accuracy + confusion matrix
  * the SAME metrics for a naive keyword-blocklist BASELINE, so the structured
    policy's contribution is visible ("vs baseline" is what a panel wants)
  * per-category breakdown when the dataset carries a category/technique column

Honest scope note: the policy gate is a *destructive + host-escape* blocker
(rm -rf, /proc/self/exe, docker.sock, fork bombs, mount/unshare ...), not a
general-purpose injection classifier. Recon-style payloads (`; cat /etc/passwd`)
are intentionally out of this layer's scope and are covered by the behavioral
IDS (Paper 3) + network policy. The per-category report makes that coverage
boundary explicit instead of hiding it in an aggregate number.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Use the SAME classifier the live executor consults.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))
from app.services import transactional_executor as tx  # noqa: E402

_MALICIOUS_LABELS = {"1", "malicious", "attack", "injection", "true", "yes",
                     "mal", "anomaly", "bad"}
_BENIGN_LABELS = {"0", "benign", "normal", "false", "no", "clean", "legit",
                  "good"}

_CMD_COLS = ("command", "cmd", "text", "payload", "input", "shell", "query")
_LABEL_COLS = ("label", "class", "is_malicious", "malicious", "target", "y")
_CAT_COLS = ("category", "technique", "attack_type", "type", "tactic", "family")

# Strawman baseline: block if any "scary" token appears. Over-blocks on purpose
# (high recall, high FPR) — it is the foil the structured policy should beat.
_BASELINE_TOKENS = (
    "rm ", "sudo", "wget", "curl", "nc ", "ncat", "/etc/passwd", "/etc/shadow",
    "chmod", "chown", "mkfs", "dd ", ";", "|", "&&", "`", "$(", ">", "<",
)


def _is_malicious(raw: str) -> bool | None:
    v = raw.strip().lower()
    if v in _MALICIOUS_LABELS:
        return True
    if v in _BENIGN_LABELS:
        return False
    return None  # unknown label value — caller decides


def _pick(header: list[str], candidates: tuple[str, ...]) -> str | None:
    low = {h.lower(): h for h in header}
    for c in candidates:
        if c in low:
            return low[c]
    return None


def _load(csv_path: Path, cmd_col: str | None, label_col: str | None,
          cat_col: str | None) -> list[tuple[str, bool, str]]:
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        cmd_col = cmd_col or _pick(header, _CMD_COLS)
        label_col = label_col or _pick(header, _LABEL_COLS)
        cat_col = cat_col or _pick(header, _CAT_COLS)
        if not cmd_col or not label_col:
            raise SystemExit(
                f"Could not find command/label columns in {header}. "
                f"Pass --cmd-col and --label-col explicitly.")
        rows: list[tuple[str, bool, str]] = []
        for r in reader:
            cmd = (r.get(cmd_col) or "").strip()
            if not cmd:
                continue
            mal = _is_malicious(r.get(label_col, ""))
            if mal is None:
                # If the label column is actually a category, treat any non-benign
                # category as malicious (common in injection datasets).
                lab = (r.get(label_col, "") or "").strip().lower()
                mal = lab not in _BENIGN_LABELS and lab not in ("", "none")
            cat = (r.get(cat_col, "") if cat_col else "") or "—"
            rows.append((cmd, bool(mal), cat))
        return rows


def _policy_pred(cmd: str) -> bool:
    """The real gate: only UNSAFE is blocked (SAFE/UNCERTAIN run)."""
    return tx.classify(cmd) is tx.Policy.UNSAFE


def _baseline_pred(cmd: str) -> bool:
    low = cmd.lower()
    return any(tok in low for tok in _BASELINE_TOKENS)


def _metrics(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(1 for yt, yp in pairs if yt and yp)
    fp = sum(1 for yt, yp in pairs if not yt and yp)
    fn = sum(1 for yt, yp in pairs if yt and not yp)
    tn = sum(1 for yt, yp in pairs if not yt and not yp)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    acc = (tp + tn) / len(pairs) if pairs else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "fpr": fpr,
            "accuracy": acc, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _fmt(name: str, m: dict) -> str:
    return (f"  {name:18}  P={m['precision']:.3f}  R={m['recall']:.3f}  "
            f"F1={m['f1']:.3f}  FPR={m['fpr']:.3f}  Acc={m['accuracy']:.3f}  "
            f"(TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, type=Path, help="labeled command CSV")
    ap.add_argument("--cmd-col")
    ap.add_argument("--label-col")
    ap.add_argument("--cat-col")
    ap.add_argument("--out", type=Path, help="write JSON report here")
    args = ap.parse_args()

    rows = _load(args.csv, args.cmd_col, args.label_col, args.cat_col)
    n_mal = sum(1 for _, m, _ in rows if m)
    print(f"\nDataset: {args.csv}  ({len(rows)} commands, "
          f"{n_mal} malicious / {len(rows) - n_mal} benign)\n")

    policy_pairs = [(m, _policy_pred(c)) for c, m, _ in rows]
    base_pairs = [(m, _baseline_pred(c)) for c, m, _ in rows]
    policy_m = _metrics(policy_pairs)
    base_m = _metrics(base_pairs)

    print("Overall:")
    print(_fmt("policy gate", policy_m))
    print(_fmt("naive baseline", base_m))

    # Per-category recall on the malicious subset (coverage map).
    cats: dict[str, list[bool]] = defaultdict(list)
    for (c, m, cat) in rows:
        if m:
            cats[cat].append(_policy_pred(c))
    if len(cats) > 1 or (cats and next(iter(cats)) != "—"):
        print("\nPolicy-gate recall by malicious category (coverage map):")
        for cat in sorted(cats, key=lambda k: -len(cats[k])):
            hits = sum(cats[cat])
            print(f"  {cat[:34]:34}  {hits:4d}/{len(cats[cat]):<4d}  "
                  f"recall={hits / len(cats[cat]):.2f}")

    report = {
        "dataset": str(args.csv),
        "n_total": len(rows),
        "n_malicious": n_mal,
        "policy_gate": policy_m,
        "naive_baseline": base_m,
        "per_category_recall": {
            cat: {"hits": sum(v), "n": len(v), "recall": sum(v) / len(v)}
            for cat, v in cats.items()},
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
