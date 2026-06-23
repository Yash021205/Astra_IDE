"""B1 — baseline scheduler policies produce valid actions and behave as intended."""
import unittest

import numpy as np

try:
    from ml.scheduler.env import SchedulerEnv
    from ml.scheduler import baselines as B
    _OK = True
except ImportError:
    _OK = False


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestBaselines(unittest.TestCase):
    def setUp(self):
        self.env = SchedulerEnv(num_nodes=4, seed=0)
        self.env.reset(seed=0)

    def test_actions_are_valid(self):
        for name, fn in B.all_baselines().items():
            a = fn(self.env)
            self.assertEqual(len(a), 4, name)
            self.assertTrue(0 <= a[0] < self.env.num_nodes, name)
            self.assertIn(a[1], (0, 1, 2), name)          # sandbox tier

    def test_least_loaded_picks_min_cpu(self):
        self.env.state.cpu_util[:] = [0.9, 0.1, 0.5, 0.8]
        self.assertEqual(B.least_loaded(self.env)[0], 1)  # node 1 is least loaded

    def test_tier_tracks_risk(self):
        self.assertEqual(B._tier_from_risk(0.1), 0)       # runc
        self.assertEqual(B._tier_from_risk(0.5), 1)       # gvisor
        self.assertEqual(B._tier_from_risk(0.9), 2)       # firecracker

    def test_round_robin_cycles(self):
        rr = B.round_robin()
        picks = [rr(self.env)[0] for _ in range(8)]
        self.assertEqual(picks, [0, 1, 2, 3, 0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
