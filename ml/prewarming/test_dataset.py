"""Tests for the synthetic session generator and sequence builder."""
import unittest

from ml.prewarming.dataset import (
    generate_synthetic_sessions,
    sessions_to_sequences,
    LANG_VOCAB,
)


class TestSyntheticSessions(unittest.TestCase):
    def test_generation_is_deterministic_with_seed(self):
        a = generate_synthetic_sessions(n_users=10, n_days=5, seed=123)
        b = generate_synthetic_sessions(n_users=10, n_days=5, seed=123)
        self.assertEqual(len(a), len(b))
        self.assertEqual(a[0].hour, b[0].hour)

    def test_sessions_sorted_by_user_day_hour(self):
        sessions = generate_synthetic_sessions(n_users=5, n_days=3, seed=1)
        for i in range(1, len(sessions)):
            prev, cur = sessions[i - 1], sessions[i]
            self.assertTrue(
                (prev.user_id, prev.day, prev.hour) <= (cur.user_id, cur.day, cur.hour)
            )

    def test_language_in_vocab(self):
        sessions = generate_synthetic_sessions(n_users=5, n_days=2, seed=2)
        for s in sessions:
            self.assertIn(s.language, LANG_VOCAB)


class TestSequenceBuilder(unittest.TestCase):
    def test_shapes(self):
        sessions = generate_synthetic_sessions(n_users=10, n_days=10, seed=5)
        X, y = sessions_to_sequences(sessions, seq_len=5)
        self.assertEqual(X.shape[1], 5)
        self.assertEqual(X.shape[2], 4)
        self.assertEqual(X.shape[0], y.shape[0])

    def test_labels_are_binary(self):
        sessions = generate_synthetic_sessions(n_users=5, n_days=5, seed=7)
        _, y = sessions_to_sequences(sessions, seq_len=3, horizon_minutes=30)
        unique = set(y.tolist())
        self.assertTrue(unique.issubset({0.0, 1.0}))

    def test_empty_when_too_few_sessions(self):
        # 1 user, 1 day → almost no sequences possible with seq_len=10
        sessions = generate_synthetic_sessions(n_users=1, n_days=1, seed=99)
        X, y = sessions_to_sequences(sessions, seq_len=10)
        self.assertEqual(X.shape[0], y.shape[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
