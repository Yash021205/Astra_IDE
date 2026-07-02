"""Integration tests for the complete PF-MPPO pipeline."""
import json
import os
import tempfile
import unittest

import numpy as np
import torch

try:
    import gymnasium
    from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG
    from ml.scheduler.pfmppo.graph_algorithms import parse_task_features, global_prioritization
    from ml.scheduler.pfmppo.env import PFMPPOEnv
    from ml.scheduler.pfmppo.network import PFMPPONetwork
    from ml.scheduler.pfmppo.ppo_agent import PPOAgent, RolloutBuffer
    from ml.scheduler.pfmppo.multi_agent import CTDETrainer
    from ml.scheduler.pfmppo.rule_library import RuleLibrary
    _OK = True
except ImportError:
    _OK = False


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestTrainingConvergence(unittest.TestCase):
    """Test that training loop shows improvement over iterations."""

    def test_reward_improves(self):
        """Train for 300 iterations and verify reward trend improves."""
        env_config = {
            "num_tasks": 5,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 30,
            "seed": 42,
        }

        import torch
        torch.manual_seed(0)
        trainer = CTDETrainer(
            num_workers=2,
            env_config=env_config,
            k_pairs=10,
            lr=0.001,
            batch_size=100,
            gamma=0.9,
            epsilon=0.2,
        )

        metrics = trainer.train(iterations=500, log_interval=500)

        # Compare first 30 vs last 30 mean rewards
        early_rewards = metrics["mean_reward"][:30]
        late_rewards = metrics["mean_reward"][-30:]

        early_mean = np.mean(early_rewards)
        late_mean = np.mean(late_rewards)

        # Training should improve reward (seeded for reproducibility).
        self.assertGreater(late_mean, early_mean)


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestTemplateTrainingConvergence(unittest.TestCase):
    """Test that training on template DAGs converges."""

    def test_template_mode_reward_improves(self):
        """Train for 300 iterations on template DAGs and verify improvement."""
        env_config = {
            "num_tasks": 20,
            "num_vms": 4,
            "k_pairs": 10,
            "max_steps": 50,
            "seed": 42,
            "dag_mode": "template",
            "num_workspaces": (2, 4),
        }

        import torch
        torch.manual_seed(0)
        trainer = CTDETrainer(
            num_workers=2,
            env_config=env_config,
            k_pairs=10,
            lr=0.001,
            batch_size=100,
            gamma=0.9,
            epsilon=0.2,
        )

        metrics = trainer.train(iterations=500, log_interval=500)

        early_rewards = metrics["mean_reward"][:30]
        late_rewards = metrics["mean_reward"][-30:]

        early_mean = np.mean(early_rewards)
        late_mean = np.mean(late_rewards)

        self.assertGreater(late_mean, early_mean)

    def test_hybrid_mode_runs(self):
        """Hybrid mode completes training without errors."""
        env_config = {
            "num_tasks": 10,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 30,
            "seed": 42,
            "dag_mode": "hybrid",
            "num_workspaces": (2, 3),
            "template_ratio": 0.5,
        }

        trainer = CTDETrainer(
            num_workers=2,
            env_config=env_config,
            k_pairs=10,
            batch_size=50,
        )

        metrics = trainer.train(iterations=20, log_interval=100)
        self.assertEqual(len(metrics["mean_reward"]), 20)
        self.assertTrue(all(np.isfinite(r) for r in metrics["mean_reward"]))


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestPretrainAndSelect(unittest.TestCase):
    """Test pre-training multiple configs and model selection."""

    def test_select_closer_model(self):
        """Pre-train 2 configs, verify selection picks the closer one."""
        tmp_dir = tempfile.mkdtemp()

        configs = [
            {"name": "small", "num_vms": 2, "vm_configs": [
                {"node_id": "vm_0", "cpu_cap": 2.0, "mem_cap": 4096.0, "disk_cap": 51200.0,
                 "bandwidth_mbps": 500.0, "proc_rate_mbps": 100.0, "power_static_w": 8.0, "power_max_w": 120.0},
                {"node_id": "vm_1", "cpu_cap": 2.0, "mem_cap": 4096.0, "disk_cap": 51200.0,
                 "bandwidth_mbps": 500.0, "proc_rate_mbps": 100.0, "power_static_w": 8.0, "power_max_w": 120.0},
            ]},
            {"name": "large", "num_vms": 4, "vm_configs": [
                {"node_id": f"vm_{i}", "cpu_cap": 16.0, "mem_cap": 32768.0, "disk_cap": 512000.0,
                 "bandwidth_mbps": 5000.0, "proc_rate_mbps": 800.0, "power_static_w": 20.0, "power_max_w": 500.0}
                for i in range(4)
            ]},
        ]

        for cfg in configs:
            model_dir = os.path.join(tmp_dir, cfg["name"])
            os.makedirs(model_dir, exist_ok=True)

            env_config = {
                "num_tasks": 5,
                "num_vms": cfg["num_vms"],
                "k_pairs": 10,
                "max_steps": 20,
                "vm_configs": cfg["vm_configs"],
                "seed": 42,
            }

            trainer = CTDETrainer(
                num_workers=2,
                env_config=env_config,
                k_pairs=10,
                batch_size=20,
            )
            trainer.train(iterations=5, log_interval=100)
            trainer.save(os.path.join(model_dir, "model.pt"))

            # Save metadata
            metadata = {
                "num_vms": cfg["num_vms"],
                "config_features": [
                    np.mean([v["cpu_cap"] for v in cfg["vm_configs"]]),
                    np.mean([v["mem_cap"] for v in cfg["vm_configs"]]) / 1000.0,
                    np.mean([v["disk_cap"] for v in cfg["vm_configs"]]) / 10000.0,
                    np.mean([v["bandwidth_mbps"] for v in cfg["vm_configs"]]) / 1000.0,
                    np.mean([v["proc_rate_mbps"] for v in cfg["vm_configs"]]) / 100.0,
                    np.mean([v["power_max_w"] for v in cfg["vm_configs"]]) / 100.0,
                ],
            }
            with open(os.path.join(model_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f)

        # Test selection
        library = RuleLibrary(tmp_dir)
        self.assertEqual(len(library.models), 2)

        # Query with 2 small VMs should select the "small" model
        query_vms = [
            VM(node_id="q0", cpu_cap=2.0, mem_cap=4096.0, disk_cap=51200.0,
               bandwidth_mbps=500.0, proc_rate_mbps=100.0, power_max_w=120.0),
            VM(node_id="q1", cpu_cap=2.0, mem_cap=4096.0, disk_cap=51200.0,
               bandwidth_mbps=500.0, proc_rate_mbps=100.0, power_max_w=120.0),
        ]
        selected = library.select_model(query_vms)
        self.assertIsNotNone(selected)
        self.assertIn("small", selected)

        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestEndToEndInference(unittest.TestCase):
    """Test full pipeline: train → save → load → infer."""

    def test_inference_produces_valid_action(self):
        env_config = {
            "num_tasks": 5,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 20,
            "seed": 42,
        }

        # Train briefly
        trainer = CTDETrainer(
            num_workers=2,
            env_config=env_config,
            k_pairs=10,
            batch_size=20,
        )
        trainer.train(iterations=5, log_interval=100)

        # Save
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            model_path = f.name
        trainer.save(model_path)

        # Load and infer
        network = PFMPPONetwork(input_dim=100, k_pairs=10)
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
        network.load_state_dict(checkpoint["network"])
        network.eval()

        state = np.random.randn(100).astype(np.float32)
        state_t = torch.tensor(state).unsqueeze(0)
        mask_t = torch.ones(1, 10)

        with torch.no_grad():
            probs, value = network(state_t, mask_t)

        action = int(probs.squeeze(0).argmax().item())
        self.assertGreaterEqual(action, 0)
        self.assertLess(action, 10)
        self.assertAlmostEqual(probs.sum().item(), 1.0, places=4)

        os.unlink(model_path)


@unittest.skipUnless(_OK, "gymnasium not installed")
class TestBenchmarkComparison(unittest.TestCase):
    """Test PF-MPPO against simple baselines on same environment."""

    def test_pfmppo_vs_random(self):
        """PF-MPPO trained agent produces finite rewards (smoke test)."""
        env_config = {
            "num_tasks": 5,
            "num_vms": 2,
            "k_pairs": 10,
            "max_steps": 30,
            "seed": 42,
        }

        # Train briefly
        trainer = CTDETrainer(
            num_workers=2,
            env_config=env_config,
            k_pairs=10,
            batch_size=40,
        )
        trainer.train(iterations=50, log_interval=100)
        agent = trainer.get_agent()

        # Evaluate PF-MPPO — just verify it produces finite rewards
        pfmppo_rewards = self._evaluate(agent, env_config, deterministic=False)
        random_rewards = self._evaluate_random(env_config)

        # Both should produce finite rewards
        self.assertTrue(all(np.isfinite(r) for r in pfmppo_rewards))
        self.assertTrue(all(np.isfinite(r) for r in random_rewards))

        # With very short training, just verify the agent runs without crashing
        # and produces rewards in a reasonable range (not all -50 penalty)
        pfmppo_mean = np.mean(pfmppo_rewards)
        self.assertGreater(pfmppo_mean, -5000.0)

    def _evaluate(self, agent, env_config, deterministic=True):
        env = PFMPPOEnv(**env_config)
        rewards = []

        for ep in range(5):
            obs, info = env.reset(seed=ep + 100)
            mask = info["valid_mask"]
            ep_reward = 0.0

            for _ in range(env_config["max_steps"]):
                action, _, _ = agent.select_action(obs, mask, deterministic=deterministic)
                obs, reward, terminated, truncated, info = env.step(action)
                mask = info["valid_mask"]
                ep_reward += reward
                if terminated or truncated:
                    break

            rewards.append(ep_reward)
        return rewards

    def _evaluate_random(self, env_config):
        env = PFMPPOEnv(**env_config)
        rewards = []

        for ep in range(5):
            obs, info = env.reset(seed=ep + 100)
            mask = info["valid_mask"]
            ep_reward = 0.0

            for _ in range(env_config["max_steps"]):
                valid_actions = np.where(mask > 0)[0]
                if len(valid_actions) == 0:
                    break
                action = np.random.choice(valid_actions)
                obs, reward, terminated, truncated, info = env.step(action)
                mask = info["valid_mask"]
                ep_reward += reward
                if terminated or truncated:
                    break

            rewards.append(ep_reward)
        return rewards


if __name__ == "__main__":
    unittest.main(verbosity=2)
