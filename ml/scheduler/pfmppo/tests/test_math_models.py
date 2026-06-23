"""Tests for mathematical models (Equations 3-16, 30)."""
import math
import unittest

from ml.scheduler.pfmppo.math_models import (
    communication_delay,
    computation_time,
    response_time,
    makespan,
    dynamic_power,
    task_energy,
    total_energy,
    load_balance_metric,
    pfmppo_reward,
)


class TestCommunicationDelay(unittest.TestCase):
    def test_same_vm_is_zero(self):
        self.assertEqual(communication_delay(100.0, 1000.0, 500.0, same_vm=True), 0.0)

    def test_cross_vm(self):
        # data=100MB, bw_src=1000, bw_dst=500 -> 100/500 = 0.2
        self.assertAlmostEqual(communication_delay(100.0, 1000.0, 500.0), 0.2)

    def test_uses_min_bandwidth(self):
        # data=200, min(2000, 1000) = 1000 -> 200/1000 = 0.2
        self.assertAlmostEqual(communication_delay(200.0, 2000.0, 1000.0), 0.2)

    def test_zero_bandwidth_returns_inf(self):
        self.assertEqual(communication_delay(100.0, 0.0, 500.0), float('inf'))


class TestComputationTime(unittest.TestCase):
    def test_normal(self):
        # data=100MB, rate=200 -> 100/200 = 0.5
        self.assertAlmostEqual(computation_time(100.0, 200.0), 0.5)

    def test_zero_rate_returns_inf(self):
        self.assertEqual(computation_time(100.0, 0.0), float('inf'))


class TestResponseTime(unittest.TestCase):
    def test_sum(self):
        self.assertAlmostEqual(response_time(1.0, 2.0, 3.0), 6.0)


class TestMakespan(unittest.TestCase):
    def test_max(self):
        self.assertAlmostEqual(makespan([1.0, 5.0, 3.0, 2.0]), 5.0)

    def test_empty(self):
        self.assertEqual(makespan([]), 0.0)


class TestDynamicPower(unittest.TestCase):
    def test_idle(self):
        # utilization=0 -> P = P_static
        self.assertAlmostEqual(dynamic_power(11.0, 200.0, 0.0), 11.0)

    def test_full_load(self):
        # utilization=1, freq=1 -> P = P_static + (P_max - P_static) * 1 * 1 = P_max
        self.assertAlmostEqual(dynamic_power(11.0, 200.0, 1.0), 200.0)

    def test_half_load(self):
        # P = 11 + (200-11) * 1 * 0.5 = 11 + 94.5 = 105.5
        self.assertAlmostEqual(dynamic_power(11.0, 200.0, 0.5), 105.5)

    def test_frequency_factor(self):
        # freq=0.5 -> f^3 = 0.125
        # P = 11 + (200-11) * 0.125 * 1.0 = 11 + 23.625 = 34.625
        self.assertAlmostEqual(dynamic_power(11.0, 200.0, 1.0, freq=0.5), 34.625)


class TestTaskEnergy(unittest.TestCase):
    def test_normal(self):
        # power=100W, duration=10s -> 1000 Wh (Joules technically)
        self.assertAlmostEqual(task_energy(100.0, 0.0, 10.0), 1000.0)

    def test_negative_duration_is_zero(self):
        self.assertAlmostEqual(task_energy(100.0, 10.0, 5.0), 0.0)


class TestTotalEnergy(unittest.TestCase):
    def test_sum(self):
        self.assertAlmostEqual(total_energy([100.0, 200.0, 300.0]), 600.0)

    def test_empty(self):
        self.assertEqual(total_energy([]), 0.0)


class TestLoadBalanceMetric(unittest.TestCase):
    def test_perfect_balance(self):
        self.assertAlmostEqual(load_balance_metric([0.5, 0.5, 0.5, 0.5]), 0.0)

    def test_single_vm(self):
        self.assertEqual(load_balance_metric([0.7]), 0.0)

    def test_empty(self):
        self.assertEqual(load_balance_metric([]), 0.0)

    def test_imbalanced(self):
        lb = load_balance_metric([1.0, 0.0, 0.0, 0.0])
        self.assertGreater(lb, 0.0)

    def test_higher_imbalance_means_higher_metric(self):
        balanced = load_balance_metric([0.5, 0.5, 0.5, 0.5])
        imbalanced = load_balance_metric([1.0, 0.0, 0.5, 0.5])
        self.assertLess(balanced, imbalanced)


class TestPFMPPOReward(unittest.TestCase):
    def test_lower_response_time_better(self):
        fast = pfmppo_reward(response_t=1.0, energy=100.0, load_balance=0.5)
        slow = pfmppo_reward(response_t=10.0, energy=100.0, load_balance=0.5)
        self.assertGreater(fast, slow)

    def test_lower_energy_better(self):
        low_e = pfmppo_reward(response_t=5.0, energy=10.0, load_balance=0.5)
        high_e = pfmppo_reward(response_t=5.0, energy=1000.0, load_balance=0.5)
        self.assertGreater(low_e, high_e)

    def test_lower_lb_better(self):
        balanced = pfmppo_reward(response_t=5.0, energy=100.0, load_balance=0.01)
        imbalanced = pfmppo_reward(response_t=5.0, energy=100.0, load_balance=1.0)
        self.assertGreater(balanced, imbalanced)

    def test_reward_is_finite(self):
        r = pfmppo_reward(response_t=0.001, energy=0.001, load_balance=0.001)
        self.assertTrue(math.isfinite(r))


if __name__ == "__main__":
    unittest.main(verbosity=2)
