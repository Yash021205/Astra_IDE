"""
Synthetic session-log generator + sequence builder for LSTM prewarming training.

Generates per-user session logs over `n_days` with a configurable hourly activity
profile (peaks at typical work-hours), then converts them into supervised
training pairs:
  X = sequence of (hour_sin, hour_cos, day_of_week, language_id) for past K sessions
  y = 1 if a session starts within the next 15 minutes after the last X session, else 0

The synthetic profile mimics the patterns described in Section 6.2 of the spec
(work-hour peaks at 9-11am and 2-4pm, secondary peaks at 8-10pm).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

LANG_VOCAB = {"python": 0, "javascript": 1, "go": 2, "rust": 3, "java": 4, "cpp": 5, "bash": 6}


@dataclass
class Session:
    user_id:   int
    day:       int          # 0..n_days
    weekday:   int          # 0..6
    hour:      float        # 0..24 (with fractional minutes)
    language:  str

    @property
    def language_id(self) -> int:
        return LANG_VOCAB.get(self.language, 0)


# ── Synthetic generation ─────────────────────────────────────────────────────

# Per-hour probability of starting a session for an "active" user
_HOURLY_PROFILE = np.array([
    # 0  1  2  3  4  5  6  7   8   9   10  11
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.1, 0.3, 0.6, 0.7, 0.5,
    # 12 13  14  15  16  17  18   19   20   21   22   23
    0.3, 0.3, 0.6, 0.7, 0.5, 0.3, 0.2, 0.25, 0.4, 0.4, 0.2, 0.1,
])
_HOURLY_PROFILE = _HOURLY_PROFILE / _HOURLY_PROFILE.sum()


def generate_synthetic_sessions(
    n_users: int = 100,
    n_days:  int = 30,
    sessions_per_user_per_day: float = 2.5,
    languages: Tuple[str, ...] = ("python", "javascript", "go"),
    seed: int = 42,
) -> List[Session]:
    rng = np.random.default_rng(seed)
    sessions: List[Session] = []

    for user_id in range(n_users):
        # Each user prefers one language ~70% of the time
        primary_lang = rng.choice(languages)
        for day in range(n_days):
            weekday = day % 7
            # Lower activity on weekends
            lambda_ = sessions_per_user_per_day * (0.5 if weekday >= 5 else 1.0)
            n_sessions = rng.poisson(lambda_)
            for _ in range(n_sessions):
                hour_bin = rng.choice(24, p=_HOURLY_PROFILE)
                hour     = hour_bin + rng.uniform(0, 1)
                lang     = primary_lang if rng.random() < 0.7 else rng.choice(languages)
                sessions.append(Session(
                    user_id=user_id, day=day, weekday=weekday,
                    hour=float(hour), language=str(lang),
                ))

    # Sort by (user, day, hour) so windows are contiguous
    sessions.sort(key=lambda s: (s.user_id, s.day, s.hour))
    return sessions


# ── Sequence construction ────────────────────────────────────────────────────

def _encode(s: Session) -> np.ndarray:
    """Encode a single session into the 4-feature vector expected by the LSTM."""
    rad = 2 * np.pi * (s.hour / 24.0)
    return np.array([
        (np.sin(rad) + 1) / 2.0,
        (np.cos(rad) + 1) / 2.0,
        s.weekday / 6.0,
        s.language_id / max(1, len(LANG_VOCAB) - 1),
    ], dtype=np.float32)


def sessions_to_sequences(
    sessions: List[Session],
    seq_len:  int = 10,
    horizon_minutes: int = 15,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build supervised pairs (X, y) per user:
      X[i] = features of the i-th session's `seq_len` most recent past sessions
      y[i] = 1 if the next session starts within `horizon_minutes`, else 0

    Returns:
      X: shape (N, seq_len, 4) float32
      y: shape (N,)            float32
    """
    Xs: list[np.ndarray] = []
    ys: list[float]      = []

    # Group by user
    from itertools import groupby
    grouped = groupby(sessions, key=lambda s: s.user_id)

    horizon_h = horizon_minutes / 60.0
    for _, user_iter in grouped:
        user_sessions = list(user_iter)
        encoded = [_encode(s) for s in user_sessions]

        for i in range(seq_len, len(user_sessions) - 1):
            window      = np.stack(encoded[i - seq_len:i], axis=0)
            current     = user_sessions[i]
            next_session = user_sessions[i + 1]

            # Convert (day, hour) to absolute hours then check gap
            cur_abs  = current.day      * 24 + current.hour
            next_abs = next_session.day * 24 + next_session.hour
            label    = 1.0 if (next_abs - cur_abs) <= horizon_h else 0.0

            Xs.append(window)
            ys.append(label)

    if not Xs:
        return (
            np.zeros((0, seq_len, 4), dtype=np.float32),
            np.zeros((0,),            dtype=np.float32),
        )

    return np.stack(Xs, axis=0), np.array(ys, dtype=np.float32)
