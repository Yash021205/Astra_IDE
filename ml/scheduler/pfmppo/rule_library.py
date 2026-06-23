"""
Rule Library and Model Selection (Algorithm 3) for PF-MPPO.

Manages pre-trained models for different cluster configurations.
When the live cluster changes, selects the best pre-trained model using:
1. Node count proximity filtering
2. Maximum Mean Discrepancy (MMD) ranking
3. Shadow execution for final selection
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from ml.scheduler.pfmppo.dag import VM
from ml.scheduler.pfmppo.network import PFMPPONetwork


class ModelEntry:
    """A registered pre-trained model in the rule library."""

    def __init__(
        self,
        model_path: str,
        node_count: int,
        config_features: np.ndarray,
        metadata: Dict,
    ):
        self.model_path = model_path
        self.node_count = node_count
        self.config_features = config_features
        self.metadata = metadata
        self.mmd: float = 0.0


class RuleLibrary:
    """
    Manages pre-trained models and selects the best one for a live cluster.

    Algorithm 3 implementation:
    1. Filter by node count proximity (top-10 by (n_live - n_model)^2)
    2. Rank by MMD (simplified kernel mean embedding distance)
    3. Shadow execution on top-3 to pick the winner
    """

    def __init__(self, library_dir: str):
        self.library_dir = Path(library_dir)
        self.models: List[ModelEntry] = []
        self._scan_library()

    def _scan_library(self) -> None:
        """Scan the library directory for model files + metadata."""
        if not self.library_dir.exists():
            return

        for meta_file in self.library_dir.glob("*/metadata.json"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                model_path = str(meta_file.parent / "model.pt")
                if not Path(model_path).exists():
                    continue
                node_count = meta.get("num_vms", 4)
                config_features = np.array(
                    meta.get("config_features", [0.0] * 6), dtype=np.float32
                )
                self.models.append(ModelEntry(model_path, node_count, config_features, meta))
            except (json.JSONDecodeError, KeyError):
                continue

    def register_model(
        self,
        model_path: str,
        cluster_config: List[VM],
        metrics: Dict,
    ) -> None:
        """Register a trained model in the library."""
        config_features = self._extract_config_features(cluster_config)
        node_count = len(cluster_config)
        entry = ModelEntry(model_path, node_count, config_features, metrics)
        self.models.append(entry)

    def select_model(
        self,
        live_cluster_config: List[VM],
        k_pairs: int = 10,
    ) -> Optional[str]:
        """
        Algorithm 3: Select the best pre-trained model for the live cluster.

        Steps:
        1. Sort by node count proximity, take top-10
        2. Compute MMD, take top-3
        3. (Optional) Shadow execution -- simplified to MMD winner for now
        """
        if not self.models:
            return None

        n_live = len(live_cluster_config)
        live_features = self._extract_config_features(live_cluster_config)

        # Step 1: Filter by node count proximity
        sorted_by_count = sorted(
            self.models, key=lambda m: (n_live - m.node_count) ** 2
        )
        top_candidates = sorted_by_count[:min(10, len(sorted_by_count))]

        # Step 2: Compute MMD (simplified: L2 distance of mean feature vectors)
        for model in top_candidates:
            model.mmd = float(np.linalg.norm(live_features - model.config_features))

        sorted_by_mmd = sorted(top_candidates, key=lambda m: m.mmd)
        top_3 = sorted_by_mmd[:min(3, len(sorted_by_mmd))]

        # Step 3: Return the model with lowest MMD
        # (Full shadow execution requires running the env which is expensive;
        #  for production, this would spawn short rollouts with each model)
        return top_3[0].model_path if top_3 else None

    def select_model_with_shadow(
        self,
        live_cluster_config: List[VM],
        k_pairs: int = 10,
        shadow_steps: int = 50,
    ) -> Optional[str]:
        """
        Full Algorithm 3 with shadow execution on top-3 candidates.

        Runs each candidate model on a short episode and picks the one
        with highest cumulative reward.
        """
        if not self.models:
            return None

        n_live = len(live_cluster_config)
        live_features = self._extract_config_features(live_cluster_config)

        # Steps 1-2: same as select_model
        sorted_by_count = sorted(
            self.models, key=lambda m: (n_live - m.node_count) ** 2
        )
        top_candidates = sorted_by_count[:min(10, len(sorted_by_count))]

        for model in top_candidates:
            model.mmd = float(np.linalg.norm(live_features - model.config_features))

        sorted_by_mmd = sorted(top_candidates, key=lambda m: m.mmd)
        top_3 = sorted_by_mmd[:min(3, len(sorted_by_mmd))]

        # Step 3: Shadow execution
        from ml.scheduler.pfmppo.env import PFMPPOEnv

        vm_configs = [
            {
                "node_id": vm.node_id,
                "cpu_cap": vm.cpu_cap,
                "mem_cap": vm.mem_cap,
                "disk_cap": vm.disk_cap,
                "bandwidth_mbps": vm.bandwidth_mbps,
                "proc_rate_mbps": vm.proc_rate_mbps,
                "power_static_w": vm.power_static_w,
                "power_max_w": vm.power_max_w,
            }
            for vm in live_cluster_config
        ]

        best_model_path = None
        best_reward = float('-inf')

        for entry in top_3:
            network = PFMPPONetwork(input_dim=k_pairs * 10, k_pairs=k_pairs)
            checkpoint = torch.load(entry.model_path, map_location="cpu", weights_only=True)
            network.load_state_dict(checkpoint["network"])
            network.eval()

            env = PFMPPOEnv(
                num_tasks=10,
                num_vms=n_live,
                k_pairs=k_pairs,
                max_steps=shadow_steps,
                vm_configs=vm_configs,
                seed=123,
            )

            total_reward = 0.0
            obs, info = env.reset()
            valid_mask = info.get("valid_mask", np.ones(k_pairs, dtype=np.float32))

            for _ in range(shadow_steps):
                state_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
                mask_t = torch.tensor(valid_mask, dtype=torch.float32).unsqueeze(0)
                with torch.no_grad():
                    probs, _ = network(state_t, mask_t)
                action = int(probs.squeeze(0).argmax().item())
                obs, reward, terminated, truncated, info = env.step(action)
                valid_mask = info.get("valid_mask", np.ones(k_pairs, dtype=np.float32))
                total_reward += reward
                if terminated or truncated:
                    break

            if total_reward > best_reward:
                best_reward = total_reward
                best_model_path = entry.model_path

        return best_model_path

    def _extract_config_features(self, vms: List[VM]) -> np.ndarray:
        """Extract a summary feature vector from a list of VMs."""
        if not vms:
            return np.zeros(6, dtype=np.float32)

        cpu_caps = [vm.cpu_cap for vm in vms]
        mem_caps = [vm.mem_cap for vm in vms]
        disk_caps = [vm.disk_cap for vm in vms]
        bws = [vm.bandwidth_mbps for vm in vms]
        proc_rates = [vm.proc_rate_mbps for vm in vms]
        powers = [vm.power_max_w for vm in vms]

        return np.array([
            np.mean(cpu_caps),
            np.mean(mem_caps) / 1000.0,
            np.mean(disk_caps) / 10000.0,
            np.mean(bws) / 1000.0,
            np.mean(proc_rates) / 100.0,
            np.mean(powers) / 100.0,
        ], dtype=np.float32)

    def list_models(self) -> List[Dict]:
        """List all registered models."""
        return [
            {
                "model_path": m.model_path,
                "node_count": m.node_count,
                "metadata": m.metadata,
            }
            for m in self.models
        ]
