"""
Unit tests for the research-grounded risk scorer.
See docs/research/01-adaptive-sandboxing.md for the basis of every value here.
"""
import unittest

from ml.risk_scorer.scorer import RiskScorer, WorkloadRequest


class TestLanguageSubscore(unittest.TestCase):
    def setUp(self):
        self.s = RiskScorer()

    def test_shell_is_highest_class(self):
        self.assertEqual(self.s._language_subscore("bash"), 1.0)
        self.assertEqual(self.s._language_subscore("powershell"), 1.0)

    def test_interpreted_ffi_is_medium(self):
        self.assertEqual(self.s._language_subscore("python"), 0.5)
        self.assertEqual(self.s._language_subscore("javascript"), 0.5)

    def test_managed_is_low(self):
        self.assertEqual(self.s._language_subscore("go"), 0.2)
        self.assertEqual(self.s._language_subscore("rust"), 0.2)
        self.assertEqual(self.s._language_subscore("java"), 0.2)


class TestTierThresholds(unittest.TestCase):
    def setUp(self):
        self.s = RiskScorer()

    def test_tier_boundaries(self):
        self.assertEqual(self.s.select_tier(0.0),  "runc")
        self.assertEqual(self.s.select_tier(0.29), "runc")
        self.assertEqual(self.s.select_tier(0.30), "gvisor")       # crossover
        self.assertEqual(self.s.select_tier(0.69), "gvisor")
        self.assertEqual(self.s.select_tier(0.70), "firecracker")  # crossover
        self.assertEqual(self.s.select_tier(1.00), "firecracker")


class TestEndToEndScoring(unittest.TestCase):
    def setUp(self):
        self.s = RiskScorer()

    def test_safe_managed_high_trust_gets_runc(self):
        req = WorkloadRequest(language="go", network_access=False,
                              filesystem_write=False, user_trust=0.95,
                              code_snippet='fmt.Println("hi")')
        score, tier = self.s.score_and_select(req)
        self.assertEqual(tier, "runc")
        self.assertLess(score, 0.30)

    def test_plain_python_trusted_stays_low(self):
        # python(0.5*0.25) + fs_write(1*0.10) + trust(0.1*0.20) = 0.245 -> runc
        req = WorkloadRequest(language="python", network_access=False,
                              filesystem_write=True, user_trust=0.9,
                              code_snippet="print('hello')")
        score, tier = self.s.score_and_select(req)
        self.assertLess(score, 0.30)
        self.assertEqual(tier, "runc")

    def test_network_python_low_trust_promotes_to_gvisor(self):
        req = WorkloadRequest(language="python", network_access=True,
                              filesystem_write=True, user_trust=0.3,
                              code_snippet="import requests")
        score, tier = self.s.score_and_select(req)
        self.assertGreaterEqual(score, 0.30)
        self.assertEqual(tier, "gvisor")

    def test_shell_with_escape_vector_low_trust_is_firecracker(self):
        req = WorkloadRequest(language="bash", network_access=True,
                              filesystem_write=True, user_trust=0.1,
                              code_snippet="unshare -r -n; mount /dev/sda /mnt")
        score, tier = self.s.score_and_select(req)
        self.assertGreaterEqual(score, 0.70)
        self.assertEqual(tier, "firecracker")

    def test_score_is_clamped_to_one(self):
        req = WorkloadRequest(language="bash", network_access=True,
                              filesystem_write=True, user_trust=0.0,
                              code_snippet="unshare; nsenter; insmod x.ko; "
                                           "echo > release_agent; cat /proc/self/exe")
        self.assertLessEqual(self.s.score(req), 1.0)


class TestPythonAST(unittest.TestCase):
    """AST analysis must ignore comments/strings (no false positives)."""
    def setUp(self):
        self.s = RiskScorer()

    def test_subprocess_in_comment_not_flagged(self):
        clean = WorkloadRequest(language="python", filesystem_write=False,
                                user_trust=0.9,
                                code_snippet="# we avoid subprocess here\nx = 1 + 1")
        b = self.s.score_detailed(clean)
        self.assertEqual(b.code_signature, 0.0)
        self.assertEqual(b.matched_vectors, ())

    def test_subprocess_in_string_not_flagged(self):
        clean = WorkloadRequest(language="python", filesystem_write=False,
                                user_trust=0.9,
                                code_snippet='msg = "do not use os.system"')
        b = self.s.score_detailed(clean)
        self.assertEqual(b.code_signature, 0.0)

    def test_real_os_system_call_flagged(self):
        dirty = WorkloadRequest(language="python", filesystem_write=False,
                                user_trust=0.9,
                                code_snippet="import os\nos.system('ls')")
        b = self.s.score_detailed(dirty)
        self.assertGreater(b.code_signature, 0.0)
        self.assertIn("os.system()", b.matched_vectors)

    def test_eval_flagged(self):
        dirty = WorkloadRequest(language="python", filesystem_write=False,
                                user_trust=0.9, code_snippet="eval('2+2')")
        b = self.s.score_detailed(dirty)
        self.assertIn("eval()", b.matched_vectors)

    def test_subprocess_shell_true_is_high_severity(self):
        low  = WorkloadRequest(language="python", filesystem_write=False, user_trust=0.9,
                               code_snippet="import subprocess\nsubprocess.run(['ls'])")
        high = WorkloadRequest(language="python", filesystem_write=False, user_trust=0.9,
                               code_snippet="import subprocess\nsubprocess.run('ls', shell=True)")
        self.assertGreater(self.s.score_detailed(high).code_signature,
                           self.s.score_detailed(low).code_signature)

    def test_invalid_python_falls_back_to_token_scan(self):
        snippet = WorkloadRequest(language="python", filesystem_write=False,
                                  user_trust=0.9,
                                  code_snippet="this is not python but mount /dev/sda")
        b = self.s.score_detailed(snippet)
        self.assertGreater(b.code_signature, 0.0)


