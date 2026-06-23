"""Tests for graph algorithms (Algorithms 1, 2, admission control, cycle detection)."""
import unittest

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG
from ml.scheduler.pfmppo.graph_algorithms import (
    parse_task_features,
    global_prioritization,
    filter_admissible_pairs,
    detect_cycle,
    CyclicDependencyError,
)


class TestParseTaskFeatures(unittest.TestCase):
    def _make_chain_dag(self):
        """t0 -> t1 -> t2 -> t3"""
        dag = TaskDAG()
        for i in range(4):
            dag.add_task(Task(task_id=f"t{i}"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t2")
        dag.add_edge("t2", "t3")
        return dag

    def _make_diamond_dag(self):
        """t0 -> t1, t0 -> t2, t1 -> t3, t2 -> t3"""
        dag = TaskDAG()
        for i in range(4):
            dag.add_task(Task(task_id=f"t{i}"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t0", "t2")
        dag.add_edge("t1", "t3")
        dag.add_edge("t2", "t3")
        return dag

    def test_chain_succ_nums(self):
        dag = self._make_chain_dag()
        features = parse_task_features(dag)
        self.assertEqual(features["t0"]["succ_nums"], 1)
        self.assertEqual(features["t3"]["succ_nums"], 0)

    def test_chain_desc_nums(self):
        dag = self._make_chain_dag()
        features = parse_task_features(dag)
        self.assertEqual(features["t0"]["desc_nums"], 3)  # t1, t2, t3
        self.assertEqual(features["t1"]["desc_nums"], 2)  # t2, t3
        self.assertEqual(features["t3"]["desc_nums"], 0)

    def test_chain_task_layers(self):
        dag = self._make_chain_dag()
        features = parse_task_features(dag)
        self.assertEqual(features["t0"]["task_layers"], 0)
        self.assertEqual(features["t1"]["task_layers"], 1)
        self.assertEqual(features["t2"]["task_layers"], 2)
        self.assertEqual(features["t3"]["task_layers"], 3)

    def test_diamond_features(self):
        dag = self._make_diamond_dag()
        features = parse_task_features(dag)
        # t0 has 2 successors, 3 descendants
        self.assertEqual(features["t0"]["succ_nums"], 2)
        self.assertEqual(features["t0"]["desc_nums"], 3)
        self.assertEqual(features["t0"]["task_layers"], 0)
        # t3 is at layer 2
        self.assertEqual(features["t3"]["task_layers"], 2)
        self.assertEqual(features["t3"]["succ_nums"], 0)

    def test_wide_fan(self):
        """t0 -> t1, t0 -> t2, t0 -> t3, t0 -> t4"""
        dag = TaskDAG()
        for i in range(5):
            dag.add_task(Task(task_id=f"t{i}"))
        for i in range(1, 5):
            dag.add_edge("t0", f"t{i}")
        features = parse_task_features(dag)
        self.assertEqual(features["t0"]["succ_nums"], 4)
        self.assertEqual(features["t0"]["desc_nums"], 4)
        for i in range(1, 5):
            self.assertEqual(features[f"t{i}"]["task_layers"], 1)

    def test_cyclic_dag_raises(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0"))
        dag.add_task(Task(task_id="t1"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t0")
        with self.assertRaises(CyclicDependencyError):
            parse_task_features(dag)


class TestGlobalPrioritization(unittest.TestCase):
    def test_ordering(self):
        dag = TaskDAG()
        for i in range(4):
            dag.add_task(Task(task_id=f"t{i}"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t2")
        dag.add_edge("t2", "t3")

        features = parse_task_features(dag)
        sorted_tasks = global_prioritization(dag, features)

        # t0 should have highest weight (most descendants + successors)
        self.assertEqual(sorted_tasks[0].task_id, "t0")
        # Weights should be descending
        for i in range(len(sorted_tasks) - 1):
            self.assertGreaterEqual(sorted_tasks[i].weight, sorted_tasks[i + 1].weight)


class TestAdmissionControl(unittest.TestCase):
    def test_predecessor_check(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0", req_cpu=1.0, req_mem=512.0, req_disk=1024.0))
        dag.add_task(Task(task_id="t1", req_cpu=1.0, req_mem=512.0, req_disk=1024.0))
        dag.add_edge("t0", "t1")

        features = parse_task_features(dag)
        sorted_tasks = global_prioritization(dag, features)
        vms = [VM(node_id="vm_0", avail_cpu=4.0, avail_mem=8192.0, avail_disk=102400.0)]

        # Nothing completed: only t0 should be admissible (it has no predecessors)
        pairs = filter_admissible_pairs(sorted_tasks, vms, set(), dag, k=10)
        task_ids = [t.task_id for t, _ in pairs]
        self.assertIn("t0", task_ids)
        self.assertNotIn("t1", task_ids)

        # After t0 is done: t1 should be admissible
        pairs = filter_admissible_pairs(sorted_tasks, vms, {"t0"}, dag, k=10)
        task_ids = [t.task_id for t, _ in pairs]
        self.assertIn("t1", task_ids)

    def test_resource_check(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0", req_cpu=8.0, req_mem=16384.0, req_disk=1024.0))

        features = parse_task_features(dag)
        sorted_tasks = global_prioritization(dag, features)

        # VM too small
        small_vm = [VM(node_id="vm_0", avail_cpu=2.0, avail_mem=4096.0, avail_disk=102400.0)]
        pairs = filter_admissible_pairs(sorted_tasks, small_vm, set(), dag, k=10)
        self.assertEqual(len(pairs), 0)

        # VM large enough
        big_vm = [VM(node_id="vm_1", avail_cpu=16.0, avail_mem=32768.0, avail_disk=102400.0)]
        pairs = filter_admissible_pairs(sorted_tasks, big_vm, set(), dag, k=10)
        self.assertEqual(len(pairs), 1)

    def test_k_limit(self):
        dag = TaskDAG()
        for i in range(20):
            dag.add_task(Task(task_id=f"t{i}", req_cpu=0.5, req_mem=256.0, req_disk=512.0))

        features = parse_task_features(dag)
        sorted_tasks = global_prioritization(dag, features)
        vms = [VM(node_id=f"vm_{j}", avail_cpu=16.0, avail_mem=32768.0, avail_disk=512000.0)
               for j in range(4)]

        pairs = filter_admissible_pairs(sorted_tasks, vms, set(), dag, k=10)
        self.assertLessEqual(len(pairs), 10)


class TestCycleDetection(unittest.TestCase):
    def test_no_cycle(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0"))
        dag.add_task(Task(task_id="t1"))
        dag.add_edge("t0", "t1")
        self.assertFalse(detect_cycle(dag))  # returns False, no exception

    def test_with_cycle(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0"))
        dag.add_task(Task(task_id="t1"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t0")
        with self.assertRaises(CyclicDependencyError):
            detect_cycle(dag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
