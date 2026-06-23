"""Tests for DAG data structures (Task, VM, TaskDAG)."""
import unittest

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG


class TestTask(unittest.TestCase):
    def test_default_values(self):
        t = Task(task_id="t1")
        self.assertEqual(t.task_id, "t1")
        self.assertEqual(t.req_cpu, 1.0)
        self.assertEqual(t.succ_nums, 0)
        self.assertEqual(t.weight, 0.0)

    def test_custom_values(self):
        t = Task(task_id="t2", t_dur=5.0, req_cpu=2.0, req_mem=2048.0, data_size_mb=100.0)
        self.assertEqual(t.t_dur, 5.0)
        self.assertEqual(t.req_cpu, 2.0)
        self.assertEqual(t.req_mem, 2048.0)


class TestVM(unittest.TestCase):
    def test_default_values(self):
        vm = VM(node_id="vm_0")
        self.assertEqual(vm.cpu_cap, 4.0)
        self.assertEqual(vm.avail_cpu, 4.0)
        self.assertEqual(vm.bandwidth_mbps, 1000.0)

    def test_custom_values(self):
        vm = VM(node_id="vm_1", cpu_cap=16.0, mem_cap=32768.0, avail_cpu=12.0)
        self.assertEqual(vm.cpu_cap, 16.0)
        self.assertEqual(vm.avail_cpu, 12.0)


class TestTaskDAG(unittest.TestCase):
    def test_empty_dag(self):
        dag = TaskDAG()
        self.assertEqual(dag.num_tasks(), 0)
        self.assertEqual(dag.get_roots(), [])
        self.assertFalse(dag.has_cycle())

    def test_single_task(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t1"))
        self.assertEqual(dag.num_tasks(), 1)
        self.assertEqual(len(dag.get_roots()), 1)

    def test_linear_chain(self):
        dag = TaskDAG()
        for i in range(4):
            dag.add_task(Task(task_id=f"t{i}"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t2")
        dag.add_edge("t2", "t3")

        roots = dag.get_roots()
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].task_id, "t0")
        self.assertEqual(dag.get_successors("t0"), ["t1"])
        self.assertEqual(dag.get_predecessors("t3"), ["t2"])
        self.assertFalse(dag.has_cycle())

    def test_diamond_dag(self):
        dag = TaskDAG()
        for i in range(4):
            dag.add_task(Task(task_id=f"t{i}"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t0", "t2")
        dag.add_edge("t1", "t3")
        dag.add_edge("t2", "t3")

        roots = dag.get_roots()
        self.assertEqual(len(roots), 1)
        self.assertEqual(dag.get_predecessors("t3"), ["t1", "t2"])
        self.assertFalse(dag.has_cycle())

    def test_cycle_detection(self):
        dag = TaskDAG()
        dag.add_task(Task(task_id="t0"))
        dag.add_task(Task(task_id="t1"))
        dag.add_task(Task(task_id="t2"))
        dag.add_edge("t0", "t1")
        dag.add_edge("t1", "t2")
        dag.add_edge("t2", "t0")  # cycle

        self.assertTrue(dag.has_cycle())

    def test_get_task(self):
        dag = TaskDAG()
        t = Task(task_id="t1", req_cpu=3.0)
        dag.add_task(t)
        retrieved = dag.get_task("t1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.req_cpu, 3.0)
        self.assertIsNone(dag.get_task("nonexistent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
