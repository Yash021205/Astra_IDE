"""Tests for the PPO agent (action selection, advantage computation, update)."""
import unittest

import numpy as np
import torch

from ml.scheduler.pfmppo.network import PFMPPONetwork
from ml.scheduler.pfmppo.ppo_agent import PPOAgent, RolloutBuffer, _weighted_random_sampling


class TestWeightedRandomSampling(unittest.TestCase):
    def test_returns_valid_index(self):
        probs = np.array([0.1, 0.5, 0.3, 0.1])
        for _ in range(100):
            action = _weighted_random_sampling(probs)
            self.assertGreaterEqual(action, 0)
            self.assertLess(action, 4)

    def test_deterministic_distribution(self):
        # If one action has prob 1.0, it should always be selected
        probs = np.array([0.0, 0.0, 1.0, 0.0])
        for _ in range(50):
            action = _weighted_random_sampling(probs)
            self.assertEqual(action, 2)

    def test_uniform_distribution(self):
        probs = np.array([0.25, 0.25, 0.25, 0.25])
        counts = np.zeros(4)
        for _ in range(1000):
            action = _weighted_random_sampling(probs)
            counts[action] += 1
        # Each should be selected roughly equally
        for c in counts:
            self.assertGreater(c, 100)  # at least 10% of the time


class TestPPOAgent(unittest.TestCase):
    def setUp(self):
        self.network = PFMPPONetwork(input_dim=100, k_pairs=10)
        self.agent = PPOAgent(self.network, lr=0.001, gamma=0.9, epsilon=0.2)

    def test_select_action_returns_valid(self):
        state = np.random.randn(100).astype(np.float32)
        valid_mask = np.ones(10, dtype=np.float32)

        action, log_prob, value = self.agent.select_action(state, valid_mask)
        self.assertGreaterEqual(action, 0)
        self.assertLess(action, 10)
        self.assertTrue(np.isfinite(log_prob))
        self.assertTrue(np.isfinite(value))

    def test_select_action_deterministic(self):
        state = np.random.randn(100).astype(np.float32)
        valid_mask = np.ones(10, dtype=np.float32)

        # Deterministic should always pick same action
        actions = set()
        for _ in range(10):
            action, _, _ = self.agent.select_action(state, valid_mask, deterministic=True)
            actions.add(action)
        self.assertEqual(len(actions), 1)

    def test_action_masking(self):
        state = np.random.randn(100).astype(np.float32)
        valid_mask = np.zeros(10, dtype=np.float32)
        valid_mask[:3] = 1.0  # Only actions 0, 1, 2 valid

        for _ in range(50):
            action, _, _ = self.agent.select_action(state, valid_mask)
            self.assertLess(action, 3)

    def test_compute_advantages_shapes(self):
        rewards = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0])
        values = torch.tensor([0.5, 1.5, 2.5, 3.5, 4.5])
        dones = torch.tensor([0.0, 0.0, 0.0, 0.0, 1.0])

        advantages, returns = self.agent.compute_advantages(rewards, values, dones)
        self.assertEqual(advantages.shape, (5,))
        self.assertEqual(returns.shape, (5,))

    def test_update_runs_without_error(self):
        buffer = RolloutBuffer()
        state = np.random.randn(100).astype(np.float32)
        valid_mask = np.ones(10, dtype=np.float32)

        for _ in range(20):
            buffer.add(
                state=state,
                action=np.random.randint(0, 10),
                log_prob=-1.0,
                reward=np.random.randn(),
                value=np.random.randn(),
                done=False,
                valid_mask=valid_mask,
            )

        metrics = self.agent.update(buffer)
        self.assertIn("actor_loss", metrics)
        self.assertIn("critic_loss", metrics)
        self.assertIn("entropy", metrics)
        self.assertTrue(np.isfinite(metrics["actor_loss"]))
        self.assertTrue(np.isfinite(metrics["critic_loss"]))


class TestRolloutBuffer(unittest.TestCase):
    def test_add_and_len(self):
        buffer = RolloutBuffer()
        self.assertEqual(len(buffer), 0)

        buffer.add(
            state=np.zeros(100, dtype=np.float32),
            action=0,
            log_prob=-1.0,
            reward=1.0,
            value=0.5,
            done=False,
            valid_mask=np.ones(10, dtype=np.float32),
        )
        self.assertEqual(len(buffer), 1)

    def test_get_tensors(self):
        buffer = RolloutBuffer()
        for _ in range(5):
            buffer.add(
                state=np.random.randn(100).astype(np.float32),
                action=3,
                log_prob=-0.5,
                reward=1.0,
                value=0.8,
                done=False,
                valid_mask=np.ones(10, dtype=np.float32),
            )

        tensors = buffer.get_tensors(torch.device("cpu"))
        self.assertEqual(tensors["states"].shape, (5, 100))
        self.assertEqual(tensors["actions"].shape, (5,))
        self.assertEqual(tensors["valid_masks"].shape, (5, 10))

    def test_clear(self):
        buffer = RolloutBuffer()
        buffer.add(np.zeros(100), 0, -1.0, 1.0, 0.5, False, np.ones(10))
        buffer.clear()
        self.assertEqual(len(buffer), 0)


class TestSaveLoad(unittest.TestCase):
    def test_save_and_load(self):
        import tempfile
        import os

        network = PFMPPONetwork(input_dim=100, k_pairs=10)
        agent = PPOAgent(network, lr=0.001)

        state = np.random.randn(100).astype(np.float32)
        action_before, _, _ = agent.select_action(state, deterministic=True)

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name

        try:
            agent.save(path)

            # Load into new agent
            new_network = PFMPPONetwork(input_dim=100, k_pairs=10)
            new_agent = PPOAgent(new_network, lr=0.001)
            new_agent.load(path)

            action_after, _, _ = new_agent.select_action(state, deterministic=True)
            self.assertEqual(action_before, action_after)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
