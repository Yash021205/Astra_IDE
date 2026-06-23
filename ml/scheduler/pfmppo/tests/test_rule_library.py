"""Tests for the Rule Library and model selection (Algorithm 3)."""
import json
import os
import tempfile
import unittest

import numpy as np
import torch

from ml.scheduler.pfmppo.dag import VM
from ml.scheduler.pfmppo.network import PFMPPONetwork
from ml.scheduler.pfmppo.rule_library import RuleLibrary, ModelEntry


class TestRuleLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._create_mock_models()
        self.library = RuleLibrary(self.tmp_dir)

    def _create_mock_models(self):
        """Create mock model files in the temp directory."""
        configs = [
            {"name": "2_nodes", "num_vms": 2, "features": [2.0, 4.096, 5.12, 0.5, 1.0, 1.2]},
            {"name": "4_nodes", "num_vms": 4, "features": [7.5, 15.36, 21.76, 2.125, 3.75, 2.925]},
            {"name": "8_nodes", "num_vms": 8, "features": [7.5, 14.336, 20.48, 2.0, 3.5, 3.15]},
        ]

        for cfg in configs:
            model_dir = os.path.join(self.tmp_dir, cfg["name"])
            os.makedirs(model_dir, exist_ok=True)

            # Save a dummy model
            network = PFMPPONetwork(input_dim=100, k_pairs=10)
            torch.save({"network": network.state_dict()}, os.path.join(model_dir, "model.pt"))

            # Save metadata
            metadata = {
                "config_name": cfg["name"],
                "num_vms": cfg["num_vms"],
                "config_features": cfg["features"],
            }
            with open(os.path.join(model_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f)

    def test_scan_finds_models(self):
        self.assertEqual(len(self.library.models), 3)

    def test_list_models(self):
        models = self.library.list_models()
        self.assertEqual(len(models), 3)
        node_counts = {m["node_count"] for m in models}
        self.assertEqual(node_counts, {2, 4, 8})

    def test_select_model_by_count(self):
        # Query with 4 VMs matching the 4_nodes config features should prefer 4_nodes
        vms = [
            VM(node_id="vm_0", cpu_cap=4.0, mem_cap=8192.0, disk_cap=102400.0,
               bandwidth_mbps=1000.0, proc_rate_mbps=200.0, power_max_w=200.0),
            VM(node_id="vm_1", cpu_cap=8.0, mem_cap=16384.0, disk_cap=204800.0,
               bandwidth_mbps=2000.0, proc_rate_mbps=400.0, power_max_w=350.0),
            VM(node_id="vm_2", cpu_cap=2.0, mem_cap=4096.0, disk_cap=51200.0,
               bandwidth_mbps=500.0, proc_rate_mbps=100.0, power_max_w=120.0),
            VM(node_id="vm_3", cpu_cap=16.0, mem_cap=32768.0, disk_cap=512000.0,
               bandwidth_mbps=5000.0, proc_rate_mbps=800.0, power_max_w=500.0),
        ]
        selected = self.library.select_model(vms)
        self.assertIsNotNone(selected)
        self.assertIn("4_nodes", selected)

    def test_select_model_by_mmd(self):
        # Query with 2 small VMs should prefer 2_nodes
        vms = [VM(node_id=f"vm_{i}", cpu_cap=2.0, mem_cap=4096.0, disk_cap=51200.0,
                  bandwidth_mbps=500.0, proc_rate_mbps=100.0, power_max_w=120.0)
               for i in range(2)]
        selected = self.library.select_model(vms)
        self.assertIsNotNone(selected)
        self.assertIn("2_nodes", selected)

    def test_empty_library_returns_none(self):
        empty_lib = RuleLibrary(tempfile.mkdtemp())
        vms = [VM(node_id="vm_0")]
        self.assertIsNone(empty_lib.select_model(vms))

    def test_register_model(self):
        vms = [VM(node_id=f"vm_{i}") for i in range(6)]
        self.library.register_model(
            model_path="/fake/path/model.pt",
            cluster_config=vms,
            metrics={"mean_reward": -5.0},
        )
        self.assertEqual(len(self.library.models), 4)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
