"""Tests for multi-agent CTDE training."""
import unittest

import numpy as np
import torch

try:
    import gymnasium
    from ml.scheduler.pfmppo.multi_agent import WorkerAgent, CTDETrainer
    from ml.scheduler.pfmppo.network import PFMPPONetwork
    _OK = True
except ImportError:
    _OK = False


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestWorkerAgent(unittest.TestCase):
    def setUp(self):
        self.network = PFMPPONetwork(input_dim=100, k_pairs=10)
        self.env_config = {
            "num_tasks": 5,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 20,
            "seed": 42,
        }
        self.worker = WorkerAgent(
            worker_id=0,
            env_config=self.env_config,
            network=self.network,
        )

    def test_collect_trajectory(self):
        buffer = self.worker.collect_trajectory(steps=10)
        self.assertEqual(len(buffer), 10)

    def test_sync_weights(self):
        new_network = PFMPPONetwork(input_dim=100, k_pairs=10)
        new_weights = new_network.state_dict()
        self.worker.sync_weights(new_weights)

        # Verify weights match
        for key in new_weights:
            self.assertTrue(
                torch.allclose(
                    self.worker.network.state_dict()[key],
                    new_weights[key],
                )
            )


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestCTDETrainer(unittest.TestCase):
    def setUp(self):
        self.env_config = {
            "num_tasks": 5,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 20,
            "seed": 42,
        }

    def test_creation(self):
        trainer = CTDETrainer(
            num_workers=2,
            env_config=self.env_config,
            k_pairs=10,
            batch_size=20,
        )
        self.assertEqual(len(trainer.workers), 2)

    def test_single_iteration(self):
        trainer = CTDETrainer(
            num_workers=2,
            env_config=self.env_config,
            k_pairs=10,
            batch_size=20,
            lr=0.001,
        )
        metrics = trainer.train(iterations=1, log_interval=1)
        self.assertIn("actor_loss", metrics)
        self.assertIn("mean_reward", metrics)
        self.assertEqual(len(metrics["actor_loss"]), 1)

    def test_weight_broadcast(self):
        trainer = CTDETrainer(
            num_workers=2,
            env_config=self.env_config,
            k_pairs=10,
            batch_size=20,
        )
        # After training, worker weights should match global
        trainer.train(iterations=1, log_interval=10)
        global_weights = trainer.global_agent.get_weights()

        # Broadcast manually and check
        for worker in trainer.workers:
            worker.sync_weights(global_weights)
            for key in global_weights:
                self.assertTrue(
                    torch.allclose(
                        worker.network.state_dict()[key],
                        global_weights[key],
                    )
                )

    def test_save_and_load(self):
        import tempfile
        import os

        trainer = CTDETrainer(
            num_workers=2,
            env_config=self.env_config,
            k_pairs=10,
            batch_size=20,
        )
        trainer.train(iterations=1, log_interval=10)

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name

        try:
            trainer.save(path)

            # Load into new trainer
            new_trainer = CTDETrainer(
                num_workers=2,
                env_config=self.env_config,
                k_pairs=10,
                batch_size=20,
            )
            new_trainer.load(path)

            # Weights should match
            for key in trainer.global_agent.get_weights():
                self.assertTrue(
                    torch.allclose(
                        trainer.global_agent.get_weights()[key],
                        new_trainer.global_agent.get_weights()[key],
                    )
                )
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
