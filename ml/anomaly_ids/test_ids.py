"""
Tests for the graph-based container IDS (Iacovazzi & Raza, IEEE CSR 2022).

The paper's F1=0.9 numbers require the CloudSuite syscall corpus (needs live
host-level capture — our B2 dependency). Here we (a) verify the embedding math
exactly matches the paper (length-4 anonymous walks = Bell number B4 = 15) and
(b) validate the full RF + Isolation-Forest pipeline separates structured
"normal" workloads from an unstructured "attack" on synthetic syscall traces.
"""
import random
import unittest

from ml.anomaly_ids.embedding import (
    generate_anonymous_walks, anonymous_walk_embedding, build_syscall_graph,
    rich_embedding, rich_embed_dim, graph_stats, EMBED_DIM,
)
from ml.anomaly_ids.detector import ContainerIDS, Decision


class TestAnonymousWalkMath(unittest.TestCase):
    def test_length4_is_bell_number_15(self):
        # Bell numbers: B1=1, B2=2, B3=5, B4=15, B5=52
        self.assertEqual(len(generate_anonymous_walks(2)), 2)
        self.assertEqual(len(generate_anonymous_walks(3)), 5)
        self.assertEqual(len(generate_anonymous_walks(4)), 15)
        self.assertEqual(len(generate_anonymous_walks(5)), 52)
        self.assertEqual(EMBED_DIM, 15)

    def test_walks_are_valid_rgs(self):
        for w in generate_anonymous_walks(4):
            self.assertEqual(w[0], 1)                      # always starts at 1
            for i in range(1, len(w)):
                self.assertLessEqual(w[i], max(w[:i]) + 1)  # restricted-growth rule

    def test_embedding_dim_and_normalized(self):
        seq = [1, 2, 3, 1, 2, 3, 1, 2, 3, 4, 2, 1]
        emb = anonymous_walk_embedding(seq, seed=1)
        self.assertEqual(len(emb), 15)
        self.assertAlmostEqual(sum(emb), 1.0, places=6)

    def test_empty_sequence_is_zero_vector(self):
        self.assertEqual(anonymous_walk_embedding([], seed=1), [0.0] * 15)

    def test_bigram_graph_counts(self):
        g = build_syscall_graph([1, 2, 1, 2, 3])
        self.assertEqual(g[1][2], 2)   # bigram (1->2) occurs twice
        self.assertEqual(g[2][1], 1)
        self.assertEqual(g[2][3], 1)

    def test_embedding_length_is_generalized(self):
        # Regression: passing length != 4 must give a Bell(length)-dim distribution,
        # not silently fall back to the length-4 vocabulary (all-zeros bug).
        seq = [1, 2, 3, 2, 1, 4, 5, 4, 2, 3, 1, 2, 3, 4, 5, 1, 2, 1, 3, 2]
        self.assertEqual(len(anonymous_walk_embedding(seq, length=3, n_walks=300, seed=0)), 5)
        self.assertEqual(len(anonymous_walk_embedding(seq, length=5, n_walks=300, seed=0)), 52)
        v5 = anonymous_walk_embedding(seq, length=5, n_walks=300, seed=0)
        self.assertAlmostEqual(sum(v5), 1.0, places=6)   # a real distribution, not zeros

    def test_graph_stats_fixed_size_bounded(self):
        s = graph_stats([1, 2, 3, 2, 1, 4, 5, 4, 2, 3, 1, 2])
        self.assertEqual(len(s), 8)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in s))

    def test_rich_embedding_dim_and_deterministic(self):
        seq = [1, 2, 3, 2, 1, 4, 5, 4, 2, 3, 1, 2, 3, 4, 5, 1, 2, 1, 3, 2]
        a = rich_embedding(seq, n_walks=200, seed=3)
        b = rich_embedding(seq, n_walks=200, seed=3)
        self.assertEqual(len(a), rich_embed_dim())       # 72 walks + 8 stats + 32 freq = 112
        self.assertEqual(len(a), 112)
        self.assertEqual(a, b)                            # deterministic given seed


# ── Synthetic syscall workloads for the pipeline test ─────────────────────────

def _structured_trace(node_cycle, length, noise, rng):
    """A 'normal' workload: mostly cycles through node_cycle with a little noise."""
    seq, i = [], 0
    for _ in range(length):
        if rng.random() < noise:
            seq.append(rng.randint(1, 30))
        else:
            seq.append(node_cycle[i % len(node_cycle)])
            i += 1
    return seq

