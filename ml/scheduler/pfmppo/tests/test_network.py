"""Tests for the PF-MPPO neural network architecture."""
import unittest

import torch
import numpy as np

from ml.scheduler.pfmppo.network import PFMPPONetwork


class TestPFMPPONetwork(unittest.TestCase):
    def setUp(self):
        self.network = PFMPPONetwork(input_dim=100, k_pairs=10)

    def test_output_shapes(self):
        state = torch.randn(1, 100)
        probs, value = self.network(state)
        self.assertEqual(probs.shape, (1, 10))
        self.assertEqual(value.shape, (1, 1))

    def test_batch_forward(self):
        state = torch.randn(32, 100)
        probs, value = self.network(state)
        self.assertEqual(probs.shape, (32, 10))
        self.assertEqual(value.shape, (32, 1))

    def test_probs_sum_to_one(self):
        state = torch.randn(5, 100)
        probs, _ = self.network(state)
        sums = probs.sum(dim=-1)
        for s in sums:
            self.assertAlmostEqual(s.item(), 1.0, places=5)

    def test_probs_non_negative(self):
        state = torch.randn(10, 100)
        probs, _ = self.network(state)
        self.assertTrue((probs >= 0).all())

    def test_action_masking(self):
        state = torch.randn(1, 100)
        mask = torch.zeros(1, 10)
        mask[0, :3] = 1.0  # Only first 3 actions valid

        probs, _ = self.network(state, valid_mask=mask)
        # Invalid actions should have zero probability
        self.assertAlmostEqual(probs[0, 3:].sum().item(), 0.0, places=5)
        # Valid actions should sum to 1
        self.assertAlmostEqual(probs[0, :3].sum().item(), 1.0, places=5)

    def test_all_masked_gives_uniform(self):
        state = torch.randn(1, 100)
        mask = torch.zeros(1, 10)  # All invalid

        probs, _ = self.network(state, valid_mask=mask)
        # Should fallback to uniform
        expected = 1.0 / 10
        for p in probs[0]:
            self.assertAlmostEqual(p.item(), expected, places=5)

    def test_gradient_flow(self):
        state = torch.randn(4, 100, requires_grad=True)
        probs, value = self.network(state)

        # Actor gradient
        loss_actor = -probs.log().mean()
        loss_actor.backward(retain_graph=True)
        self.assertIsNotNone(state.grad)

        # Critic gradient
        state.grad = None
        loss_critic = value.mean()
        loss_critic.backward()
        self.assertIsNotNone(state.grad)

    def test_parameter_count(self):
        total_params = sum(p.numel() for p in self.network.parameters())
        # 5 hidden layers (paper Table 2):
        # Input(100) -> 64: 100*64+64 = 6464
        # 64 -> 64: 64*64+64 = 4160
        # 64 -> 32: 64*32+32 = 2080
        # 32 -> 32: 32*32+32 = 1056
        # 32 -> 16: 32*16+16 = 528
        # Actor: 16*10+10 = 170 ; Critic: 16*1+1 = 17
        # Total: 14475
        self.assertEqual(total_params, 14475)

    def test_no_mask_works(self):
        state = torch.randn(2, 100)
        probs, value = self.network(state, valid_mask=None)
        self.assertEqual(probs.shape, (2, 10))
        sums = probs.sum(dim=-1)
        for s in sums:
            self.assertAlmostEqual(s.item(), 1.0, places=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
