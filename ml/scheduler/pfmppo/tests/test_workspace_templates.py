"""Tests for workspace template DAG generation."""
import unittest

import numpy as np

from ml.scheduler.pfmppo.dag import Task, VM, TaskDAG
from ml.scheduler.pfmppo.workspace_templates import (
    ALL_TEMPLATES,
    GENERIC_TEMPLATE,
    PYTHON_TEMPLATE,
    NODEJS_TEMPLATE,
    CPP_TEMPLATE,
    MONOREPO_TEMPLATE,
    TEMPLATES,
    WorkspaceTemplate,
    SubTaskProfile,
    get_template_for_language,
    instantiate_template,
    generate_template_dag,
    compute_template_aggregates,
)


class TestTemplateDefinitions(unittest.TestCase):
    """Test that all templates are correctly defined."""

    def test_all_templates_have_subtasks(self):
        for template in ALL_TEMPLATES:
            self.assertGreater(len(template.subtasks), 0, f"{template.name} has no subtasks")

    def test_all_templates_have_edges(self):
        for template in ALL_TEMPLATES:
            self.assertGreater(len(template.edges), 0, f"{template.name} has no edges")

    def test_edge_indices_valid(self):
        for template in ALL_TEMPLATES:
            n = len(template.subtasks)
            for src, dst in template.edges:
                self.assertGreaterEqual(src, 0, f"{template.name}: edge src {src} < 0")
                self.assertLess(src, n, f"{template.name}: edge src {src} >= {n}")
                self.assertGreaterEqual(dst, 0, f"{template.name}: edge dst {dst} < 0")
                self.assertLess(dst, n, f"{template.name}: edge dst {dst} >= {n}")

    def test_python_template_structure(self):
        self.assertEqual(len(PYTHON_TEMPLATE.subtasks), 6)
        names = [s.name for s in PYTHON_TEMPLATE.subtasks]
        self.assertIn("image_pull", names)
        self.assertIn("pip_install", names)
        self.assertIn("devserver_start", names)

    def test_monorepo_has_parallel_installs(self):
        self.assertEqual(len(MONOREPO_TEMPLATE.subtasks), 7)
        names = [s.name for s in MONOREPO_TEMPLATE.subtasks]
        self.assertIn("pkg_a_install", names)
        self.assertIn("pkg_b_install", names)
        self.assertIn("pkg_c_install", names)

    def test_generic_is_minimal(self):
        self.assertEqual(len(GENERIC_TEMPLATE.subtasks), 3)

    def test_template_count(self):
        self.assertEqual(len(ALL_TEMPLATES), 7)


class TestLanguageMapping(unittest.TestCase):
    """Test language-to-template mapping."""

    def test_known_languages(self):
        self.assertEqual(get_template_for_language("python").name, "python_project")
        self.assertEqual(get_template_for_language("javascript").name, "nodejs_project")
        self.assertEqual(get_template_for_language("typescript").name, "nodejs_project")
        self.assertEqual(get_template_for_language("cpp").name, "cpp_project")
        self.assertEqual(get_template_for_language("go").name, "go_project")
        self.assertEqual(get_template_for_language("rust").name, "rust_project")

    def test_fallback_to_generic(self):
        self.assertEqual(get_template_for_language("java").name, "generic_project")
        self.assertEqual(get_template_for_language("unknown").name, "generic_project")
        self.assertEqual(get_template_for_language("").name, "generic_project")

    def test_case_insensitive(self):
        self.assertEqual(get_template_for_language("Python").name, "python_project")
        self.assertEqual(get_template_for_language("RUST").name, "rust_project")

    def test_whitespace_stripped(self):
        self.assertEqual(get_template_for_language("  python  ").name, "python_project")


class TestInstantiateTemplate(unittest.TestCase):
    """Test template instantiation produces valid DAGs."""

    def test_produces_correct_task_count(self):
        rng = np.random.default_rng(42)
        dag = instantiate_template(PYTHON_TEMPLATE, "ws0", rng)
        self.assertEqual(dag.num_tasks(), 6)

    def test_task_ids_prefixed(self):
        rng = np.random.default_rng(42)
        dag = instantiate_template(PYTHON_TEMPLATE, "ws_test", rng)
        for task in dag.get_all_tasks():
            self.assertTrue(task.task_id.startswith("ws_test_"), f"Bad ID: {task.task_id}")

    def test_dag_is_acyclic(self):
        rng = np.random.default_rng(42)
        for template in ALL_TEMPLATES:
            dag = instantiate_template(template, "ws0", rng)
            self.assertFalse(dag.has_cycle(), f"{template.name} produced cyclic DAG")

    def test_edges_match_template(self):
        rng = np.random.default_rng(42)
        dag = instantiate_template(GENERIC_TEMPLATE, "ws0", rng)
        # Generic: image_pull -> repo_clone -> ext_load
        self.assertIn("ws0_repo_clone", dag.succ_map.get("ws0_image_pull", []))
        self.assertIn("ws0_ext_load", dag.succ_map.get("ws0_repo_clone", []))

    def test_noise_produces_variance(self):
        durations = []
        for seed in range(100):
            rng = np.random.default_rng(seed)
            dag = instantiate_template(PYTHON_TEMPLATE, "ws0", rng)
            task = dag.get_task("ws0_pip_install")
            durations.append(task.t_dur)
        self.assertGreater(np.std(durations), 1.0)

    def test_values_always_positive(self):
        for seed in range(50):
            rng = np.random.default_rng(seed)
            for template in ALL_TEMPLATES:
                dag = instantiate_template(template, f"ws{seed}", rng)
                for task in dag.get_all_tasks():
                    self.assertGreater(task.t_dur, 0, f"Negative duration: {task.task_id}")
                    self.assertGreater(task.req_cpu, 0, f"Negative CPU: {task.task_id}")
                    self.assertGreater(task.req_mem, 0, f"Negative mem: {task.task_id}")
                    self.assertGreater(task.req_disk, 0, f"Negative disk: {task.task_id}")
                    self.assertGreater(task.data_size_mb, 0, f"Negative data: {task.task_id}")

    def test_all_templates_instantiate(self):
        rng = np.random.default_rng(42)
        for template in ALL_TEMPLATES:
            dag = instantiate_template(template, "ws0", rng)
            self.assertEqual(dag.num_tasks(), len(template.subtasks))


