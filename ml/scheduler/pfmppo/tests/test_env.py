"""Tests for the PF-MPPO Gymnasium environment."""
import unittest

import numpy as np

try:
    import gymnasium
    from ml.scheduler.pfmppo.env import PFMPPOEnv, encode_state, K_PAIRS_DEFAULT, FEATURES_PER_PAIR
    _OK = True
except ImportError:
    _OK = False


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestPFMPPOEnv(unittest.TestCase):
    def setUp(self):
        self.env = PFMPPOEnv(num_tasks=10, num_vms=4, k_pairs=10, max_steps=50, seed=42)

    def test_observation_shape(self):
        obs, info = self.env.reset()
        self.assertEqual(obs.shape, (K_PAIRS_DEFAULT * FEATURES_PER_PAIR,))
        self.assertEqual(obs.shape, (100,))

    def test_action_space(self):
        self.env.reset()
        self.assertEqual(self.env.action_space.n, K_PAIRS_DEFAULT)

    def test_valid_mask_in_info(self):
        _, info = self.env.reset()
        self.assertIn("valid_mask", info)
        mask = info["valid_mask"]
        self.assertEqual(mask.shape, (K_PAIRS_DEFAULT,))
        # At least one valid action
        self.assertGreater(mask.sum(), 0)

    def test_step_with_valid_action(self):
        obs, info = self.env.reset()
        mask = info["valid_mask"]
        valid_actions = np.where(mask > 0)[0]
        self.assertGreater(len(valid_actions), 0)

        action = valid_actions[0]
        next_obs, reward, terminated, truncated, next_info = self.env.step(action)

        self.assertEqual(next_obs.shape, (100,))
        self.assertIsInstance(reward, float)
        self.assertIsInstance(terminated, bool)
        self.assertIsInstance(truncated, bool)

    def test_invalid_action_penalty(self):
        obs, info = self.env.reset()
        mask = info["valid_mask"]

        # Find an invalid action (if any zero-padded slots exist)
        invalid_actions = np.where(mask == 0)[0]
        if len(invalid_actions) > 0:
            _, reward, _, _, step_info = self.env.step(invalid_actions[0])
            self.assertEqual(reward, -50.0)
            self.assertTrue(step_info["invalid_action"])

    def test_episode_terminates(self):
        self.env = PFMPPOEnv(num_tasks=3, num_vms=4, k_pairs=10, max_steps=100, seed=42)
        obs, info = self.env.reset()
        done = False
        steps = 0

        while not done and steps < 100:
            mask = info["valid_mask"]
            valid_actions = np.where(mask > 0)[0]
            if len(valid_actions) == 0:
                break
            action = valid_actions[0]
            obs, reward, terminated, truncated, info = self.env.step(action)
            done = terminated or truncated
            steps += 1

        # Should terminate (either all tasks done or max_steps)
        self.assertTrue(done or len(np.where(info["valid_mask"] > 0)[0]) == 0)

    def test_reward_is_finite(self):
        obs, info = self.env.reset()
        mask = info["valid_mask"]
        valid_actions = np.where(mask > 0)[0]
        if len(valid_actions) > 0:
            _, reward, _, _, _ = self.env.step(valid_actions[0])
            self.assertTrue(np.isfinite(reward))

    def test_zero_padding_when_few_pairs(self):
        # Small env with few tasks/VMs
        env = PFMPPOEnv(num_tasks=2, num_vms=1, k_pairs=10, seed=99)
        obs, info = env.reset()
        # Most of the state should be zero-padded
        mask = info["valid_mask"]
        num_valid = int(mask.sum())
        self.assertLessEqual(num_valid, 10)
        # Zero-padded region should be all zeros
        for i in range(num_valid, 10):
            offset = i * FEATURES_PER_PAIR
            self.assertTrue(np.all(obs[offset:offset + FEATURES_PER_PAIR] == 0.0))


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestEncodeState(unittest.TestCase):
    def test_empty_pairs(self):
        state = encode_state([], k=10)
        self.assertEqual(state.shape, (100,))
        self.assertTrue(np.all(state == 0.0))

    def test_feature_dimension(self):
        from ml.scheduler.pfmppo.dag import Task, VM
        pairs = [(Task(task_id="t0", req_cpu=1.0, req_mem=512.0, req_disk=1024.0),
                  VM(node_id="vm_0", avail_cpu=4.0, avail_mem=8192.0, avail_disk=102400.0))]
        state = encode_state(pairs, k=10)
        self.assertEqual(state.shape, (100,))
        # First 10 values should be non-zero (the pair features)
        self.assertFalse(np.all(state[:10] == 0.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
