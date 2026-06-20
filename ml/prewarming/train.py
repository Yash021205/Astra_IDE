"""
Train the LSTM prewarming predictor on synthetic session logs.

Usage:
    python -m ml.prewarming.train --users 100 --days 30 --epochs 20 --out runs/lstm

Outputs:
    runs/lstm/model.pt           Trained PyTorch weights
    runs/lstm/metrics.json       Precision / Recall / F1 on held-out users
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train LSTM prewarming predictor")
    parser.add_argument("--users",  type=int,   default=100)
    parser.add_argument("--days",   type=int,   default=30)
    parser.add_argument("--epochs", type=int,   default=20)
    parser.add_argument("--seq-len", type=int,  default=10)
    parser.add_argument("--horizon-minutes", type=int, default=15)
    parser.add_argument("--lr",     type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--out",    type=str,   default="runs/lstm")
    parser.add_argument("--seed",   type=int,   default=42)
    args = parser.parse_args()

    try:
        import numpy as np
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
        from sklearn.metrics import precision_score, recall_score, f1_score
    except ImportError:
        print("ERROR: missing ML deps. Install: pip install -r ml/requirements.txt", file=sys.stderr)
        return 1

    from ml.prewarming.dataset import generate_synthetic_sessions, sessions_to_sequences
    from ml.prewarming.model import build_model

    torch.manual_seed(args.seed)

    print(f"[1/4] Generating {args.users} users × {args.days} days of synthetic sessions...")
    all_sessions = generate_synthetic_sessions(
        n_users=args.users, n_days=args.days, seed=args.seed
    )
    print(f"      Generated {len(all_sessions)} total sessions")

    print(f"[2/4] Building supervised sequences (seq_len={args.seq_len})...")
    train_users = int(args.users * 0.8)
    train_sessions = [s for s in all_sessions if s.user_id < train_users]
    test_sessions  = [s for s in all_sessions if s.user_id >= train_users]

    X_train, y_train = sessions_to_sequences(train_sessions, seq_len=args.seq_len,
                                             horizon_minutes=args.horizon_minutes)
    X_test,  y_test  = sessions_to_sequences(test_sessions,  seq_len=args.seq_len,
                                             horizon_minutes=args.horizon_minutes)
    print(f"      Train: {X_train.shape}  pos_rate={y_train.mean():.3f}")
    print(f"      Test:  {X_test.shape}   pos_rate={y_test.mean():.3f}")

    if X_train.shape[0] == 0:
        print("Not enough sessions to build training sequences.", file=sys.stderr)
        return 1

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
        batch_size=args.batch_size, shuffle=True,
    )

    print("[3/4] Training LSTM...")
    model     = build_model(input_size=4)
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            preds = model(xb)
            loss  = criterion(preds, yb)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * xb.size(0)
        epoch_loss = running_loss / len(train_loader.dataset)
        print(f"      Epoch {epoch + 1:02d}/{args.epochs}  loss={epoch_loss:.4f}")

    print("[4/4] Evaluating on held-out users...")
    model.eval()
    with torch.no_grad():
        preds = model(torch.from_numpy(X_test)).numpy()
    bin_preds = (preds > 0.5).astype(int)
    bin_truth = y_test.astype(int)

    precision = precision_score(bin_truth, bin_preds, zero_division=0)
    recall    = recall_score(bin_truth,    bin_preds, zero_division=0)
    f1        = f1_score(bin_truth,        bin_preds, zero_division=0)
    print(f"      precision={precision:.3f}  recall={recall:.3f}  f1={f1:.3f}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_dir / "model.pt")
    (out_dir / "metrics.json").write_text(json.dumps({
        "precision": float(precision),
        "recall":    float(recall),
        "f1":        float(f1),
        "epochs":    args.epochs,
        "users":     args.users,
        "days":      args.days,
    }, indent=2))
    print(f"Saved → {out_dir / 'model.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