class TestGenerateTemplateDag(unittest.TestCase):
    """Test composite DAG generation for training."""

    def test_produces_dag_and_vms(self):
        rng = np.random.default_rng(42)
        dag, vms = generate_template_dag(num_workspaces=3, rng=rng)
        self.assertIsInstance(dag, TaskDAG)
        self.assertGreater(dag.num_tasks(), 0)
        self.assertGreater(len(vms), 0)

    def test_task_count_scales_with_workspaces(self):
        rng = np.random.default_rng(42)
        dag_small, _ = generate_template_dag(num_workspaces=2, rng=rng)
        rng = np.random.default_rng(42)
        dag_large, _ = generate_template_dag(num_workspaces=6, rng=rng)
        self.assertGreater(dag_large.num_tasks(), dag_small.num_tasks())

    def test_no_cross_workspace_edges(self):
        rng = np.random.default_rng(42)
        dag, _ = generate_template_dag(num_workspaces=4, rng=rng)
        for src_id, successors in dag.succ_map.items():
            src_ws = src_id.split("_")[0]  # "ws0", "ws1", etc.
            for dst_id in successors:
                dst_ws = dst_id.split("_")[0]
                self.assertEqual(src_ws, dst_ws,
                    f"Cross-workspace edge: {src_id} -> {dst_id}")

    def test_composite_dag_is_acyclic(self):
        rng = np.random.default_rng(42)
        dag, _ = generate_template_dag(num_workspaces=5, rng=rng)
        self.assertFalse(dag.has_cycle())

    def test_language_weights(self):
        rng = np.random.default_rng(42)
        dag, _ = generate_template_dag(
            num_workspaces=10,
            rng=rng,
            language_weights={"python": 1.0},
        )
        for task in dag.get_all_tasks():
            # Python template tasks: image_pull, repo_clone, pip_install, lsp_start, ext_load, devserver_start
            name_part = "_".join(task.task_id.split("_")[1:])
            valid_names = {"image_pull", "repo_clone", "pip_install", "lsp_start", "ext_load", "devserver_start"}
            self.assertIn(name_part, valid_names, f"Non-python task: {task.task_id}")

    def test_custom_vm_configs(self):
        rng = np.random.default_rng(42)
        vm_configs = [
            {"node_id": "test_vm_0", "cpu_cap": 8.0, "mem_cap": 16384.0},
            {"node_id": "test_vm_1", "cpu_cap": 4.0, "mem_cap": 8192.0},
        ]
        _, vms = generate_template_dag(num_workspaces=2, rng=rng, vm_configs=vm_configs)
        self.assertEqual(len(vms), 2)
        self.assertEqual(vms[0].node_id, "test_vm_0")


class TestComputeTemplateAggregates(unittest.TestCase):
    """Test aggregate computation for inference encoding."""

    def test_generic_aggregates(self):
        agg = compute_template_aggregates(GENERIC_TEMPLATE)
        self.assertEqual(agg["num_subtasks"], 3)
        self.assertEqual(agg["depth"], 2)
        self.assertGreater(agg["critical_path_duration"], 0)
        self.assertGreater(agg["peak_cpu"], 0)
        self.assertGreater(agg["total_disk"], 0)

    def test_python_has_more_depth_than_generic(self):
        py_agg = compute_template_aggregates(PYTHON_TEMPLATE)
        gen_agg = compute_template_aggregates(GENERIC_TEMPLATE)
        self.assertGreater(py_agg["depth"], gen_agg["depth"])
        self.assertGreater(py_agg["num_subtasks"], gen_agg["num_subtasks"])

    def test_cpp_has_high_peak_cpu(self):
        cpp_agg = compute_template_aggregates(CPP_TEMPLATE)
        gen_agg = compute_template_aggregates(GENERIC_TEMPLATE)
        self.assertGreater(cpp_agg["peak_cpu"], gen_agg["peak_cpu"])

    def test_critical_path_positive(self):
        for template in ALL_TEMPLATES:
            agg = compute_template_aggregates(template)
            self.assertGreater(agg["critical_path_duration"], 0, f"{template.name}")

    def test_monorepo_parallel_install_affects_peak(self):
        agg = compute_template_aggregates(MONOREPO_TEMPLATE)
        # 3 parallel installs: peak CPU should be sum of all 3
        total_pkg_cpu = sum(
            s.req_cpu for s in MONOREPO_TEMPLATE.subtasks
            if "pkg" in s.name
        )
        self.assertGreaterEqual(agg["peak_cpu"], total_pkg_cpu)


if __name__ == "__main__":
    unittest.main(verbosity=2)
