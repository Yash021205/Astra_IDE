"""
B5 — the AI-driven multi-cluster optimizer must beat the reactive baseline in the
direction of the paper's Table I (Punniyamoorthy et al., arXiv:2512.24914):
higher utilisation + load balance, lower oscillation + latency.
"""
import unittest

import numpy as np

from ml.federation import optimizer as O


class TestDemand(unittest.TestCase):
    def test_shape_and_imbalance(self):
        d = O.bursty_demand(n_clusters=2, steps=288, seed=0)
        self.assertEqual(d.shape, (2, 288))
        self.assertGreater(d[0].mean(), d[1].mean())   # cluster 0 is the hot one
        self.assertTrue((d >= 0).all())


class TestLatencyModel(unittest.TestCase):
    def test_monotonic_and_overload_penalty(self):
        self.assertLess(O._latency_ms(0.3), O._latency_ms(0.8))
        self.assertLess(O._latency_ms(0.9), O._latency_ms(1.4))   # overload costs more
        self.assertGreater(O._latency_ms(1.5), 300.0)

    def test_weighted_latency_follows_busy_cluster(self):
        # demand-weighted latency must reflect the overloaded (busy) cluster
        lat = O._weighted_latency([1.6, 0.1], [10.0, 0.5])
        self.assertGreater(lat, O._latency_ms(1.0))


class TestTableIDirection(unittest.TestCase):
    """AI-driven beats reactive across seeds, in the paper's direction."""

    @classmethod
    def setUpClass(cls):
        re, ai = [], []
        for s in range(12):
            d = O.bursty_demand(seed=s)
            re.append(O.simulate_reactive(d))
            ai.append(O.simulate_ai_driven(d))
        cls.re = {k: np.mean([r[k] for r in re]) for k in re[0]}
        cls.ai = {k: np.mean([a[k] for a in ai]) for k in ai[0]}

    def test_utilization_higher(self):
        self.assertGreater(self.ai["utilization_efficiency"],
                           self.re["utilization_efficiency"])

    def test_load_balance_higher(self):
        self.assertGreater(self.ai["load_balance"], self.re["load_balance"])

    def test_stability_better(self):
        # fewer scaling oscillations per hour
        self.assertLess(self.ai["stability_events_per_hr"],
                        self.re["stability_events_per_hr"])

    def test_latency_not_worse(self):
        # AI latency should be at least as good as reactive (per-request weighted)
        self.assertLessEqual(self.ai["latency_ms"], self.re["latency_ms"] + 1.0)

    def test_magnitudes_in_paper_ballpark(self):
        # utilisation ~0.6→0.7+, balance ~0.8→0.95, stability ~6→4 (paper 6.4→3.1)
        self.assertGreater(self.ai["utilization_efficiency"], 0.65)
        self.assertGreater(self.ai["load_balance"], 0.90)
        self.assertGreater(self.re["stability_events_per_hr"], 4.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
