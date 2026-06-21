"""
Code execution service.

This is a DEMO executor that runs user code inside the backend container.
In the full ASTRA-IDE architecture, execution happens inside per-user sandbox
pods (runc/gvisor/firecracker) — this service exists so the UI has a working
"Run" button before the K8s cluster is provisioned in Phase 3+.

Safety guardrails (still NOT suitable for hostile multi-tenant workloads):
  - Hard timeout (5 s)
  - Output truncated to 10 KB
  - Compiled binaries written to /tmp and deleted after execution
  - Process group killed on timeout to clean up subprocesses

Supported languages:
  - python   → python3 <file>
  - cpp      → g++ <file> -o <bin>, then run <bin>
  - javascript → node <file>
  - bash     → bash <file>
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass

# Hard limits
TIMEOUT_SECONDS = 5
MAX_OUTPUT_BYTES = 10 * 1024     # 10 KB per stream


def _resolve_python() -> str:
    """Pick a working Python interpreter: python3 (Linux containers) → python
    (Windows dev) → the backend's own interpreter. The Windows `python3` is a
    Store stub that returns 9009, so we probe rather than assume."""
    for cand in (sys.executable, "python3", "python"):
        try:
            if cand and subprocess.run([cand, "--version"], capture_output=True,
                                       timeout=5).returncode == 0:
                return cand
        except Exception:
            continue
    return sys.executable


PYTHON = _resolve_python()


@dataclass
class ExecutionResult:
    language:   str
    exit_code:  int
    stdout:     str
    stderr:     str
    runtime_ms: int
    timeout:    bool
    truncated:  bool


def _truncate(s: str) -> tuple[str, bool]:
    """Truncate output to MAX_OUTPUT_BYTES, return (clipped_str, was_truncated)."""
    if len(s.encode("utf-8", errors="replace")) <= MAX_OUTPUT_BYTES:
        return s, False
    encoded = s.encode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
    return encoded.decode("utf-8", errors="replace") + "\n…[truncated]", True


def _run(argv: list[str], stdin: str | None, cwd: str) -> ExecutionResult:
    """Run a subprocess with timeout and capture stdout/stderr."""
    started = time.time()
    timed_out = False
    truncated_any = False

    # start_new_session=True puts the child in its own process group so
    # killpg() reaches any subprocesses it spawned (cleanup on timeout)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
        text=True,
    )

    try:
        stdout, stderr = proc.communicate(input=stdin or "", timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        # POSIX: kill the whole process group so spawned children die too.
        # Non-POSIX (no os.killpg, e.g. Windows dev box) falls back to proc.kill().
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass
        stdout, stderr = proc.communicate()

    runtime_ms = int((time.time() - started) * 1000)
    stdout_clip, t1 = _truncate(stdout or "")
    stderr_clip, t2 = _truncate(stderr or "")
    truncated_any = t1 or t2

    return ExecutionResult(
        language="",                                     # set by caller
        exit_code=-1 if timed_out else (proc.returncode or 0),
        stdout=stdout_clip,
        stderr=stderr_clip
            + (f"\n[execution timed out after {TIMEOUT_SECONDS}s]" if timed_out else ""),
        runtime_ms=runtime_ms,
        timeout=timed_out,
        truncated=truncated_any,
    )


# ── Language adapters ───────────────────────────────────────────────────────

def _execute_python(code: str, stdin: str | None) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="astra-py-", ignore_cleanup_errors=True) as tmpdir:
        src = os.path.join(tmpdir, "main.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        result = _run([PYTHON, src], stdin, tmpdir)
        result.language = "python"
        return result


def _execute_cpp(code: str, stdin: str | None) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="astra-cpp-", ignore_cleanup_errors=True) as tmpdir:
        src = os.path.join(tmpdir, "main.cpp")
        binp = os.path.join(tmpdir, "main")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        # Compile first
        compile_result = _run(
            ["g++", "-std=c++17", "-O2", "-o", binp, src],
            stdin=None,
            cwd=tmpdir,
        )
        if compile_result.exit_code != 0 or compile_result.timeout:
            compile_result.language = "cpp"
            compile_result.stderr = "compile error:\n" + compile_result.stderr
            return compile_result
        # Then run
        run_result = _run([binp], stdin, tmpdir)
        run_result.language = "cpp"
        return run_result


def _execute_javascript(code: str, stdin: str | None) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="astra-js-", ignore_cleanup_errors=True) as tmpdir:
        src = os.path.join(tmpdir, "main.js")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        result = _run(["node", src], stdin, tmpdir)
        result.language = "javascript"
        return result


def _execute_bash(code: str, stdin: str | None) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="astra-sh-", ignore_cleanup_errors=True) as tmpdir:
        src = os.path.join(tmpdir, "main.sh")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        os.chmod(src, 0o755)
        result = _run(["bash", src], stdin, tmpdir)
        result.language = "bash"
        return result


# ── Public dispatcher ──────────────────────────────────────────────────────

_DISPATCH: dict[str, callable] = {
    "python":     _execute_python,
    "cpp":        _execute_cpp,
    "c++":        _execute_cpp,
    "javascript": _execute_javascript,
    "js":         _execute_javascript,
    "bash":       _execute_bash,
    "sh":         _execute_bash,
    "shell":      _execute_bash,
}


def supported_languages() -> list[str]:
    """The user-facing canonical names (lowercase)."""
    return ["python", "cpp", "javascript", "bash"]


def execute(language: str, code: str, stdin: str | None = None) -> ExecutionResult:
    """
    Run user code in the requested language and return the result.

    Pre-execution interception (Paper 1, Yan arXiv:2512.12806 §4.2): the policy
    engine classifies the code; UNSAFE (destructive / direct host-escape) code is
    BLOCKED and never executed. The full transactional snapshot/rollback layer
    activates once workspaces have persistent state (MinIO ticket); for the
    current ephemeral-temp-dir model the interception layer is the active guard.
    """
    lang = language.lower().strip()
    runner = _DISPATCH.get(lang)
    if runner is None:
        return ExecutionResult(
            language=lang,
            exit_code=-2,
            stdout="",
            stderr=f"Language '{language}' is not supported. Available: "
                   + ", ".join(supported_languages()),
            runtime_ms=0,
            timeout=False,
            truncated=False,
        )

    # Policy interception — block destructive / escape-grade code before it runs.
    from app.services import transactional_executor as _tx
    if _tx.classify(code) is _tx.Policy.UNSAFE:
        return ExecutionResult(
            language=lang,
            exit_code=-3,
            stdout="",
            stderr="Policy Violation: destructive or host-escape command "
                   "blocked before execution (sandbox policy, Paper 1 §4.2).",
            runtime_ms=0,
            timeout=False,
            truncated=False,
        )
    return runner(code, stdin)
