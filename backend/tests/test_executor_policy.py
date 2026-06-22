"""
End-to-end: the live executor must intercept UNSAFE code (Paper 1, Yan
arXiv:2512.12806 §4.2) BEFORE running it, while letting benign code through the
policy gate.

NOTE on platforms: the language runners (`python3`, `bash`, `g++`) target the
Linux execution containers. On a Windows dev box Git-Bash hangs under subprocess
pipes, so the "benign actually runs" guarantee is asserted at the policy
boundary (classify → not UNSAFE) for bash, and exercised end-to-end only where a
real interpreter is dependable. The thing Subtask 5 adds — blocking UNSAFE code
before any runner is invoked — is platform-independent and fully covered here.
"""
import shutil
import unittest

from app.services import executor_service as ex
from app.services import transactional_executor as tx


class TestExecutorPolicyInterception(unittest.TestCase):

    # ── UNSAFE code is blocked before any runner executes (platform-independent)
    def test_destructive_bash_blocked_before_run(self):
        r = ex.execute("bash", "rm -rf /")
        self.assertEqual(r.exit_code, -3)
        self.assertIn("Policy Violation", r.stderr)
        self.assertEqual(r.stdout, "")            # never executed

    def test_escape_primitive_blocked(self):
        r = ex.execute("bash", "cat /proc/self/exe > /tmp/x")
        self.assertEqual(r.exit_code, -3)

    def test_docker_sock_blocked(self):
        r = ex.execute("bash",
                       "curl --unix-socket /var/run/docker.sock http://localhost/x")
        self.assertEqual(r.exit_code, -3)

    def test_fork_bomb_blocked(self):
        r = ex.execute("bash", ":(){ :|:& };:")
        self.assertEqual(r.exit_code, -3)

    # ── Benign code passes the policy gate (the contract Subtask 5 adds) ────────
    def test_benign_bash_passes_policy(self):
        # classify is the gate execute() consults; benign must not be UNSAFE.
        self.assertIsNot(tx.classify("echo hi"), tx.Policy.UNSAFE)

    def test_benign_python_passes_policy(self):
        self.assertIsNot(tx.classify("print('hello from astra')"), tx.Policy.UNSAFE)

    def test_benign_python_runs_when_interpreter_present(self):
        # Real end-to-end run where a dependable interpreter exists.
        if not shutil.which("python3"):
            self.skipTest("python3 not on PATH in this environment")
        r = ex.execute("python", "print('hello from astra')")
        self.assertNotEqual(r.exit_code, -3)      # policy did not block


if __name__ == "__main__":
    unittest.main(verbosity=2)
