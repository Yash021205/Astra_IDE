"""
Tests for the B3 pre-warm policy + cold-start simulator.

Reproduces the paper's qualitative Table III result: an adaptive keep-alive
window (driven by predicted inter-arrival) yields far fewer cold starts than the
fixed 10-min window, with the Shahrad hybrid-histogram baseline in between.
"""
import unittest

import numpy as np

from ml.prewarming import policy as P


def _sparse_periodic(n=600, period=20):
    """One invocation every `period` steps (gap 20 > fixed window 10)."""
    counts = np.zeros(n)
    counts[::period] = 1
    return counts


class TestSimulator(unittest.TestCase):
    def test_first_invocation_is_always_cold(self):
        r = P.simulate_cold_starts([1, 0, 0], keep_alive=10)
        self.assertEqual(r["cold_starts"], 1)
        self.assertEqual(r["active"], 1)

    def test_warm_hit_within_window(self):
        # invocations at t=0 and t=3; window 5 keeps it warm -> 1 cold (the first)
        counts = [1, 0, 0, 1, 0]
        self.assertEqual(P.simulate_cold_starts(counts, 5)["cold_starts"], 1)
        # window 2 expires before t=3 -> both cold
        self.assertEqual(P.simulate_cold_starts(counts, 2)["cold_starts"], 2)

    def test_prewarm_prevents_cold_start(self):
        counts = [1, 0, 0, 1]
        prewarm = [True, False, False, True]
        self.assertEqual(P.simulate_cold_starts(counts, 1, prewarm)["cold_starts"], 0)


class TestPaperTableIII(unittest.TestCase):
    """Adaptive < hybrid-histogram < fixed, in cold starts (paper Table III shape)."""

    def setUp(self):
        self.counts = _sparse_periodic()

    def test_fixed_window_is_worst(self):
        # gap 20 > fixed 10 -> every invocation after the first is cold
        fixed = P.simulate_cold_starts(self.counts, P.DEFAULT_WINDOW)["cold_starts"]
        oracle_ka = P.oracle_keep_alive(self.counts)
        adaptive = P.simulate_cold_starts(self.counts, oracle_ka)["cold_starts"]
        self.assertLess(adaptive, fixed)

    def test_adaptive_reduction_in_paper_band(self):
        # Oracle adaptive should cut cold starts well into the paper's 50-80%+ band.
        oracle_ka = P.oracle_keep_alive(self.counts)
        red = P.reduction_vs_fixed(self.counts, oracle_ka)
        self.assertGreater(red, 80.0, f"reduction {red:.1f}% below expectation")

    def test_hybrid_histogram_between_fixed_and_adaptive(self):
        fixed = P.simulate_cold_starts(self.counts, P.DEFAULT_WINDOW)["cold_starts"]
        hist_ka = P.hybrid_histogram_keep_alive(self.counts, percentile=95)
        hist = P.simulate_cold_starts(self.counts, hist_ka)["cold_starts"]
        oracle_ka = P.oracle_keep_alive(self.counts)
        adaptive = P.simulate_cold_starts(self.counts, oracle_ka)["cold_starts"]
        self.assertLessEqual(adaptive, hist)
        self.assertLessEqual(hist, fixed)


class TestPrewarmCount(unittest.TestCase):
    def test_ceil_of_demand(self):
        self.assertEqual(P.prewarm_count(0.0), 0)
        self.assertEqual(P.prewarm_count(2.1), 3)
        self.assertEqual(P.prewarm_count(4, capacity=2), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