def _attack_trace(length, rng):
    """An 'attack': unstructured near-uniform syscalls over a wide range."""
    return [rng.randint(1, 30) for _ in range(length)]


def _embed_many(traces, seed0=0):
    return [anonymous_walk_embedding(t, seed=seed0 + i) for i, t in enumerate(traces)]


class TestIDSPipeline(unittest.TestCase):
    """RF + ensemble-of-IF separates structured normals from unstructured attack."""

    @classmethod
    def setUpClass(cls):
        rng = random.Random(7)
        # Three normal workload classes, each a distinct cyclic syscall pattern
        cycles = {
            "data_analytics": [1, 2, 3],
            "media_streaming": [4, 5, 6, 7],
            "web_search":      [8, 9],
        }
        by_class = {}
        # deterministic per-class seed (NOT Python's salted hash(), which varies per
        # process and made this test flaky)
        for ci, (name, cyc) in enumerate(cycles.items()):
            traces = [_structured_trace(cyc, 60, noise=0.05, rng=rng) for _ in range(40)]
            by_class[name] = _embed_many(traces, seed0=100 + ci * 100)
        cls.ids = ContainerIDS(seed=42).fit(by_class)

        # Held-out NORMAL samples (same generators)
        cls.normal_eval = []
        for name, cyc in cycles.items():
            traces = [_structured_trace(cyc, 60, noise=0.05, rng=rng) for _ in range(15)]
            cls.normal_eval += _embed_many(traces, seed0=500)

        # ATTACK samples (unstructured)
        attacks = [_attack_trace(60, rng) for _ in range(20)]
        cls.attack_eval = _embed_many(attacks, seed0=900)

    def test_attack_detection_rate_in_paper_range(self):
        flagged = sum(1 for v in self.attack_eval
                      if self.ids.predict(v).decision is Decision.ANOMALY)
        tpr = flagged / len(self.attack_eval)
        # Paper §VI-D reports TPR spanning 0.49 (Brute Force) to 1.0 (Meterpreter/
        # cryptomining) across attack types, and notes "TPR below 0.7 against
        # Backdoor/SQLInjection, below 0.5 against Brute Force." We assert the
        # detector clears the paper's documented FLOOR (~0.5), not perfection.
        self.assertGreaterEqual(tpr, 0.5, f"TPR below paper floor: {tpr:.2f}")

    def test_false_positive_rate_low(self):
        fp = sum(1 for v in self.normal_eval
                 if self.ids.predict(v).decision is Decision.ANOMALY)
        fpr = fp / len(self.normal_eval)
        # Paper FPRs 0.024-0.071; synthetic should keep normals mostly NORMAL.
        self.assertLessEqual(fpr, 0.3, f"FPR too high: {fpr:.2f}")

    def test_rf_recovers_workload_class(self):
        # Stage-2 RF should label a clean data_analytics-style trace correctly
        rng = random.Random(123)
        t = _structured_trace([1, 2, 3], 60, noise=0.02, rng=rng)
        res = self.ids.predict(anonymous_walk_embedding(t, seed=11))
        self.assertEqual(res.rf_class, "data_analytics")


class TestIDSPersistence(unittest.TestCase):
    """A fitted detector saved to disk and reloaded predicts identically — this is
    the artifact path (train offline on real data → commit ids.joblib → serve)."""

    def test_save_load_round_trip(self):
        import tempfile, os
        rng = random.Random(7)
        cyc = {"a": [1, 2, 3], "b": [4, 5, 6, 7]}
        by_class = {
            name: _embed_many([_structured_trace(c, 60, 0.05, rng) for _ in range(20)],
                              seed0=100 + i * 100)
            for i, (name, c) in enumerate(cyc.items())
        }
        ids = ContainerIDS(seed=42).fit(by_class)
        sample = anonymous_walk_embedding(_structured_trace([1, 2, 3], 60, 0.02, rng), seed=11)
        before = ids.predict(sample)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ids.joblib")
            ids.save(path)
            self.assertTrue(os.path.exists(path))
            loaded = ContainerIDS.load(path)

        after = loaded.predict(sample)
        self.assertEqual(loaded.classes_, ids.classes_)
        self.assertEqual(after.decision, before.decision)
        self.assertEqual(after.rf_class, before.rf_class)

    def test_save_before_fit_raises(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                ContainerIDS(seed=1).save(os.path.join(d, "x.joblib"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
