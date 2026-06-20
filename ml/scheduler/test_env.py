"""Tests for the PPO Gymnasium environment (no SB3 dependency)."""
import unittest
import numpy as np

from ml.scheduler.env import (
    ClusterState,
    WorkloadJob,
    encode_observation,
    compute_balance,
    NUM_NODES_DEFAULT,
    NODE_FEATURES,
    JOB_FEATURES,
    CLUSTER_FEATURES,
)
from ml.scheduler.reward import compute_reward, RewardWeights


class TestObservationEncoding(unittest.TestCase):
    def test_observation_dimension(self):
        state = ClusterState.empty(NUM_NODES_DEFAULT)
        job   = WorkloadJob(0.5, 512, 0, 0.2, False, True)
        obs   = encode_observation(state, job, time_of_day_h=12.0)
        expected_dim = NUM_NODES_DEFAULT * NODE_FEATURES + JOB_FEATURES + CLUSTER_FEATURES
        self.assertEqual(obs.shape, (expected_dim,))

    def test_observation_values_in_unit_interval(self):
        state = ClusterState.empty(NUM_NODES_DEFAULT)
        state.cpu_util[0] = 0.7
        job   = WorkloadJob(2.0, 4096, 3, 0.5, True, True)
        obs   = encode_observation(state, job, time_of_day_h=15.0)
        self.assertTrue((obs >= 0).all())
        self.assertTrue((obs <= 1).all())


class TestBalance(unittest.TestCase):
    def test_perfectly_balanced(self):
        self.assertAlmostEqual(compute_balance(np.array([0.5, 0.5, 0.5, 0.5])), 1.0, places=2)

    def test_zero_load_is_balanced(self):
        self.assertAlmostEqual(compute_balance(np.array([0.0, 0.0, 0.0])), 1.0)

    def test_imbalanced_is_less_than_one(self):
        self.assertLess(compute_balance(np.array([1.0, 0.0, 0.0, 0.0])), 0.5)


class TestReward(unittest.TestCase):
    def test_lower_latency_means_higher_reward(self):
        kwargs = dict(
            resource_utilization=0.7,
            cluster_balance=0.9,
            energy_cost_kwh=2.0,
            carbon_intensity_gco2=400.0,
        )
        fast = compute_reward(startup_latency_seconds=1.0,  **kwargs)
        slow = compute_reward(startup_latency_seconds=10.0, **kwargs)
        self.assertGreater(fast, slow)

    def test_sla_violation_lowers_reward(self):
        kwargs = dict(
            startup_latency_seconds=1.0, resource_utilization=0.7,
            cluster_balance=0.9, energy_cost_kwh=2.0, carbon_intensity_gco2=400.0,
        )
        clean = compute_reward(**kwargs, sla_violated=False)
        bad   = compute_reward(**kwargs, sla_violated=True)
        self.assertGreater(clean, bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
