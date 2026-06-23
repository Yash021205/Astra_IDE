"""
Tests for Google Cluster Trace data loader and episode generation.
"""
import os
import unittest

import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data")
TRACE_AVAILABLE = (
    os.path.isdir(os.path.join(DATA_DIR, "machine_events"))
    and os.path.isdir(os.path.join(DATA_DIR, "task_events"))
)


@unittest.skipUnless(TRACE_AVAILABLE, "Google cluster trace data not available")
class TestTraceLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ml.scheduler.pfmppo.google_trace_loader import GoogleTraceDataset
        cls.dataset = GoogleTraceDataset(
            data_dir=DATA_DIR,
            max_tasks_per_episode=30,
            max_jobs_per_episode=5,
            min_tasks_per_job=2,
        ).load()

    def test_machines_loaded(self):
        self.assertGreater(self.dataset.num_machines, 100)

    def test_jobs_loaded(self):
        self.assertGreater(self.dataset.num_jobs, 10)

    def test_stats_valid(self):
        stats = self.dataset.stats()
        self.assertGreater(stats["total_tasks"], 0)
        self.assertGreater(stats["median_duration_s"], 0)
        self.assertGreater(stats["tasks_per_job_avg"], 1.0)


@unittest.skipUnless(TRACE_AVAILABLE, "Google cluster trace data not available")
class TestEpisodeSampling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ml.scheduler.pfmppo.google_trace_loader import GoogleTraceDataset
        cls.dataset = GoogleTraceDataset(
            data_dir=DATA_DIR,
            max_tasks_per_episode=30,
            max_jobs_per_episode=5,
            min_tasks_per_job=2,
        ).load()

    def test_episode_produces_valid_dag(self):
        rng = np.random.default_rng(42)
        dag, vms = self.dataset.sample_episode(rng)
        self.assertGreater(dag.num_tasks(), 0)
        self.assertLessEqual(dag.num_tasks(), 30)
        self.assertFalse(dag.has_cycle())

    def test_episode_produces_vms(self):
        rng = np.random.default_rng(42)
        _, vms = self.dataset.sample_episode(rng)
        self.assertEqual(len(vms), 4)
        for vm in vms:
            self.assertGreater(vm.cpu_cap, 0)
            self.assertGreater(vm.mem_cap, 0)

    def test_different_seeds_produce_different_episodes(self):
        dag1, _ = self.dataset.sample_episode(np.random.default_rng(1))
        dag2, _ = self.dataset.sample_episode(np.random.default_rng(99))
        ids1 = {t.task_id for t in dag1.get_all_tasks()}
        ids2 = {t.task_id for t in dag2.get_all_tasks()}
        self.assertNotEqual(ids1, ids2)

    def test_episode_with_vm_configs(self):
        vm_configs = [
            {"node_id": "test_0", "cpu_cap": 8.0, "mem_cap": 16384.0},
            {"node_id": "test_1", "cpu_cap": 4.0, "mem_cap": 8192.0},
        ]
        rng = np.random.default_rng(42)
        _, vms = self.dataset.sample_episode(rng, vm_configs=vm_configs)
        self.assertEqual(len(vms), 2)
        self.assertEqual(vms[0].node_id, "test_0")


@unittest.skipUnless(TRACE_AVAILABLE, "Google cluster trace data not available")
class TestResourceScaling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ml.scheduler.pfmppo.google_trace_loader import GoogleTraceDataset
        cls.dataset = GoogleTraceDataset(
            data_dir=DATA_DIR,
            max_tasks_per_episode=30,
            max_jobs_per_episode=5,
        ).load()

    def test_cpu_in_expected_range(self):
        rng = np.random.default_rng(42)
        dag, _ = self.dataset.sample_episode(rng)
        for task in dag.get_all_tasks():
            self.assertGreaterEqual(task.req_cpu, 0.25)
            self.assertLessEqual(task.req_cpu, 32.0)

    def test_memory_in_expected_range(self):
        rng = np.random.default_rng(42)
        dag, _ = self.dataset.sample_episode(rng)
        for task in dag.get_all_tasks():
            self.assertGreaterEqual(task.req_mem, 128.0)
            self.assertLessEqual(task.req_mem, 131072.0)

    def test_duration_positive_and_bounded(self):
        rng = np.random.default_rng(42)
        dag, _ = self.dataset.sample_episode(rng)
        for task in dag.get_all_tasks():
            self.assertGreater(task.t_dur, 0)
            self.assertLessEqual(task.t_dur, 3600.0)


@unittest.skipUnless(TRACE_AVAILABLE, "Google cluster trace data not available")
class TestVMSampling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ml.scheduler.pfmppo.google_trace_loader import GoogleTraceDataset
        cls.dataset = GoogleTraceDataset(
            data_dir=DATA_DIR,
            max_tasks_per_episode=20,
        ).load()

    def test_vms_have_heterogeneous_capacity(self):
        rng = np.random.default_rng(42)
        _, vms = self.dataset.sample_episode(rng)
        cpus = [vm.cpu_cap for vm in vms]
        # Not all identical (trace has diverse machines)
        self.assertGreater(len(set(round(c, 2) for c in cpus)), 1)

    def test_vm_capacity_matches_available(self):
        rng = np.random.default_rng(42)
        _, vms = self.dataset.sample_episode(rng)
        for vm in vms:
            self.assertEqual(vm.cpu_cap, vm.avail_cpu)
            self.assertEqual(vm.mem_cap, vm.avail_mem)


@unittest.skipUnless(TRACE_AVAILABLE, "Google cluster trace data not available")
class TestIntegration(unittest.TestCase):
    """Full pipeline: trace data → env reset → valid observation."""

    def test_env_reset_with_trace_mode(self):
        try:
            import gymnasium  # noqa: F401
        except ImportError:
            self.skipTest("gymnasium not installed")

        from ml.scheduler.pfmppo.env import PFMPPOEnv
        env = PFMPPOEnv(
            dag_mode="trace",
            data_dir=DATA_DIR,
            num_tasks=30,
            max_steps=100,
            seed=42,
        )
        obs, info = env.reset()
        self.assertEqual(obs.shape, (100,))  # k_pairs=10 * 10 features
        self.assertIn("valid_mask", info)
        self.assertTrue(np.any(info["valid_mask"] > 0))

    def test_env_step_works_with_trace(self):
        try:
            import gymnasium  # noqa: F401
        except ImportError:
            self.skipTest("gymnasium not installed")

        from ml.scheduler.pfmppo.env import PFMPPOEnv
        env = PFMPPOEnv(
            dag_mode="trace",
            data_dir=DATA_DIR,
            num_tasks=20,
            max_steps=100,
            seed=42,
        )
        obs, info = env.reset()
        valid = np.where(info["valid_mask"] > 0)[0]
        if len(valid) > 0:
            obs2, reward, term, trunc, info2 = env.step(int(valid[0]))
            self.assertEqual(obs2.shape, (100,))
            self.assertIsInstance(reward, float)

    def test_generate_trace_dag_function(self):
        from ml.scheduler.pfmppo.google_trace_loader import (
            GoogleTraceDataset, generate_trace_dag,
        )
        dataset = GoogleTraceDataset(data_dir=DATA_DIR, max_tasks_per_episode=20).load()
        rng = np.random.default_rng(7)
        dag, vms = generate_trace_dag(dataset, rng)
        self.assertGreater(dag.num_tasks(), 0)
        self.assertFalse(dag.has_cycle())
        self.assertGreater(len(vms), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
