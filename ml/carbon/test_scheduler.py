"""
B6 tests: carbon-aware shifting reduces emissions vs the carbon-agnostic baseline,
and more slack saves more carbon (the PCAPS knob).
"""
import unittest

import numpy as np

from ml.carbon import scheduler as C


def _jobs(n=40, duration=4, seed=0, horizon=96):
    rng = np.random.default_rng(seed)
    return [C.Job(arrival=int(rng.integers(0, horizon - duration - 24)),
                  duration=duration, power_kw=0.2) for _ in range(n)]


class TestCarbonAccounting(unittest.TestCase):
    def test_window_carbon_and_total(self):
        trace = np.array([100.0, 200.0, 300.0, 400.0])
        j = [C.Job(arrival=0, duration=2, power_kw=1.0)]
        # 0.5h steps: 1kW * (100+200)/... actually total = 1*100*0.5 + 1*200*0.5 = 150
        self.assertAlmostEqual(C.total_carbon(j, [0], trace, step_hours=0.5), 150.0)

    def test_diurnal_shape(self):
        tr = C.diurnal_trace(days=1, steps_per_day=48, seed=0)
        # midday (step ~26 ≈ 13h) should be lower-carbon than evening peak (~36 ≈ 18h)
        self.assertLess(tr[26], tr[36])


class TestCarbonAware(unittest.TestCase):
    def setUp(self):
        self.trace = C.diurnal_trace(days=2, steps_per_day=48, seed=1)
        self.jobs = _jobs(horizon=len(self.trace))

    def test_aware_beats_agnostic(self):
        m = C.evaluate(self.jobs, self.trace, slack=24)
        self.assertLess(m["carbon_aware_g"], m["carbon_agnostic_g"])
        self.assertGreater(m["carbon_reduction_pct"], 5.0)

    def test_more_slack_saves_more(self):
        r6 = C.evaluate(self.jobs, self.trace, slack=6)["carbon_reduction_pct"]
        r24 = C.evaluate(self.jobs, self.trace, slack=24)["carbon_reduction_pct"]
        self.assertGreaterEqual(r24, r6)

    def test_zero_slack_is_agnostic(self):
        m = C.evaluate(self.jobs, self.trace, slack=0)
        self.assertAlmostEqual(m["carbon_reduction_pct"], 0.0, places=6)
        self.assertEqual(m["mean_delay_steps"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