class TestShellTokenScan(unittest.TestCase):
    def setUp(self):
        self.s = RiskScorer()

    def test_word_boundary_avoids_false_positive(self):
        b = self.s.score_detailed(WorkloadRequest(
            language="bash", filesystem_write=False, user_trust=0.9,
            code_snippet="echo mounting evidence"))
        self.assertNotIn("mount", b.matched_vectors)

    def test_real_mount_command_flagged(self):
        b = self.s.score_detailed(WorkloadRequest(
            language="bash", filesystem_write=False, user_trust=0.9,
            code_snippet="mount /dev/sda1 /mnt"))
        self.assertIn("mount", b.matched_vectors)

    def test_docker_sock_flagged_any_language(self):
        b = self.s.score_detailed(WorkloadRequest(
            language="bash", filesystem_write=False, user_trust=0.9,
            code_snippet="curl --unix-socket /var/run/docker.sock http://x"))
        self.assertIn("docker.sock", b.matched_vectors)


class TestAblationConfig(unittest.TestCase):
    """Weights/thresholds must be overridable for the ablation study."""
    def test_custom_weights_change_score(self):
        default = RiskScorer()
        custom  = RiskScorer(weight_language=0.5, weight_code_scan=0.1,
                             weight_user_trust=0.2, weight_network=0.1,
                             weight_fs_write=0.1)
        req = WorkloadRequest(language="bash", network_access=False,
                              filesystem_write=False, user_trust=0.9)
        self.assertNotEqual(default.score(req), custom.score(req))

    def test_breakdown_explain_is_readable(self):
        b = RiskScorer().score_detailed(WorkloadRequest(
            language="bash", network_access=True, filesystem_write=True,
            user_trust=0.2, code_snippet="mount /dev/sda /mnt"))
        text = b.explain()
        self.assertIn("risk=", text)
        self.assertIn("firecracker", text)


class TestPaper2DifficultySeverity(unittest.TestCase):
    """
    Severity must follow Paper 2 (arXiv:2603.02277) Table 1 difficulty ratings,
    inverse-mapped: an easier-to-exploit primitive (diff 1) yields HIGHER
    static-code severity than a diff-5 kernel exploit.
    """
    def setUp(self):
        self.s = RiskScorer()

    def _sig(self, code: str, lang: str = "bash") -> float:
        return self.s.score_detailed(WorkloadRequest(
            language=lang, filesystem_write=False, user_trust=0.9,
            code_snippet=code)).code_signature

    def test_diff1_docker_sock_outranks_diff5_packet_socket(self):
        # docker.sock (diff 1, severity 1.00) > af_packet (diff 5, severity 0.40)
        self.assertGreater(self._sig("cat /var/run/docker.sock"),
                           self._sig("socket(AF_PACKET, SOCK_RAW)"))

    def test_diff2_unshare_outranks_diff3_insmod(self):
        # unshare (diff 2, 0.85) > insmod (diff 3, 0.65)
        self.assertGreater(self._sig("unshare -rn"), self._sig("insmod evil.ko"))

    def test_known_cve_vectors_detected(self):
        # Spot-check vectors from Table 1 across all three layers
        for token in ["/proc/self/exe", "release_agent", "kubectl cp",
                      "kernel.core_pattern", "open_by_handle_at"]:
            b = self.s.score_detailed(WorkloadRequest(
                language="bash", filesystem_write=False, user_trust=0.9,
                code_snippet=f"do something with {token} here"))
            self.assertGreater(b.code_signature, 0.0, f"{token} not detected")

    def test_difficulty_severity_map_values(self):
        from ml.risk_scorer.scorer import _DIFF_SEVERITY
        self.assertEqual(_DIFF_SEVERITY[1], 1.00)
        self.assertEqual(_DIFF_SEVERITY[5], 0.40)
        # monotonic non-increasing with difficulty
        vals = [_DIFF_SEVERITY[d] for d in (1, 2, 3, 4, 5)]
        self.assertEqual(vals, sorted(vals, reverse=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
