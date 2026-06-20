"""Unit tests for the risk scorer."""
import unittest

from ml.risk_scorer.scorer import RiskScorer, WorkloadRequest


class TestRiskScoring(unittest.TestCase):
    def setUp(self):
        self.scorer = RiskScorer()

    def test_safe_python_high_trust_gets_runc(self):
        req = WorkloadRequest(
            language="python",
            network_access=False,
            filesystem_write=False,
            user_trust=0.9,
            code_snippet="print('hello')",
        )
        score, tier = self.scorer.score_and_select(req)
        self.assertEqual(tier, "runc")
        self.assertLess(score, 0.30)

    def test_python_with_filesystem_write_only_still_runc(self):
        # Single moderate factor (FS write 0.20) → still < 0.30 → runc
        req = WorkloadRequest(language="python", filesystem_write=True, user_trust=0.9)
        score, tier = self.scorer.score_and_select(req)
        self.assertAlmostEqual(score, 0.20, places=2)
        self.assertEqual(tier, "runc")

    def test_two_risk_factors_promote_to_gvisor(self):
        # Network (0.20) + FS write (0.20) = 0.40 → gvisor
        req = WorkloadRequest(
            language="python",
            network_access=True,
            filesystem_write=True,
            user_trust=0.9,
        )
        score, tier = self.scorer.score_and_select(req)
        self.assertAlmostEqual(score, 0.40, places=2)
        self.assertEqual(tier, "gvisor")

    def test_shell_lang_with_low_trust_promotes_to_firecracker(self):
        # bash (0.30) + network (0.20) + fs (0.20) + low trust (0.20) = 0.90 → firecracker
        req = WorkloadRequest(
            language="bash",
            network_access=True,
            filesystem_write=True,
            user_trust=0.2,
        )
        score, tier = self.scorer.score_and_select(req)
        self.assertGreaterEqual(score, 0.70)
        self.assertEqual(tier, "firecracker")

    def test_suspicious_keyword_bumps_score(self):
        clean = WorkloadRequest(language="python", filesystem_write=False, user_trust=0.9,
                                code_snippet="x = 1 + 1")
        dirty = WorkloadRequest(language="python", filesystem_write=False, user_trust=0.9,
                                code_snippet="import subprocess; subprocess.run(['ls'])")
        self.assertGreater(self.scorer.score(dirty), self.scorer.score(clean))

    def test_score_capped_at_one(self):
        req = WorkloadRequest(
            language="bash", network_access=True, filesystem_write=True,
            user_trust=0.0, code_snippet="rm -rf / && os.system('reboot')",
        )
        self.assertLessEqual(self.scorer.score(req), 1.0)


class TestTierSelection(unittest.TestCase):
    def setUp(self):
        self.scorer = RiskScorer()

    def test_tier_boundaries(self):
        self.assertEqual(self.scorer.select_tier(0.0),  "runc")
        self.assertEqual(self.scorer.select_tier(0.29), "runc")
        self.assertEqual(self.scorer.select_tier(0.30), "gvisor")  # boundary
        self.assertEqual(self.scorer.select_tier(0.69), "gvisor")
        self.assertEqual(self.scorer.select_tier(0.70), "firecracker")  # boundary
        self.assertEqual(self.scorer.select_tier(1.00), "firecracker")


if __name__ == "__main__":
    unittest.main(verbosity=2)
